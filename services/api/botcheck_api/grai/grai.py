from __future__ import annotations

import base64
import binascii
import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import UserContext, require_editor, require_operator, require_viewer
from ..database import get_db
from ..exceptions import (
    DESTINATION_NOT_FOUND,
    GRAI_EVAL_ARTIFACT_NOT_FOUND,
    GRAI_EVAL_SUITE_NAME_CONFLICT,
    GRAI_EVAL_RUN_NOT_FOUND,
    GRAI_EVAL_SUITE_NOT_FOUND,
    GRAI_INVALID_TRANSPORT_PROFILE,
    GRAI_IMPORT_INVALID,
    JOB_QUEUE_UNAVAILABLE,
    ApiProblem,
)
from ..providers.service import resolve_tenant_provider_binding_state
from ..providers.usage_service import assert_provider_quota_available
from ..config import settings
from ..models import DestinationProtocol, GraiEvalCaseRow, GraiEvalPromptRow, GraiEvalRunRow, GraiEvalSuiteRow
from ..repo_runs import get_bot_destination_row_for_tenant
from ..retention import download_artifact_bytes
from .importer import compile_promptfoo_yaml
from .observability import (
    diagnostic_feature_names,
    observe_import,
    observe_report_request,
    observe_run_create,
    observe_run_enqueue,
)
from .schemas import (
    GraiEvalArtifactResponse,
    GraiEvalAssertionResponse,
    GraiEvalMatrixResponse,
    GraiEvalCasePayload,
    GraiEvalCaseResponse,
    GraiEvalRunCancelResponse,
    GraiEvalRunCreateRequest,
    GraiEvalRunProgressResponse,
    GraiEvalReportResponse,
    GraiEvalResultFiltersResponse,
    GraiEvalResultPageResponse,
    GraiEvalResultStatusFilter,
    GraiEvalRunHistoryDestinationResponse,
    GraiEvalRunHistoryResponse,
    GraiEvalRunResponse,
    GraiEvalPromptPayload,
    GraiEvalPromptResponse,
    GraiEvalSuiteDetailResponse,
    GraiEvalSuiteImportRequest,
    GraiEvalSuiteSummaryResponse,
    GraiEvalSuiteUpsertRequest,
    GraiEvalRunDestinationResponse,
    GraiImportDiagnosticResponse,
    GraiImportErrorResponse,
)
from .service_models import (
    GraiCompiledCase,
    GraiCompiledPrompt,
    GraiCompiledSuite,
    GraiEvalRunDestinationSnapshot,
    GraiEvalRunSnapshot,
    GraiImportValidationError,
)
from .store_service import (
    build_grai_eval_matrix,
    build_grai_eval_report,
    cancel_grai_eval_run,
    create_grai_eval_suite,
    create_grai_eval_run_snapshot,
    delete_grai_eval_suite,
    get_grai_eval_result_for_tenant,
    get_grai_eval_suite_counts,
    get_grai_eval_run_for_tenant,
    get_grai_eval_suite_for_tenant,
    list_grai_eval_cases_for_suite,
    list_grai_eval_runs_for_suite,
    list_grai_eval_run_destinations_for_tenant,
    list_grai_eval_run_destinations_for_runs,
    list_grai_eval_prompts_for_suite,
    list_grai_eval_results_page,
    list_grai_eval_suites_for_tenant,
    update_grai_eval_suite,
)

router = APIRouter()
event_logger = structlog.get_logger("botcheck.api.grai.suites")


def _suite_from_request(body: GraiEvalSuiteUpsertRequest) -> GraiCompiledSuite:
    return GraiCompiledSuite(
        name=body.name,
        description=body.description,
        metadata_json=dict(body.metadata_json),
        prompts=[
            GraiCompiledPrompt(
                label=prompt.label,
                prompt_text=prompt.prompt_text,
                metadata_json=dict(prompt.metadata_json),
            )
            for prompt in body.prompts
        ],
        cases=[
            GraiCompiledCase(
                description=case.description,
                vars_json=dict(case.vars_json),
                assert_json=[
                    {
                        "assertion_type": assertion.assertion_type,
                        "passed": None,
                        "score": None,
                        "threshold": assertion.threshold,
                        "weight": assertion.weight,
                        "raw_value": assertion.raw_value,
                        "failure_reason": None,
                        "latency_ms": None,
                    }
                    for assertion in case.assert_json
                ],
                tags_json=list(case.tags_json),
                metadata_json=dict(case.metadata_json),
                import_threshold=case.import_threshold,
            )
            for case in body.cases
        ],
        source_yaml=None,
    )


