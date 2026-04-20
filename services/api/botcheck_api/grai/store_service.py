from __future__ import annotations

import json as _json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_grai as grai_repo
from ..exceptions import GRAI_EVAL_SUITE_NAME_CONFLICT
from ..models import (
    GraiEvalCaseRow,
    GraiEvalPromptRow,
    GraiEvalResultRow,
    GraiEvalRunDestinationRow,
    GraiEvalRunRow,
    GraiEvalRunStatus,
    GraiEvalRunTerminalOutcome,
    GraiEvalSuiteRow,
)
from .service_models import (
    GraiCompiledSuite,
    GraiEvalRunCancelResult,
    GraiEvalRunDestinationSnapshot,
    GraiEvalResultWritePayload,
    GraiEvalRunSnapshot,
    GRAI_EVAL_DISPATCH_ERROR_PREFIX,
)



async def list_grai_eval_suites_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[GraiEvalSuiteRow]:
    return await grai_repo.list_grai_eval_suite_rows_for_tenant(db, tenant_id=tenant_id)


async def get_grai_eval_suite_for_tenant(
    db: AsyncSession,
    suite_id: str,
    tenant_id: str,
) -> GraiEvalSuiteRow | None:
    return await grai_repo.get_grai_eval_suite_row_for_tenant(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
    )


async def list_grai_eval_prompts_for_suite(
    db: AsyncSession,
    suite_id: str,
    tenant_id: str,
) -> list[GraiEvalPromptRow]:
    return await grai_repo.list_grai_eval_prompt_rows_for_suite(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
    )


async def list_grai_eval_cases_for_suite(
    db: AsyncSession,
    suite_id: str,
    tenant_id: str,
) -> list[GraiEvalCaseRow]:
    return await grai_repo.list_grai_eval_case_rows_for_suite(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
    )


async def get_grai_eval_suite_counts(
    db: AsyncSession,
    *,
    tenant_id: str,
    suite_ids: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    return await grai_repo.get_grai_eval_suite_counts(
        db,
        tenant_id=tenant_id,
        suite_ids=suite_ids,
    )


async def _assert_suite_name_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    suite_id: str | None = None,
) -> None:
    await grai_repo.assert_grai_eval_suite_name_available(
        db,
        tenant_id=tenant_id,
        name=name,
        suite_id=suite_id,
    )


async def _replace_suite_children(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
    payload: GraiCompiledSuite,
) -> tuple[list[str], list[str]]:
    return await grai_repo.replace_grai_eval_suite_children(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
        prompts=[
            {
                "label": prompt.label,
                "prompt_text": prompt.prompt_text,
                "metadata_json": dict(prompt.metadata_json),
            }
            for prompt in payload.prompts
        ],
        cases=[
            {
                "description": case.description,
                "vars_json": dict(case.vars_json),
                "assert_json": list(case.assert_json),
                "tags_json": list(case.tags_json),
                "metadata_json": dict(case.metadata_json),
                "import_threshold": case.import_threshold,
            }
            for case in payload.cases
        ],
    )


async def create_grai_eval_suite(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
    payload: GraiCompiledSuite,
) -> tuple[GraiEvalSuiteRow, list[str], list[str]]:
    await _assert_suite_name_available(db, tenant_id=tenant_id, name=payload.name)
    suite_id = f"gesuite_{uuid4().hex[:12]}"
    row = GraiEvalSuiteRow(
        suite_id=suite_id,
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        source_yaml=payload.source_yaml,
        metadata_json=dict(payload.metadata_json),
        created_by=actor_id,
        updated_by=actor_id,
        created_at=grai_repo.now_utc(),
        updated_at=grai_repo.now_utc(),
    )
    db.add(row)
    try:
        prompt_ids, case_ids = await _replace_suite_children(
            db,
            suite_id=suite_id,
            tenant_id=tenant_id,
            payload=payload,
        )
        await db.flush()
    except IntegrityError as exc:
        raise ValueError(GRAI_EVAL_SUITE_NAME_CONFLICT) from exc
    return row, prompt_ids, case_ids


async def update_grai_eval_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
    actor_id: str,
    payload: GraiCompiledSuite,
) -> tuple[GraiEvalSuiteRow, list[str], list[str]]:
    row = await get_grai_eval_suite_for_tenant(db, suite_id, tenant_id)
    if row is None:
        raise LookupError("Grai eval suite not found")
    await _assert_suite_name_available(db, tenant_id=tenant_id, name=payload.name, suite_id=suite_id)
    try:
        row.name = payload.name
        row.description = payload.description
        if payload.source_yaml is not None:
            row.source_yaml = payload.source_yaml
        row.metadata_json = dict(payload.metadata_json)
        row.updated_by = actor_id
        row.updated_at = grai_repo.now_utc()
        prompt_ids, case_ids = await _replace_suite_children(
            db,
            suite_id=suite_id,
            tenant_id=tenant_id,
            payload=payload,
        )
        await db.flush()
    except IntegrityError as exc:
        raise ValueError(GRAI_EVAL_SUITE_NAME_CONFLICT) from exc
    return row, prompt_ids, case_ids


async def delete_grai_eval_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
) -> bool:
    return await grai_repo.delete_grai_eval_suite_row_for_tenant(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
    )


async def create_grai_eval_run_snapshot(
    db: AsyncSession,
    *,
    tenant_id: str,
    suite_id: str,
    destinations: list[GraiEvalRunDestinationSnapshot],
    trigger_source: str,
    schedule_id: str | None,
    triggered_by: str | None,
    prompt_count: int,
    case_count: int,
) -> GraiEvalRunSnapshot:
    if not destinations:
        raise ValueError("destinations must contain at least one destination")
    primary_destination = destinations[0]
    row = GraiEvalRunRow(
        eval_run_id=f"gerun_{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        suite_id=suite_id,
        transport_profile_id=primary_destination.transport_profile_id,
        endpoint_at_start=primary_destination.endpoint_at_start,
        headers_at_start=dict(primary_destination.headers_at_start),
        direct_http_config_at_start=(
            dict(primary_destination.direct_http_config_at_start)
            if primary_destination.direct_http_config_at_start is not None
            else None
        ),
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        triggered_by=triggered_by,
        status=GraiEvalRunStatus.PENDING.value,
        terminal_outcome=None,
        prompt_count=prompt_count,
        case_count=case_count,
        total_pairs=prompt_count * case_count * len(destinations),
        dispatched_count=0,
        completed_count=0,
        failed_count=0,
        created_at=grai_repo.now_utc(),
        updated_at=grai_repo.now_utc(),
    )
    db.add(row)
    await db.flush()
    persisted_destinations: list[GraiEvalRunDestinationSnapshot] = []
    for destination in destinations:
        destination_row = GraiEvalRunDestinationRow(
            run_dest_id=f"grundest_{uuid4().hex[:12]}",
            eval_run_id=row.eval_run_id,
            tenant_id=tenant_id,
            destination_index=destination.destination_index,
            transport_profile_id=destination.transport_profile_id,
            label=destination.label,
            protocol=destination.protocol,
            endpoint_at_start=destination.endpoint_at_start,
            headers_at_start=dict(destination.headers_at_start),
            direct_http_config_at_start=(
                dict(destination.direct_http_config_at_start)
                if destination.direct_http_config_at_start is not None
                else None
            ),
            created_at=grai_repo.now_utc(),
            updated_at=grai_repo.now_utc(),
        )
        db.add(destination_row)
        persisted_destinations.append(
            GraiEvalRunDestinationSnapshot(
                destination_index=destination.destination_index,
                transport_profile_id=destination.transport_profile_id,
                label=destination.label,
                protocol=destination.protocol,
                endpoint_at_start=destination.endpoint_at_start,
                headers_at_start=dict(destination.headers_at_start),
                direct_http_config_at_start=(
                    dict(destination.direct_http_config_at_start)
                    if destination.direct_http_config_at_start is not None
                    else None
                ),
            )
        )
    await db.flush()
    return GraiEvalRunSnapshot(
        eval_run_id=row.eval_run_id,
        tenant_id=row.tenant_id,
        suite_id=row.suite_id,
        transport_profile_id=row.transport_profile_id,
        transport_profile_ids=[item.transport_profile_id for item in persisted_destinations],
        status=row.status,
        terminal_outcome=row.terminal_outcome,
        prompt_count=row.prompt_count,
        case_count=row.case_count,
        total_pairs=row.total_pairs,
        endpoint_at_start=row.endpoint_at_start,
        headers_at_start=dict(row.headers_at_start or {}),
        direct_http_config_at_start=(
            dict(row.direct_http_config_at_start) if row.direct_http_config_at_start is not None else None
        ),
        destinations=persisted_destinations,
        trigger_source=row.trigger_source,
        schedule_id=row.schedule_id,
        triggered_by=row.triggered_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_grai_eval_run_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> GraiEvalRunRow | None:
    return await grai_repo.get_grai_eval_run_row_for_tenant(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
    )


async def list_grai_eval_runs_for_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
    limit: int,
) -> list[GraiEvalRunRow]:
    return await grai_repo.list_grai_eval_run_rows_for_suite(
        db,
        suite_id=suite_id,
        tenant_id=tenant_id,
        limit=limit,
    )