def _assertion_response(payload: dict[str, object]) -> GraiEvalAssertionResponse:
    return GraiEvalAssertionResponse(
        assertion_type=str(payload.get("assertion_type") or ""),
        passed=payload.get("passed") if isinstance(payload.get("passed"), bool) else None,
        score=float(payload["score"]) if payload.get("score") is not None else None,
        threshold=float(payload["threshold"]) if payload.get("threshold") is not None else None,
        weight=float(payload.get("weight") or 1.0),
        raw_value=str(payload["raw_value"]) if payload.get("raw_value") is not None else None,
        failure_reason=(
            str(payload["failure_reason"]) if payload.get("failure_reason") is not None else None
        ),
        latency_ms=int(payload["latency_ms"]) if payload.get("latency_ms") is not None else None,
    )


async def _suite_detail_response(
    db: AsyncSession,
    row: GraiEvalSuiteRow,
) -> GraiEvalSuiteDetailResponse:
    prompts = await list_grai_eval_prompts_for_suite(db, row.suite_id, row.tenant_id)
    cases = await list_grai_eval_cases_for_suite(db, row.suite_id, row.tenant_id)
    return GraiEvalSuiteDetailResponse(
        suite_id=row.suite_id,
        name=row.name,
        description=row.description,
        source_yaml=row.source_yaml,
        metadata_json=dict(row.metadata_json or {}),
        prompts=[
            GraiEvalPromptResponse(
                prompt_id=prompt.prompt_id,
                label=prompt.label,
                prompt_text=prompt.prompt_text,
                metadata_json=dict(prompt.metadata_json or {}),
            )
            for prompt in prompts
        ],
        cases=[
            GraiEvalCaseResponse(
                case_id=case.case_id,
                description=case.description,
                vars_json=dict(case.vars_json or {}),
                assert_json=[_assertion_response(item) for item in list(case.assert_json or [])],
                tags_json=list(case.tags_json or []),
                metadata_json=dict(case.metadata_json or {}),
                import_threshold=case.import_threshold,
            )
            for case in cases
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _list_summary_response(
    db: AsyncSession,
    rows: list[GraiEvalSuiteRow],
    *,
    tenant_id: str,
) -> list[GraiEvalSuiteSummaryResponse]:
    suite_ids = [row.suite_id for row in rows]
    prompt_counts, case_counts = await get_grai_eval_suite_counts(
        db,
        tenant_id=tenant_id,
        suite_ids=suite_ids,
    )
    summaries: list[GraiEvalSuiteSummaryResponse] = []
    for row in rows:
        summaries.append(
            GraiEvalSuiteSummaryResponse(
                suite_id=row.suite_id,
                name=row.name,
                description=row.description,
                prompt_count=prompt_counts.get(row.suite_id, 0),
                case_count=case_counts.get(row.suite_id, 0),
                has_source_yaml=bool((row.source_yaml or "").strip()),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return summaries


def _import_error_response(exc: GraiImportValidationError) -> JSONResponse:
    payload = GraiImportErrorResponse(
        error_code=GRAI_IMPORT_INVALID,
        detail="Promptfoo import failed",
        diagnostics=[
            GraiImportDiagnosticResponse(
                message=item.message,
                path=item.path,
                feature_name=item.feature_name,
                case_index=item.case_index,
            )
            for item in exc.diagnostics
        ],
    )
    return JSONResponse(status_code=422, content=payload.model_dump(exclude_none=True))


def _assertion_type_summary(cases: list[GraiEvalCaseRow]) -> list[str]:
    assertion_types: set[str] = set()
    for case in cases:
        for item in list(case.assert_json or []):
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("assertion_type") or "").strip()
            if candidate:
                assertion_types.add(candidate)
    return sorted(assertion_types)


def _run_response_from_snapshot(snapshot: GraiEvalRunSnapshot) -> GraiEvalRunResponse:
    return GraiEvalRunResponse(
        eval_run_id=snapshot.eval_run_id,
        suite_id=snapshot.suite_id,
        transport_profile_id=snapshot.transport_profile_id,
        transport_profile_ids=list(snapshot.transport_profile_ids),
        endpoint_at_start=snapshot.endpoint_at_start,
        headers_at_start=dict(snapshot.headers_at_start or {}),
        direct_http_config_at_start=(
            dict(snapshot.direct_http_config_at_start)
            if snapshot.direct_http_config_at_start is not None
            else None
        ),
        destinations=[_destination_response(item) for item in snapshot.destinations],
        trigger_source=snapshot.trigger_source,
        schedule_id=snapshot.schedule_id,
        triggered_by=snapshot.triggered_by,
        status=snapshot.status,
        terminal_outcome=snapshot.terminal_outcome,
        prompt_count=snapshot.prompt_count,
        case_count=snapshot.case_count,
        total_pairs=snapshot.total_pairs,
        dispatched_count=0,
        completed_count=0,
        failed_count=0,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


def _destination_response(
    snapshot: GraiEvalRunDestinationSnapshot,
) -> GraiEvalRunDestinationResponse:
    return GraiEvalRunDestinationResponse(
        destination_index=snapshot.destination_index,
        transport_profile_id=snapshot.transport_profile_id,
        label=snapshot.label,
        protocol=snapshot.protocol,
        endpoint_at_start=snapshot.endpoint_at_start,
        headers_at_start=dict(snapshot.headers_at_start or {}),
        direct_http_config_at_start=(
            dict(snapshot.direct_http_config_at_start)
            if snapshot.direct_http_config_at_start is not None
            else None
        ),
    )


def _legacy_run_destinations(row: GraiEvalRunRow) -> list[GraiEvalRunDestinationSnapshot]:
    return [
        GraiEvalRunDestinationSnapshot(
            destination_index=0,
            transport_profile_id=row.transport_profile_id,
            label=row.transport_profile_id or "(legacy destination)",
            protocol=DestinationProtocol.HTTP.value,
            endpoint_at_start=row.endpoint_at_start,
            headers_at_start=dict(row.headers_at_start or {}),
            direct_http_config_at_start=(
                dict(row.direct_http_config_at_start) if row.direct_http_config_at_start is not None else None
            ),
        )
    ]


def _run_history_destinations(
    row: GraiEvalRunRow,
    destinations: list[GraiEvalRunDestinationSnapshot] | None,
) -> list[GraiEvalRunDestinationSnapshot]:
    if destinations is not None:
        return destinations
    return _legacy_run_destinations(row)


def _run_history_response(
    row: GraiEvalRunRow,
    destinations: list[GraiEvalRunDestinationSnapshot] | None,
) -> GraiEvalRunHistoryResponse:
    history_destinations = _run_history_destinations(row, destinations)
    return GraiEvalRunHistoryResponse(
        eval_run_id=row.eval_run_id,
        suite_id=row.suite_id,
        transport_profile_id=str(row.transport_profile_id or ""),
        transport_profile_ids=[item.transport_profile_id for item in history_destinations],
        destination_count=len(history_destinations),
        destinations=[
            GraiEvalRunHistoryDestinationResponse(
                destination_index=item.destination_index,
                transport_profile_id=item.transport_profile_id,
                label=item.label,
            )
            for item in history_destinations
        ],
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        trigger_source=row.trigger_source,
        prompt_count=row.prompt_count,
        case_count=row.case_count,
        total_pairs=row.total_pairs,
        dispatched_count=row.dispatched_count,
        completed_count=row.completed_count,
        failed_count=row.failed_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
        triggered_by=row.triggered_by,
        schedule_id=row.schedule_id,
    )


async def _run_response_with_destinations(
    db: AsyncSession,
    row: GraiEvalRunRow,
) -> GraiEvalRunResponse:
    destinations = await list_grai_eval_run_destinations_for_tenant(
        db,
        eval_run_id=row.eval_run_id,
        tenant_id=row.tenant_id,
    )
    if not destinations:
        destinations = _legacy_run_destinations(row)
    return GraiEvalRunResponse(
        eval_run_id=row.eval_run_id,
        suite_id=row.suite_id,
        transport_profile_id=row.transport_profile_id,
        transport_profile_ids=[item.transport_profile_id for item in destinations],
        endpoint_at_start=row.endpoint_at_start,
        headers_at_start=dict(row.headers_at_start or {}),
        direct_http_config_at_start=(
            dict(row.direct_http_config_at_start) if row.direct_http_config_at_start is not None else None
        ),
        destinations=[_destination_response(item) for item in destinations],
        trigger_source=row.trigger_source,
        schedule_id=row.schedule_id,
        triggered_by=row.triggered_by,
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        prompt_count=row.prompt_count,
        case_count=row.case_count,
        total_pairs=row.total_pairs,
        dispatched_count=row.dispatched_count,
        completed_count=row.completed_count,
        failed_count=row.failed_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_progress_response(row: GraiEvalRunRow) -> GraiEvalRunProgressResponse:
    processed_pairs = row.completed_count + row.failed_count
    total_pairs = row.total_pairs
    progress_fraction = 0.0 if total_pairs <= 0 else min(1.0, processed_pairs / total_pairs)
    return GraiEvalRunProgressResponse(
        eval_run_id=row.eval_run_id,
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        prompt_count=row.prompt_count,
        case_count=row.case_count,
        total_pairs=row.total_pairs,
        dispatched_count=row.dispatched_count,
        completed_count=row.completed_count,
        failed_count=row.failed_count,
        progress_fraction=progress_fraction,
        updated_at=row.updated_at,
    )


def _default_provider_vendor_for_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith("gpt"):
        return "openai"
    return "anthropic"


def _result_filters_response(
    *,
    prompt_id: str | None,
    assertion_type: str | None,
    tag: str | None,
    status: GraiEvalResultStatusFilter | None,
    destination_index: int | None = None,
) -> GraiEvalResultFiltersResponse:
    return GraiEvalResultFiltersResponse(
        prompt_id=prompt_id,
        assertion_type=assertion_type,
        tag=tag,
        status=status,
        destination_index=destination_index,
    )


def _encode_results_cursor(*, created_at: datetime, eval_result_id: str) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "eval_result_id": eval_result_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode()


def _decode_results_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if not cursor:
        return None, None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode() + b"==="))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        eval_result_id = str(payload["eval_result_id"])
        return created_at, eval_result_id
    except (ValueError, KeyError, binascii.Error) as exc:
        raise ApiProblem(status=400, error_code="invalid_cursor", detail="Invalid grai eval results cursor") from exc


async def _resolve_http_transport_profile(
    db: AsyncSession,
    *,
    tenant_id: str,
    transport_profile_id: str,
):
    destination = await get_bot_destination_row_for_tenant(
        db,
        destination_id=transport_profile_id,
        tenant_id=tenant_id,
    )
    if destination is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Transport profile not found",
        )
    if str(destination.protocol).strip().lower() != DestinationProtocol.HTTP.value or not bool(
        destination.is_active
    ):
        raise ApiProblem(
            status=422,
            error_code=GRAI_INVALID_TRANSPORT_PROFILE,
            detail="Transport profile must be an active HTTP transport profile",
        )
    return destination


async def _resolve_http_transport_profiles(
    db: AsyncSession,
    *,
    tenant_id: str,
    transport_profile_ids: list[str],
) -> list[GraiEvalRunDestinationSnapshot]:
    destinations: list[GraiEvalRunDestinationSnapshot] = []
    for index, transport_profile_id in enumerate(transport_profile_ids):
        destination = await _resolve_http_transport_profile(
            db,
            tenant_id=tenant_id,
            transport_profile_id=transport_profile_id,
        )
        destinations.append(
            GraiEvalRunDestinationSnapshot(
                destination_index=index,
                transport_profile_id=destination.destination_id,
                label=str(destination.name or destination.destination_id),
                protocol=str(destination.protocol),
                endpoint_at_start=str(destination.endpoint or ""),
                headers_at_start=dict(destination.headers or {}),
                direct_http_config_at_start=dict(destination.direct_http_config or {}) or None,
            )
        )
    return destinations


@router.get("/suites", response_model=list[GraiEvalSuiteSummaryResponse])
async def list_grai_eval_suites(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    rows = await list_grai_eval_suites_for_tenant(db, user.tenant_id)
    return await _list_summary_response(db, rows, tenant_id=user.tenant_id)


@router.get("/suites/{suite_id}/runs", response_model=list[GraiEvalRunHistoryResponse])
async def list_grai_eval_suite_runs(
    suite_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    suite = await get_grai_eval_suite_for_tenant(db, suite_id, user.tenant_id)
    if suite is None:
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_SUITE_NOT_FOUND,
            detail="Grai eval suite not found",
        )
    rows = await list_grai_eval_runs_for_suite(
        db,
        suite_id=suite_id,
        tenant_id=user.tenant_id,
        limit=limit,
    )
    destinations_by_run = await list_grai_eval_run_destinations_for_runs(
        db,
        eval_run_ids=[row.eval_run_id for row in rows],
        tenant_id=user.tenant_id,
    )
    event_logger.info(
        "grai_eval_suite_runs_listed",
        eval_suite_id=suite_id,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        limit=limit,
        run_count=len(rows),
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_suite_runs.list",
        resource_type="grai_eval_suite",
        resource_id=suite_id,
        detail={"limit": limit, "run_count": len(rows)},
    )
    return [
        _run_history_response(row, destinations_by_run.get(row.eval_run_id))
        for row in rows
    ]


@router.post("/suites", response_model=GraiEvalSuiteDetailResponse, status_code=201)
async def create_grai_eval_suite_route(
    body: GraiEvalSuiteUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    try:
        row, prompt_ids, case_ids = await create_grai_eval_suite(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            payload=_suite_from_request(body),
        )
    except ValueError as exc:
        if str(exc) == GRAI_EVAL_SUITE_NAME_CONFLICT:
            raise ApiProblem(status=409, error_code=GRAI_EVAL_SUITE_NAME_CONFLICT, detail="Grai eval suite name already exists") from exc
        raise

    event_logger.info(
        "grai_suite_created",
        eval_suite_id=row.suite_id,
        eval_prompt_ids=prompt_ids,
        eval_case_ids=case_ids,
        tenant_id=user.tenant_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_suite.create",
        resource_type="grai_eval_suite",
        resource_id=row.suite_id,
        detail={"name": row.name},
    )
    await db.commit()
    return await _suite_detail_response(db, row)


@router.post(
    "/suites/import",
    response_model=GraiEvalSuiteDetailResponse,
    status_code=201,
    responses={422: {"model": GraiImportErrorResponse}},
)
async def import_grai_eval_suite(
    body: GraiEvalSuiteImportRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    started = time.perf_counter()
    try:
        compiled = compile_promptfoo_yaml(yaml_content=body.yaml_content, name_override=body.name)
    except GraiImportValidationError as exc:
        observe_import(outcome="compile_error", elapsed_s=time.perf_counter() - started)
        event_logger.warning(
            "grai_suite_import_invalid",
            tenant_id=user.tenant_id,
            diagnostics_count=len(exc.diagnostics),
            feature_names=diagnostic_feature_names(exc.diagnostics),
        )
        return _import_error_response(exc)
    try:
        row, prompt_ids, case_ids = await create_grai_eval_suite(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            payload=compiled,
        )
    except ValueError as exc:
        if str(exc) == GRAI_EVAL_SUITE_NAME_CONFLICT:
            observe_import(outcome="conflict", elapsed_s=time.perf_counter() - started)
            raise ApiProblem(status=409, error_code=GRAI_EVAL_SUITE_NAME_CONFLICT, detail="Grai eval suite name already exists") from exc
        raise
    except Exception:
        observe_import(outcome="error", elapsed_s=time.perf_counter() - started)
        raise

    observe_import(outcome="success", elapsed_s=time.perf_counter() - started)

    event_logger.info(
        "grai_suite_imported",
        eval_suite_id=row.suite_id,
        eval_prompt_ids=prompt_ids,
        eval_case_ids=case_ids,
        tenant_id=user.tenant_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_suite.import",
        resource_type="grai_eval_suite",
        resource_id=row.suite_id,
        detail={"name": row.name},
    )
    await db.commit()
    return await _suite_detail_response(db, row)


@router.get("/suites/{suite_id}", response_model=GraiEvalSuiteDetailResponse)
async def get_grai_eval_suite(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    row = await get_grai_eval_suite_for_tenant(db, suite_id, user.tenant_id)
    if row is None:
        raise ApiProblem(status=404, error_code=GRAI_EVAL_SUITE_NOT_FOUND, detail="Grai eval suite not found")
    return await _suite_detail_response(db, row)


@router.put("/suites/{suite_id}", response_model=GraiEvalSuiteDetailResponse)
async def update_grai_eval_suite_route(
    suite_id: str,
    body: GraiEvalSuiteUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    try:
        row, prompt_ids, case_ids = await update_grai_eval_suite(
            db,
            suite_id=suite_id,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            payload=_suite_from_request(body),
        )
    except LookupError as exc:
        raise ApiProblem(status=404, error_code=GRAI_EVAL_SUITE_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        if str(exc) == GRAI_EVAL_SUITE_NAME_CONFLICT:
            raise ApiProblem(status=409, error_code=GRAI_EVAL_SUITE_NAME_CONFLICT, detail="Grai eval suite name already exists") from exc
        raise

    event_logger.info(
        "grai_suite_updated",
        eval_suite_id=row.suite_id,
        eval_prompt_ids=prompt_ids,
        eval_case_ids=case_ids,
        tenant_id=user.tenant_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_suite.update",
        resource_type="grai_eval_suite",
        resource_id=row.suite_id,
        detail={"name": row.name},
    )
    await db.commit()
    return await _suite_detail_response(db, row)


@router.delete("/suites/{suite_id}", status_code=204)
async def delete_grai_eval_suite_route(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    deleted = await delete_grai_eval_suite(db, suite_id=suite_id, tenant_id=user.tenant_id)
    if not deleted:
        raise ApiProblem(status=404, error_code=GRAI_EVAL_SUITE_NOT_FOUND, detail="Grai eval suite not found")
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_suite.delete",
        resource_type="grai_eval_suite",
        resource_id=suite_id,
        detail={},
    )
    await db.commit()
    return Response(status_code=204)


@router.post("/runs", response_model=GraiEvalRunResponse, status_code=202)
async def create_grai_eval_run(
    body: GraiEvalRunCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        observe_run_create(outcome="queue_unavailable")
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Job queue unavailable",
        )

    suite = await get_grai_eval_suite_for_tenant(db, body.suite_id, user.tenant_id)
    if suite is None:
        observe_run_create(outcome="suite_not_found")
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_SUITE_NOT_FOUND,
            detail="Grai eval suite not found",
        )

    try:
        destinations = await _resolve_http_transport_profiles(
            db,
            tenant_id=user.tenant_id,
            transport_profile_ids=list(body.transport_profile_ids),
        )
    except ApiProblem as exc:
        if exc.error_code in {DESTINATION_NOT_FOUND, GRAI_INVALID_TRANSPORT_PROFILE}:
            outcome = "transport_profile_not_found" if exc.status == 404 else "invalid_transport_profile"
            observe_run_create(outcome=outcome)
        raise
    prompts = await list_grai_eval_prompts_for_suite(db, suite.suite_id, user.tenant_id)
    cases = await list_grai_eval_cases_for_suite(db, suite.suite_id, user.tenant_id)
    assertion_types = _assertion_type_summary(cases)
    judge_binding = await resolve_tenant_provider_binding_state(
        db,
        tenant_id=user.tenant_id,
        capability="judge",
        model=settings.grai_eval_judge_model,
        runtime_scope="judge",
    )
    judge_model = (
        str(judge_binding.get("model") or settings.grai_eval_judge_model).strip()
        or settings.grai_eval_judge_model
    )
    judge_vendor = str(
        judge_binding.get("vendor") or _default_provider_vendor_for_model(judge_model)
    ).strip().lower()
    judge_provider_id = (
        str(judge_binding.get("provider_id") or "").strip() or f"{judge_vendor}:{judge_model}"
    )
    estimated_pairs = max(1, len(prompts) * len(cases) * len(destinations))
    try:
        await assert_provider_quota_available(
            db,
            tenant_id=user.tenant_id,
            provider_id=judge_provider_id,
            runtime_scope="judge",
            capability="judge",
            source="grai_dispatch",
            estimated_usage={"requests": estimated_pairs},
        )
    except ValueError:
        # judge_provider_id was synthesised from vendor:model and may not be in the
        # catalog (e.g. non-default model override). Skip the quota check rather than
        # surfacing an unhelpful 500 — the request proceeds without quota enforcement.
        logger.warning(
            "grai.quota_preflight.skipped_unknown_provider",
            extra={"provider_id": judge_provider_id, "tenant_id": user.tenant_id},
        )

    snapshot = await create_grai_eval_run_snapshot(
        db,
        tenant_id=user.tenant_id,
        suite_id=suite.suite_id,
        destinations=destinations,
        trigger_source="manual",
        schedule_id=None,
        triggered_by=user.sub,
        prompt_count=len(prompts),
        case_count=len(cases),
    )

    enqueue_started = time.perf_counter()
    try:
        await arq_pool.enqueue_job(
            "run_grai_eval",
            payload={
                "eval_run_id": snapshot.eval_run_id,
                "tenant_id": snapshot.tenant_id,
            },
            _queue_name="arq:eval",
        )
    except Exception:
        await db.rollback()
        elapsed = time.perf_counter() - enqueue_started
        observe_run_enqueue(outcome="error", elapsed_s=elapsed)
        observe_run_create(outcome="enqueue_failed")
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Failed to enqueue grai eval job",
        )

    elapsed = time.perf_counter() - enqueue_started
    observe_run_enqueue(outcome="success", elapsed_s=elapsed)
    observe_run_create(outcome="success")

    event_logger.info(
        "grai_eval_run_enqueued",
        eval_run_id=snapshot.eval_run_id,
        suite_id=snapshot.suite_id,
        transport_profile_id=snapshot.transport_profile_id,
        transport_profile_ids=snapshot.transport_profile_ids,
        assertion_type=assertion_types[0] if len(assertion_types) == 1 else ("none" if not assertion_types else "mixed"),
        assertion_types=assertion_types,
        tenant_id=user.tenant_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="grai_run.create",
        resource_type="grai_eval_run",
        resource_id=snapshot.eval_run_id,
        detail={
            "suite_id": snapshot.suite_id,
            "transport_profile_id": snapshot.transport_profile_id,
            "transport_profile_ids": snapshot.transport_profile_ids,
            "trigger_source": snapshot.trigger_source,
            "assertion_types": assertion_types,
        },
    )
    await db.commit()
    return _run_response_from_snapshot(snapshot)


@router.get("/runs/{eval_run_id}", response_model=GraiEvalRunResponse)
async def get_grai_eval_run(
    eval_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
    )
    return await _run_response_with_destinations(db, row)


@router.get("/runs/{eval_run_id}/progress", response_model=GraiEvalRunProgressResponse)
async def get_grai_eval_run_progress(
    eval_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
    )
    return _run_progress_response(row)


@router.get("/runs/{eval_run_id}/report", response_model=GraiEvalReportResponse)
async def get_grai_eval_run_report(
    eval_run_id: str,
    prompt_id: str | None = None,
    assertion_type: str | None = None,
    tag: str | None = None,
    status: GraiEvalResultStatusFilter | None = None,
    destination_index: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    started = time.perf_counter()
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if row is None:
        observe_report_request(endpoint="report", outcome="not_found", elapsed_s=time.perf_counter() - started)
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
        )
    try:
        report = await build_grai_eval_report(
            db,
            eval_run_id=eval_run_id,
            tenant_id=user.tenant_id,
            prompt_id=prompt_id,
            assertion_type=assertion_type,
            tag=tag,
            status=status,
            destination_index=destination_index,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        observe_report_request(endpoint="report", outcome="error", elapsed_s=elapsed)
        event_logger.exception(
            "grai_eval_report_failed",
            eval_run_id=eval_run_id,
            tenant_id=user.tenant_id,
            error=str(exc),
        )
        raise
    elapsed = time.perf_counter() - started
    observe_report_request(endpoint="report", outcome="success", elapsed_s=elapsed)
    event_logger.info(
        "grai_eval_report_built",
        eval_run_id=eval_run_id,
        tenant_id=user.tenant_id,
        prompt_id=prompt_id,
        assertion_type=assertion_type,
        tag=tag,
        status=status,
        destination_index=destination_index,
        total_results=report["total_results"],
        failed_results=report["failed_results"],
    )
    return GraiEvalReportResponse(
        eval_run_id=eval_run_id,
        suite_id=row.suite_id,
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        total_pairs=row.total_pairs,
        filters=_result_filters_response(
            prompt_id=prompt_id,
            assertion_type=assertion_type,
            tag=tag,
            status=status,
            destination_index=destination_index,
        ),
        total_results=int(report["total_results"]),
        passed_results=int(report["passed_results"]),
        failed_results=int(report["failed_results"]),
        assertion_type_breakdown=list(report["assertion_type_breakdown"]),
        failing_prompt_variants=list(report["failing_prompt_variants"]),
        tag_failure_clusters=list(report["tag_failure_clusters"]),
        exemplar_failures=list(report["exemplar_failures"]),
    )


@router.get("/runs/{eval_run_id}/results", response_model=GraiEvalResultPageResponse)
async def list_grai_eval_results(
    eval_run_id: str,
    prompt_id: str | None = None,
    assertion_type: str | None = None,
    tag: str | None = None,
    status: GraiEvalResultStatusFilter | None = None,
    destination_index: int | None = None,
    cursor: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    started = time.perf_counter()
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if row is None:
        observe_report_request(endpoint="results", outcome="not_found", elapsed_s=time.perf_counter() - started)
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
        )
    limit = max(1, min(limit, 100))
    cursor_created_at, cursor_eval_result_id = _decode_results_cursor(cursor)
    try:
        items, next_created_at, next_eval_result_id = await list_grai_eval_results_page(
            db,
            eval_run_id=eval_run_id,
            tenant_id=user.tenant_id,
            prompt_id=prompt_id,
            assertion_type=assertion_type,
            tag=tag,
            status=status,
            destination_index=destination_index,
            limit=limit,
            cursor_created_at=cursor_created_at,
            cursor_eval_result_id=cursor_eval_result_id,
        )
    except Exception:
        elapsed = time.perf_counter() - started
        observe_report_request(endpoint="results", outcome="error", elapsed_s=elapsed)
        raise
    elapsed = time.perf_counter() - started
    observe_report_request(endpoint="results", outcome="success", elapsed_s=elapsed)
    next_cursor = (
        _encode_results_cursor(created_at=next_created_at, eval_result_id=next_eval_result_id)
        if next_created_at is not None and next_eval_result_id is not None
        else None
    )
    return GraiEvalResultPageResponse(
        eval_run_id=eval_run_id,
        filters=_result_filters_response(
            prompt_id=prompt_id,
            assertion_type=assertion_type,
            tag=tag,
            status=status,
            destination_index=destination_index,
        ),
        items=list(items),
        next_cursor=next_cursor,
    )


@router.get("/runs/{eval_run_id}/matrix", response_model=GraiEvalMatrixResponse)
async def get_grai_eval_run_matrix(
    eval_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    started = time.perf_counter()
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if row is None:
        observe_report_request(endpoint="matrix", outcome="not_found", elapsed_s=time.perf_counter() - started)
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
        )
    destinations = await list_grai_eval_run_destinations_for_tenant(
        db,
        eval_run_id=eval_run_id,
        tenant_id=user.tenant_id,
    )
    if not destinations:
        destinations = _legacy_run_destinations(row)
    try:
        matrix = await build_grai_eval_matrix(
            db,
            eval_run_id=eval_run_id,
            tenant_id=user.tenant_id,
            suite_id=row.suite_id,
            destinations=destinations,
        )
    except Exception:
        elapsed = time.perf_counter() - started
        observe_report_request(endpoint="matrix", outcome="error", elapsed_s=elapsed)
        raise
    elapsed = time.perf_counter() - started
    observe_report_request(endpoint="matrix", outcome="success", elapsed_s=elapsed)
    return GraiEvalMatrixResponse(
        eval_run_id=eval_run_id,
        suite_id=row.suite_id,
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        total_pairs=row.total_pairs,
        destinations=list(matrix["destinations"]),
        prompt_groups=list(matrix["prompt_groups"]),
    )


@router.get(
    "/runs/{eval_run_id}/results/{eval_result_id}/artifact",
    response_model=GraiEvalArtifactResponse,
)
async def get_grai_eval_result_artifact(
    eval_run_id: str,
    eval_result_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    row = await get_grai_eval_result_for_tenant(
        db,
        eval_run_id=eval_run_id,
        eval_result_id=eval_result_id,
        tenant_id=user.tenant_id,
    )
    if row is None or not row.raw_s3_key:
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_ARTIFACT_NOT_FOUND,
            detail="Grai eval artifact not found",
        )
    _MAX_ARTIFACT_BYTES = 2 * 1024 * 1024  # 2 MB
    try:
        body, _content_type = await download_artifact_bytes(settings, key=row.raw_s3_key)
    except Exception as exc:
        err = getattr(exc, "response", {}).get("Error", {})
        code = str(err.get("Code", "")).strip()
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise ApiProblem(
                status=404,
                error_code=GRAI_EVAL_ARTIFACT_NOT_FOUND,
                detail="Grai eval artifact not found",
            ) from exc
        raise ApiProblem(
            status=503,
            error_code="grai_eval_artifact_unavailable",
            detail="Grai eval artifact unavailable",
        ) from exc
    if len(body) > _MAX_ARTIFACT_BYTES:
        raise ApiProblem(
            status=422,
            error_code="grai_eval_artifact_too_large",
            detail="Grai eval artifact exceeds maximum size",
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiProblem(
            status=422,
            error_code="grai_eval_artifact_corrupt",
            detail="Grai eval artifact could not be parsed",
        ) from exc
    return GraiEvalArtifactResponse(
        prompt_id=str(payload.get("prompt_id") or row.prompt_id),
        case_id=str(payload.get("case_id") or row.case_id),
        prompt_text=str(payload.get("prompt_text") or ""),
        vars_json=dict(payload.get("vars_json") or {}),
        response_text=str(payload.get("response_text") or ""),
        assertions=list(payload.get("assertions") or []),
    )


@router.post("/runs/{eval_run_id}/cancel", response_model=GraiEvalRunCancelResponse)
async def cancel_grai_eval_run_route(
    eval_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    result = await cancel_grai_eval_run(db, eval_run_id=eval_run_id, tenant_id=user.tenant_id)
    if not result.found:
        raise ApiProblem(
            status=404,
            error_code=GRAI_EVAL_RUN_NOT_FOUND,
            detail="Grai eval run not found",
        )
    if result.applied:
        await write_audit_event(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            actor_type="user",
            action="grai_run.cancel",
            resource_type="grai_eval_run",
            resource_id=eval_run_id,
            detail={"reason": result.reason},
        )
    await db.commit()
    return GraiEvalRunCancelResponse(
        eval_run_id=eval_run_id,
        applied=result.applied,
        status=result.status,
        reason=result.reason,
    )