async def list_grai_eval_run_destinations_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> list[GraiEvalRunDestinationSnapshot]:
    rows = await grai_repo.list_grai_eval_run_destination_rows_for_tenant(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
    )
    return [
        GraiEvalRunDestinationSnapshot(
            destination_index=row.destination_index,
            transport_profile_id=str(row.transport_profile_id or ""),
            label=row.label,
            protocol=row.protocol,
            endpoint_at_start=row.endpoint_at_start,
            headers_at_start=dict(row.headers_at_start or {}),
            direct_http_config_at_start=(
                dict(row.direct_http_config_at_start) if row.direct_http_config_at_start is not None else None
            ),
        )
        for row in rows
    ]


async def list_grai_eval_run_destinations_for_runs(
    db: AsyncSession,
    *,
    eval_run_ids: list[str],
    tenant_id: str,
) -> dict[str, list[GraiEvalRunDestinationSnapshot]]:
    if not eval_run_ids:
        return {}
    rows = await grai_repo.list_grai_eval_run_destination_rows_for_runs(
        db,
        eval_run_ids=eval_run_ids,
        tenant_id=tenant_id,
    )
    grouped: dict[str, list[GraiEvalRunDestinationSnapshot]] = {eval_run_id: [] for eval_run_id in eval_run_ids}
    for row in rows:
        grouped[row.eval_run_id].append(
            GraiEvalRunDestinationSnapshot(
                destination_index=row.destination_index,
                transport_profile_id=str(row.transport_profile_id or ""),
                label=row.label,
                protocol=row.protocol,
                endpoint_at_start=row.endpoint_at_start,
                headers_at_start=dict(row.headers_at_start or {}),
                direct_http_config_at_start=(
                    dict(row.direct_http_config_at_start)
                    if row.direct_http_config_at_start is not None
                    else None
                ),
            )
        )
    return grouped


async def get_grai_eval_result_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    eval_result_id: str,
    tenant_id: str,
) -> GraiEvalResultRow | None:
    return await grai_repo.get_grai_eval_result_row_for_tenant(
        db,
        eval_run_id=eval_run_id,
        eval_result_id=eval_result_id,
        tenant_id=tenant_id,
    )


async def cancel_grai_eval_run(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> GraiEvalRunCancelResult:
    row = await get_grai_eval_run_for_tenant(db, eval_run_id=eval_run_id, tenant_id=tenant_id)
    if row is None:
        return GraiEvalRunCancelResult(
            found=False,
            applied=False,
            status="unknown",
            reason="not_found",
        )
    if row.status == GraiEvalRunStatus.CANCELLED.value:
        return GraiEvalRunCancelResult(
            found=True,
            applied=False,
            status=row.status,
            reason="already_cancelled",
        )
    if row.status in {
        GraiEvalRunStatus.COMPLETE.value,
        GraiEvalRunStatus.FAILED.value,
    }:
        return GraiEvalRunCancelResult(
            found=True,
            applied=False,
            status=row.status,
            reason="already_terminal",
        )
    row = await grai_repo.cancel_grai_eval_run_row_for_tenant(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
    )
    if row is None or row.status != GraiEvalRunStatus.CANCELLED.value:
        # Concurrent transition: run reached a terminal state between the pre-check
        # and the repo mutation — treat as already_terminal rather than applied.
        return GraiEvalRunCancelResult(
            found=True,
            applied=False,
            status=row.status if row is not None else "unknown",
            reason="already_terminal",
        )
    return GraiEvalRunCancelResult(
        found=True,
        applied=True,
        status=row.status,
        reason="cancelled",
    )


async def list_grai_eval_pair_progress(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> dict[tuple[str, str, int], bool]:
    progress: dict[tuple[str, str, int], bool] = {}
    for prompt_id, case_id, destination_index, min_passed in await grai_repo.list_grai_eval_pair_progress_rows(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
    ):
        progress[(prompt_id, case_id, destination_index)] = (
            False if min_passed is None else not bool(min_passed)
        )
    return progress


async def replace_grai_eval_pair_results(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    suite_id: str,
    prompt_id: str,
    case_id: str,
    destination_index: int,
    rows: list[GraiEvalResultWritePayload],
) -> None:
    await grai_repo.replace_grai_eval_pair_result_rows(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
        suite_id=suite_id,
        prompt_id=prompt_id,
        case_id=case_id,
        destination_index=destination_index,
        rows=rows,
    )


async def set_grai_eval_run_progress(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    status: str,
    terminal_outcome: GraiEvalRunTerminalOutcome | None,
    dispatched_count: int,
    completed_count: int,
    failed_count: int,
) -> GraiEvalRunRow | None:
    return await grai_repo.set_grai_eval_run_progress_row(
        db,
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
        status=status,
        terminal_outcome=terminal_outcome,
        dispatched_count=dispatched_count,
        completed_count=completed_count,
        failed_count=failed_count,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filtered_result_query(
    *,
    eval_run_id: str,
    tenant_id: str,
    prompt_id: str | None = None,
    assertion_type: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    destination_index: int | None = None,
):
    stmt = (
        select(GraiEvalResultRow)
        .where(
            GraiEvalResultRow.eval_run_id == eval_run_id,
            GraiEvalResultRow.tenant_id == tenant_id,
        )
    )
    if prompt_id:
        stmt = stmt.where(GraiEvalResultRow.prompt_id == prompt_id)
    if assertion_type:
        stmt = stmt.where(GraiEvalResultRow.assertion_type == assertion_type)
    if tag:
        json_inner = _json.dumps(tag)[1:-1]  # encode as it appears inside a JSON array element
        pattern = f'%"{_escape_like(json_inner)}"%'
        stmt = stmt.where(cast(GraiEvalResultRow.tags_json, String).like(pattern, escape="\\"))
    if status == "passed":
        stmt = stmt.where(GraiEvalResultRow.passed.is_(True))
    elif status == "failed":
        stmt = stmt.where(GraiEvalResultRow.passed.is_(False))
    if destination_index is not None:
        stmt = stmt.where(GraiEvalResultRow.destination_index == destination_index)
    return stmt


async def list_grai_eval_results_page(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    prompt_id: str | None = None,
    assertion_type: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    destination_index: int | None = None,
    limit: int = 50,
    cursor_created_at: datetime | None = None,
    cursor_eval_result_id: str | None = None,
) -> tuple[list[dict[str, object]], datetime | None, str | None]:
    stmt = (
        select(
            GraiEvalResultRow.eval_result_id,
            GraiEvalResultRow.destination_index,
            GraiEvalRunDestinationRow.transport_profile_id,
            GraiEvalRunDestinationRow.label.label("destination_label"),
            GraiEvalResultRow.prompt_id,
            GraiEvalPromptRow.label.label("prompt_label"),
            GraiEvalResultRow.case_id,
            GraiEvalCaseRow.description.label("case_description"),
            GraiEvalResultRow.assertion_index,
            GraiEvalResultRow.assertion_type,
            GraiEvalResultRow.passed,
            GraiEvalResultRow.score,
            GraiEvalResultRow.threshold,
            GraiEvalResultRow.weight,
            GraiEvalResultRow.raw_value,
            GraiEvalResultRow.failure_reason,
            GraiEvalResultRow.latency_ms,
            GraiEvalResultRow.tags_json,
            GraiEvalResultRow.raw_s3_key,
            GraiEvalResultRow.created_at,
        )
        .select_from(GraiEvalResultRow)
        .join(
            GraiEvalPromptRow,
            (GraiEvalPromptRow.prompt_id == GraiEvalResultRow.prompt_id)
            & (GraiEvalPromptRow.tenant_id == tenant_id),
        )
        .join(
            GraiEvalCaseRow,
            (GraiEvalCaseRow.case_id == GraiEvalResultRow.case_id)
            & (GraiEvalCaseRow.tenant_id == tenant_id),
        )
        .outerjoin(
            GraiEvalRunDestinationRow,
            (GraiEvalRunDestinationRow.eval_run_id == GraiEvalResultRow.eval_run_id)
            & (GraiEvalRunDestinationRow.tenant_id == GraiEvalResultRow.tenant_id)
            & (GraiEvalRunDestinationRow.destination_index == GraiEvalResultRow.destination_index),
        )
        .where(
            GraiEvalResultRow.eval_run_id == eval_run_id,
            GraiEvalResultRow.tenant_id == tenant_id,
        )
    )
    if prompt_id:
        stmt = stmt.where(GraiEvalResultRow.prompt_id == prompt_id)
    if assertion_type:
        stmt = stmt.where(GraiEvalResultRow.assertion_type == assertion_type)
    if tag:
        json_inner = _json.dumps(tag)[1:-1]  # encode as it appears inside a JSON array element
        pattern = f'%"{_escape_like(json_inner)}"%'
        stmt = stmt.where(cast(GraiEvalResultRow.tags_json, String).like(pattern, escape="\\"))
    if status == "passed":
        stmt = stmt.where(GraiEvalResultRow.passed.is_(True))
    elif status == "failed":
        stmt = stmt.where(GraiEvalResultRow.passed.is_(False))
    if destination_index is not None:
        stmt = stmt.where(GraiEvalResultRow.destination_index == destination_index)
    if cursor_created_at is not None and cursor_eval_result_id is not None:
        stmt = stmt.where(
            or_(
                GraiEvalResultRow.created_at < cursor_created_at,
                and_(
                    GraiEvalResultRow.created_at == cursor_created_at,
                    GraiEvalResultRow.eval_result_id < cursor_eval_result_id,
                ),
            )
        )
    stmt = stmt.order_by(GraiEvalResultRow.created_at.desc(), GraiEvalResultRow.eval_result_id.desc()).limit(limit + 1)
    rows = (await db.execute(stmt)).all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = [
        {
            "eval_result_id": str(row.eval_result_id),
            "destination_index": int(row.destination_index) if row.destination_index is not None else None,
            "transport_profile_id": (
                str(row.transport_profile_id) if row.transport_profile_id is not None else None
            ),
            "destination_label": str(row.destination_label) if row.destination_label is not None else None,
            "prompt_id": str(row.prompt_id),
            "prompt_label": str(row.prompt_label),
            "case_id": str(row.case_id),
            "case_description": row.case_description,
            "assertion_index": int(row.assertion_index),
            "assertion_type": str(row.assertion_type),
            "passed": bool(row.passed),
            "score": float(row.score) if row.score is not None else None,
            "threshold": float(row.threshold) if row.threshold is not None else None,
            "weight": float(row.weight),
            "raw_value": str(row.raw_value) if row.raw_value is not None else None,
            "failure_reason": (
                str(row.failure_reason) if row.failure_reason is not None else None
            ),
            "latency_ms": int(row.latency_ms) if row.latency_ms is not None else None,
            "tags_json": list(row.tags_json or []),
            "raw_s3_key": str(row.raw_s3_key) if row.raw_s3_key is not None else None,
            "created_at": row.created_at,
        }
        for row in page_rows
    ]
    if not has_more or not page_rows:
        return items, None, None
    last_row = page_rows[-1]
    return items, last_row.created_at, str(last_row.eval_result_id)


async def build_grai_eval_report(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    prompt_id: str | None = None,
    assertion_type: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    destination_index: int | None = None,
) -> dict[str, object]:
    filtered = _filtered_result_query(
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
        prompt_id=prompt_id,
        assertion_type=assertion_type,
        tag=tag,
        status=status,
        destination_index=destination_index,
    ).subquery()

    summary_stmt = select(
        func.count(filtered.c.eval_result_id),
        func.coalesce(func.sum(case((filtered.c.passed.is_(True), 1), else_=0)), 0),
        func.coalesce(func.sum(case((filtered.c.passed.is_(False), 1), else_=0)), 0),
    )
    total_results, passed_results, failed_results = (await db.execute(summary_stmt)).one()

    breakdown_stmt = (
        select(
            filtered.c.assertion_type,
            func.count(filtered.c.eval_result_id),
            func.coalesce(func.sum(case((filtered.c.passed.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(case((filtered.c.passed.is_(False), 1), else_=0)), 0),
        )
        .group_by(filtered.c.assertion_type)
        .order_by(func.count(filtered.c.eval_result_id).desc(), filtered.c.assertion_type.asc())
    )
    assertion_type_breakdown = [
        {
            "assertion_type": str(row[0]),
            "total_results": int(row[1]),
            "passed_results": int(row[2]),
            "failed_results": int(row[3]),
        }
        for row in (await db.execute(breakdown_stmt)).all()
    ]

    failed_filtered = (
        _filtered_result_query(
            eval_run_id=eval_run_id,
            tenant_id=tenant_id,
            prompt_id=prompt_id,
            assertion_type=assertion_type,
            tag=tag,
            status="failed",
            destination_index=destination_index,
        ).subquery()
    )
    prompt_stmt = (
        select(
            failed_filtered.c.prompt_id,
            GraiEvalPromptRow.label,
            func.count(failed_filtered.c.eval_result_id),
            func.count(func.distinct(failed_filtered.c.case_id)),
        )
        .select_from(failed_filtered)
        .join(
            GraiEvalPromptRow,
            (GraiEvalPromptRow.prompt_id == failed_filtered.c.prompt_id)
            & (GraiEvalPromptRow.tenant_id == failed_filtered.c.tenant_id),
        )
        .group_by(failed_filtered.c.prompt_id, GraiEvalPromptRow.label)
        .order_by(func.count(failed_filtered.c.eval_result_id).desc(), GraiEvalPromptRow.label.asc())
        .limit(10)
    )
    failing_prompt_variants = [
        {
            "prompt_id": str(row[0]),
            "prompt_label": str(row[1]),
            "failure_count": int(row[2]),
            "failed_pairs": int(row[3]),
        }
        for row in (await db.execute(prompt_stmt)).all()
    ]

    failed_tag_rows = (
        await db.execute(
            select(
                failed_filtered.c.prompt_id,
                failed_filtered.c.case_id,
                failed_filtered.c.tags_json,
            )
        )
    ).all()
    tag_counts: dict[str, int] = {}
    tag_pairs: dict[str, set[tuple[str, str]]] = {}
    for prompt_value, case_value, tags_json in failed_tag_rows:
        for item in list(tags_json or []):
            tag_name = str(item).strip()
            if not tag_name:
                continue
            tag_counts[tag_name] = tag_counts.get(tag_name, 0) + 1
            tag_pairs.setdefault(tag_name, set()).add((str(prompt_value), str(case_value)))
    tag_failure_clusters = [
        {
            "tag": tag_name,
            "failure_count": count,
            "failed_pairs": len(tag_pairs.get(tag_name, set())),
        }
        for tag_name, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:10]

    exemplar_stmt = (
        select(
            failed_filtered.c.eval_result_id,
            failed_filtered.c.destination_index,
            GraiEvalRunDestinationRow.transport_profile_id,
            GraiEvalRunDestinationRow.label.label("destination_label"),
            failed_filtered.c.prompt_id,
            GraiEvalPromptRow.label.label("prompt_label"),
            failed_filtered.c.case_id,
            GraiEvalCaseRow.description.label("case_description"),
            failed_filtered.c.assertion_index,
            failed_filtered.c.assertion_type,
            failed_filtered.c.passed,
            failed_filtered.c.score,
            failed_filtered.c.threshold,
            failed_filtered.c.weight,
            failed_filtered.c.raw_value,
            failed_filtered.c.failure_reason,
            failed_filtered.c.latency_ms,
            failed_filtered.c.tags_json,
            failed_filtered.c.raw_s3_key,
            failed_filtered.c.created_at,
        )
        .select_from(failed_filtered)
        .join(
            GraiEvalPromptRow,
            (GraiEvalPromptRow.prompt_id == failed_filtered.c.prompt_id)
            & (GraiEvalPromptRow.tenant_id == failed_filtered.c.tenant_id),
        )
        .join(
            GraiEvalCaseRow,
            (GraiEvalCaseRow.case_id == failed_filtered.c.case_id)
            & (GraiEvalCaseRow.tenant_id == failed_filtered.c.tenant_id),
        )
        .outerjoin(
            GraiEvalRunDestinationRow,
            (GraiEvalRunDestinationRow.eval_run_id == failed_filtered.c.eval_run_id)
            & (GraiEvalRunDestinationRow.tenant_id == failed_filtered.c.tenant_id)
            & (GraiEvalRunDestinationRow.destination_index == failed_filtered.c.destination_index),
        )
        .order_by(failed_filtered.c.created_at.desc(), failed_filtered.c.eval_result_id.desc())
        .limit(10)
    )
    exemplar_failures = [
        {
            "eval_result_id": str(row[0]),
            "destination_index": int(row[1]) if row[1] is not None else None,
            "transport_profile_id": str(row[2]) if row[2] is not None else None,
            "destination_label": str(row.destination_label) if row.destination_label is not None else None,
            "prompt_id": str(row[4]),
            "prompt_label": str(row.prompt_label),
            "case_id": str(row[6]),
            "case_description": row.case_description,
            "assertion_index": int(row[8]),
            "assertion_type": str(row[9]),
            "passed": bool(row[10]),
            "score": float(row[11]) if row[11] is not None else None,
            "threshold": float(row[12]) if row[12] is not None else None,
            "weight": float(row[13]),
            "raw_value": str(row[14]) if row[14] is not None else None,
            "failure_reason": str(row[15]) if row[15] is not None else None,
            "latency_ms": int(row[16]) if row[16] is not None else None,
            "tags_json": list(row[17] or []),
            "raw_s3_key": str(row[18]) if row[18] is not None else None,
            "created_at": row[19],
        }
        for row in (await db.execute(exemplar_stmt)).all()
    ]

    return {
        "total_results": int(total_results or 0),
        "passed_results": int(passed_results or 0),
        "failed_results": int(failed_results or 0),
        "assertion_type_breakdown": assertion_type_breakdown,
        "failing_prompt_variants": failing_prompt_variants,
        "tag_failure_clusters": tag_failure_clusters,
        "exemplar_failures": exemplar_failures,
    }


def _is_dispatch_error_failure_reason(reason: str | None) -> bool:
    return bool(reason and reason.startswith(GRAI_EVAL_DISPATCH_ERROR_PREFIX))


async def build_grai_eval_matrix(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    suite_id: str,
    destinations: list[GraiEvalRunDestinationSnapshot],
) -> dict[str, object]:
    prompts = await list_grai_eval_prompts_for_suite(db, suite_id=suite_id, tenant_id=tenant_id)
    cases = await list_grai_eval_cases_for_suite(db, suite_id=suite_id, tenant_id=tenant_id)
    result_rows = (
        await db.execute(
            select(
                GraiEvalResultRow.eval_result_id,
                GraiEvalResultRow.prompt_id,
                GraiEvalResultRow.case_id,
                GraiEvalResultRow.destination_index,
                GraiEvalResultRow.assertion_index,
                GraiEvalResultRow.assertion_type,
                GraiEvalResultRow.passed,
                GraiEvalResultRow.failure_reason,
                GraiEvalResultRow.latency_ms,
            )
            .where(
                GraiEvalResultRow.eval_run_id == eval_run_id,
                GraiEvalResultRow.tenant_id == tenant_id,
            )
            .order_by(
                GraiEvalResultRow.prompt_id.asc(),
                GraiEvalResultRow.case_id.asc(),
                GraiEvalResultRow.destination_index.asc(),
                GraiEvalResultRow.assertion_index.asc(),
                GraiEvalResultRow.created_at.asc(),
                GraiEvalResultRow.eval_result_id.asc(),
            )
        )
    ).all()

    destination_by_index = {
        destination.destination_index: destination for destination in destinations
    }
    cells_by_key: dict[tuple[str, str, int], dict[str, object]] = {}
    for row in result_rows:
        key = (str(row.prompt_id), str(row.case_id), int(row.destination_index))
        destination = destination_by_index.get(int(row.destination_index))
        if destination is None:
            continue
        cell = cells_by_key.setdefault(
            key,
            {
                "destination_index": int(row.destination_index),
                "transport_profile_id": destination.transport_profile_id,
                "destination_label": destination.label,
                "artifact_eval_result_id": str(row.eval_result_id),
                "response_snippet": None,
                "latency_ms": None,
                "assertion_results": [],
            },
        )
        if cell["latency_ms"] is None and row.latency_ms is not None:
            cell["latency_ms"] = int(row.latency_ms)
        assertion_results = list(cell["assertion_results"])
        assertion_results.append(
            {
                "assertion_index": int(row.assertion_index),
                "assertion_type": str(row.assertion_type),
                "passed": bool(row.passed),
                "failure_reason": str(row.failure_reason) if row.failure_reason is not None else None,
            }
        )
        cell["assertion_results"] = assertion_results

    for cell in cells_by_key.values():
        assertion_results = list(cell["assertion_results"])
        failed_assertions = [item for item in assertion_results if not bool(item["passed"])]
        if failed_assertions:
            # Classify as error only when every *failed* assertion was produced by a
            # dispatch exception — not when some passed and some failed normally.
            if all(
                _is_dispatch_error_failure_reason(item["failure_reason"]) for item in failed_assertions
            ):
                cell["status"] = "error"
            else:
                cell["status"] = "failed"
        else:
            cell["status"] = "passed"

    # Emit "pending" placeholder cells for (prompt, case, destination) triples that
    # have no result rows yet (run still in progress). This keeps len(row.cells) ==
    # len(destinations) as an invariant the UI can rely on.
    for prompt in prompts:
        for case_row in cases:
            for destination in destinations:
                key = (str(prompt.prompt_id), str(case_row.case_id), destination.destination_index)
                if key not in cells_by_key:
                    cells_by_key[key] = {
                        "destination_index": destination.destination_index,
                        "transport_profile_id": destination.transport_profile_id,
                        "destination_label": destination.label,
                        "artifact_eval_result_id": None,
                        "response_snippet": None,
                        "latency_ms": None,
                        "assertion_results": [],
                        "status": "pending",
                    }

    total_pairs_per_destination = len(prompts) * len(cases)
    destination_summaries: list[dict[str, object]] = []
    for destination in destinations:
        passed = 0
        failed = 0
        errors = 0
        latency_values: list[int] = []
        for prompt in prompts:
            for case_row in cases:
                cell = cells_by_key[
                    (str(prompt.prompt_id), str(case_row.case_id), destination.destination_index)
                ]
                status = str(cell["status"])
                if status == "passed":
                    passed += 1
                elif status == "error":
                    errors += 1
                else:
                    failed += 1
                if cell["latency_ms"] is not None:
                    latency_values.append(int(cell["latency_ms"]))
        destination_summaries.append(
            {
                "destination_index": destination.destination_index,
                "transport_profile_id": destination.transport_profile_id,
                "label": destination.label,
                "protocol": destination.protocol,
                "pass_rate": (passed / total_pairs_per_destination) if total_pairs_per_destination else 0.0,
                "total_pairs": total_pairs_per_destination,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "avg_latency_ms": (
                    sum(latency_values) / len(latency_values) if latency_values else None
                ),
            }
        )

    prompt_groups: list[dict[str, object]] = []
    for prompt in prompts:
        rows: list[dict[str, object]] = []
        for case_row in cases:
            cells = [
                cells_by_key[(str(prompt.prompt_id), str(case_row.case_id), destination.destination_index)]
                for destination in destinations
            ]
            rows.append(
                {
                    "prompt_id": str(prompt.prompt_id),
                    "case_id": str(case_row.case_id),
                    "case_description": case_row.description,
                    "tags_json": list(case_row.tags_json or []),
                    "cells": cells,
                }
            )
        prompt_groups.append(
            {
                "prompt_id": str(prompt.prompt_id),
                "prompt_label": prompt.label,
                "prompt_text": prompt.prompt_text,
                "rows": rows,
            }
        )

    return {
        "destinations": destination_summaries,
        "prompt_groups": prompt_groups,
    }
