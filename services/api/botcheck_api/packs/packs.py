from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin.quota_service import assert_tenant_quota_available
from ..audit import write_audit_event
from ..auth import UserContext, get_service_caller, require_admin, require_viewer
from ..auth.core import get_tenant_row
from ..config import settings
from ..database import get_db
from ..exceptions import (
    AI_SCENARIOS_DISABLED,
    AI_SCENARIO_NOT_FOUND,
    ApiProblem,
    DESTINATION_INACTIVE,
    DESTINATION_NOT_FOUND,
    DESTINATIONS_DISABLED,
    JOB_QUEUE_UNAVAILABLE,
    PACK_NOT_FOUND,
    PACK_RUN_NOT_FOUND,
    SCENARIO_PACKS_DISABLED,
)
from ..models import PackRunRow, PackRunState
from ..runs.service_lifecycle import create_run_internal
from .pack_schemas import (
    ExecutionMode,
    InternalDispatchPackRunResponse,
    PackChildRunCreate,
    PackRunStartRequest,
    PackRunStartResponse,
    ScenarioPackDetailResponse,
    ScenarioPackItemResponse,
    ScenarioPackItemUpsert,
    ScenarioPackSummaryResponse,
    ScenarioPackUpsert,
)
from .service import (
    StoredScenarioPack,
    create_or_replace_scenario_pack,
    create_pack_run_snapshot,
    delete_scenario_pack,
    get_active_pack_run_by_idempotency,
    get_bot_destination,
    get_pack_run_for_tenant,
    get_scenario_pack,
    has_active_pack_runs_for_pack,
    list_pack_run_items,
    list_scenario_packs,
    start_pack_run_dispatch,
)
from ..scenarios.store_service import get_ai_scenario, get_scenario

router = APIRouter()
logger = logging.getLogger("botcheck.api.packs")


def _require_packs_enabled() -> None:
    if not settings.feature_packs_enabled:
        raise ApiProblem(
            status=503,
            error_code=SCENARIO_PACKS_DISABLED,
            detail="Scenario packs are disabled",
        )


async def _resolve_pack_item_scenario_ids(
    *,
    db: AsyncSession,
    tenant_id: str,
    body: ScenarioPackUpsert,
) -> list[str]:
    if not body.items:
        return body.scenario_ids

    resolved: list[str] = []
    for item in body.items:
        if item.ai_scenario_id is not None:
            if not settings.feature_ai_scenarios_enabled:
                raise ApiProblem(
                    status=503,
                    error_code=AI_SCENARIOS_DISABLED,
                    detail="AI scenarios are disabled",
                )
            ai_scenario = await get_ai_scenario(
                db,
                ai_scenario_id=item.ai_scenario_id,
                tenant_id=tenant_id,
            )
            if ai_scenario is None:
                raise ApiProblem(
                    status=404,
                    error_code=AI_SCENARIO_NOT_FOUND,
                    detail="AI scenario not found",
                )
            if item.scenario_id is not None and item.scenario_id != ai_scenario.scenario_id:
                raise HTTPException(
                    status_code=422,
                    detail="scenario_id does not match ai_scenario_id",
                )
            resolved.append(ai_scenario.scenario_id)
            continue

        assert item.scenario_id is not None
        resolved.append(item.scenario_id)
    return resolved


def _summary_response(stored_pack: StoredScenarioPack) -> ScenarioPackSummaryResponse:
    return ScenarioPackSummaryResponse(
        pack_id=stored_pack.pack_id,
        name=stored_pack.name,
        description=stored_pack.description,
        tags=stored_pack.tags,
        execution_mode=ExecutionMode(stored_pack.execution_mode),
        scenario_count=len(stored_pack.items),
    )


def _detail_response(stored_pack: StoredScenarioPack) -> ScenarioPackDetailResponse:
    return ScenarioPackDetailResponse(
        **_summary_response(stored_pack).model_dump(),
        items=[
            ScenarioPackItemResponse(
                scenario_id=item.scenario_id,
                ai_scenario_id=item.ai_scenario_id,
                order_index=item.order_index,
            )
            for item in stored_pack.items
        ],
    )


def _is_pack_run_terminal(state: str) -> bool:
    return state in {
        PackRunState.COMPLETE.value,
        PackRunState.PARTIAL.value,
        PackRunState.FAILED.value,
        PackRunState.CANCELLED.value,
    }


def _normalize_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) > 128:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be 128 characters or fewer",
        )
    return key


async def _validate_pack_destination_for_tenant(
    *,
    db: AsyncSession,
    tenant_id: str,
    destination_id: str | None,
    transport_profile_id: str | None,
) -> str | None:
    if (
        destination_id is not None
        and transport_profile_id is not None
        and destination_id != transport_profile_id
    ):
        raise HTTPException(status_code=422, detail="destination_id does not match transport_profile_id")
    resolved_destination_id = transport_profile_id or destination_id
    if resolved_destination_id is None:
        return None
    if not settings.feature_destinations_enabled:
        raise ApiProblem(
            status=503,
            error_code=DESTINATIONS_DISABLED,
            detail="Destinations are disabled",
        )
    destination = await get_bot_destination(db, resolved_destination_id, tenant_id)
    if destination is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Destination not found",
        )
    if not destination.is_active:
        raise ApiProblem(
            status=422,
            error_code=DESTINATION_INACTIVE,
            detail="Destination is inactive",
        )
    return resolved_destination_id


def _finalize_pack_run_if_all_items_terminal(pack_run: PackRunRow) -> None:
    if pack_run.completed < pack_run.total_scenarios:
        return
    if pack_run.state == PackRunState.CANCELLED.value:
        pack_run.gate_outcome = "cancelled"
        return
    if pack_run.blocked > 0:
        pack_run.state = PackRunState.PARTIAL.value
        pack_run.gate_outcome = "blocked"
        return
    if pack_run.failed > 0:
        pack_run.state = PackRunState.FAILED.value
        pack_run.gate_outcome = "blocked"
        return
    pack_run.state = PackRunState.COMPLETE.value
    pack_run.gate_outcome = "passed"


async def _mark_pack_item_failed(
    *,
    item,
    pack_run: PackRunRow,
    error_code: str,
    error_detail: str,
) -> None:
    item.state = "failed"
    item.error_code = error_code
    item.error_detail = error_detail
    pack_run.failed += 1
    pack_run.completed += 1
    _finalize_pack_run_if_all_items_terminal(pack_run)


async def _dispatch_pending_pack_items(
    *,
    request: Request,
    db: AsyncSession,
    pack_run: PackRunRow,
) -> tuple[int, int]:
    item_rows = await list_pack_run_items(db, pack_run_id=pack_run.pack_run_id)
    pending_items = [item for item in item_rows if item.state == "pending"]
    dispatched_count = 0
    failed_count = 0

    for index, item in enumerate(pending_items):
        await db.refresh(pack_run, attribute_names=["state"])
        if pack_run.state == PackRunState.CANCELLED.value:
            remaining_pending = sum(
                1 for pending_item in pending_items[index:] if pending_item.state == "pending"
            )
            logger.info(
                "pack_dispatch_stopped_cancelled",
                extra={
                    "pack_run_id": pack_run.pack_run_id,
                    "remaining_pending": remaining_pending,
                },
            )
            break

        scenario_data = await get_scenario(db, item.scenario_id, pack_run.tenant_id)
        if scenario_data is None:
            await _mark_pack_item_failed(
                item=item,
                pack_run=pack_run,
                error_code="scenario_version_mismatch",
                error_detail="Scenario missing after pack snapshot",
            )
            failed_count += 1
            await db.commit()
            continue
        _, current_version_hash = scenario_data
        if current_version_hash != item.scenario_version_hash:
            await _mark_pack_item_failed(
                item=item,
                pack_run=pack_run,
                error_code="scenario_version_mismatch",
                error_detail=(
                    "Scenario version hash changed after pack snapshot "
                    f"({item.scenario_version_hash} -> {current_version_hash})"
                ),
            )
            failed_count += 1
            await db.commit()
            continue

        trigger_source = (
            "scheduled"
            if str(pack_run.trigger_source).strip().lower() == "scheduled"
            else "pack"
        )
        try:
            child_run = await create_run_internal(
                request=request,
                body=PackChildRunCreate(
                    scenario_id=item.scenario_id,
                    bot_endpoint=pack_run.dial_target,
                    destination_id=pack_run.destination_id,
                    dial_target=pack_run.dial_target,
                    transport_profile_id=pack_run.transport_profile_id,
                ),
                tenant_id=pack_run.tenant_id,
                trigger_source=trigger_source,
                triggered_by=pack_run.triggered_by,
                schedule_id=pack_run.schedule_id,
                db=db,
                pack_run_id=pack_run.pack_run_id,
                auto_commit=False,
            )
        except ApiProblem as exc:
            await _mark_pack_item_failed(
                item=item,
                pack_run=pack_run,
                error_code=exc.error_code,
                error_detail=f"API {exc.status}: {exc.detail}",
            )
            failed_count += 1
            logger.warning(
                "pack_dispatch_item_api_problem",
                extra={
                    "pack_run_id": pack_run.pack_run_id,
                    "scenario_id": item.scenario_id,
                    "status": exc.status,
                    "error_code": exc.error_code,
                    "detail": exc.detail,
                },
            )
            await db.commit()
            continue
        except HTTPException as exc:
            await _mark_pack_item_failed(
                item=item,
                pack_run=pack_run,
                error_code="run_dispatch_failed",
                error_detail=f"HTTP {exc.status_code}: {exc.detail}",
            )
            failed_count += 1
            logger.warning(
                "pack_dispatch_item_http_error",
                extra={
                    "pack_run_id": pack_run.pack_run_id,
                    "scenario_id": item.scenario_id,
                    "status": exc.status_code,
                    "detail": str(exc.detail),
                },
            )
            await db.commit()
            continue
        except Exception as exc:
            await _mark_pack_item_failed(
                item=item,
                pack_run=pack_run,
                error_code="run_dispatch_failed",
                error_detail=f"{type(exc).__name__}: {exc}",
            )
            failed_count += 1
            logger.warning(
                "pack_dispatch_item_error",
                extra={
                    "pack_run_id": pack_run.pack_run_id,
                    "scenario_id": item.scenario_id,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            await db.commit()
            continue

        item.state = "dispatched"
        item.run_id = child_run.run_id
        item.error_code = None
        item.error_detail = None
        pack_run.dispatched += 1
        dispatched_count += 1
        await db.commit()

    return dispatched_count, failed_count


@router.get("/", response_model=list[ScenarioPackSummaryResponse])
async def list_packs(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    packs = await list_scenario_packs(db, user.tenant_id)
    return [_summary_response(pack) for pack in packs]


@router.post("/", response_model=ScenarioPackDetailResponse, status_code=201)
async def create_pack(
    body: ScenarioPackUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_packs_enabled()
    tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
    await assert_tenant_quota_available(
        db,
        tenant=tenant,
        tenant_id=user.tenant_id,
        quota_name="max_packs",
    )
    try:
        scenario_ids = await _resolve_pack_item_scenario_ids(
            db=db,
            tenant_id=user.tenant_id,
            body=body,
        )
        pack = await create_or_replace_scenario_pack(
            db,
            tenant_id=user.tenant_id,
            name=body.name,
            description=body.description,
            tags=body.tags,
            execution_mode=body.execution_mode.value,
            scenario_ids=scenario_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise ApiProblem(
            status=404,
            error_code=PACK_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="pack.create",
        resource_type="pack",
        resource_id=pack.pack_id,
        detail={
            "name": pack.name,
            "scenario_count": len(pack.items),
            "execution_mode": pack.execution_mode,
        },
    )
    await db.commit()
    return _detail_response(pack)


@router.get("/{pack_id}", response_model=ScenarioPackDetailResponse)
async def get_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    pack = await get_scenario_pack(db, pack_id, user.tenant_id)
    if pack is None:
        raise ApiProblem(
            status=404,
            error_code=PACK_NOT_FOUND,
            detail="Pack not found",
        )
    return _detail_response(pack)


@router.put("/{pack_id}", response_model=ScenarioPackDetailResponse)
async def update_pack(
    pack_id: str,
    body: ScenarioPackUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_packs_enabled()
    try:
        scenario_ids = await _resolve_pack_item_scenario_ids(
            db=db,
            tenant_id=user.tenant_id,
            body=body,
        )
        pack = await create_or_replace_scenario_pack(
            db,
            pack_id=pack_id,
            tenant_id=user.tenant_id,
            name=body.name,
            description=body.description,
            tags=body.tags,
            execution_mode=body.execution_mode.value,
            scenario_ids=scenario_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise ApiProblem(
            status=404,
            error_code=PACK_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="pack.update",
        resource_type="pack",
        resource_id=pack.pack_id,
        detail={
            "name": pack.name,
            "scenario_count": len(pack.items),
            "execution_mode": pack.execution_mode,
        },
    )
    await db.commit()
    return _detail_response(pack)


@router.delete("/{pack_id}", status_code=204)
async def delete_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_packs_enabled()
    if await has_active_pack_runs_for_pack(
        db,
        pack_id=pack_id,
        tenant_id=user.tenant_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete pack with active pack runs",
        )
    deleted = await delete_scenario_pack(db, pack_id, user.tenant_id)
    if not deleted:
        raise ApiProblem(
            status=404,
            error_code=PACK_NOT_FOUND,
            detail="Pack not found",
        )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="pack.delete",
        resource_type="pack",
        resource_id=pack_id,
        detail={},
    )
    await db.commit()


@router.post("/{pack_id}/run", response_model=PackRunStartResponse, status_code=202)
async def run_pack(
    pack_id: str,
    request: Request,
    body: PackRunStartRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_packs_enabled()
    transport_profile_id = body.transport_profile_id if body is not None else None
    dial_target = body.dial_target or body.bot_endpoint if body is not None else None
    destination_id = await _validate_pack_destination_for_tenant(
        db=db,
        tenant_id=user.tenant_id,
        destination_id=body.destination_id if body is not None else None,
        transport_profile_id=transport_profile_id,
    )
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Job queue unavailable",
        )
    idempotency_key = _normalize_idempotency_key(request.headers.get("Idempotency-Key"))
    if idempotency_key is not None:
        existing = await get_active_pack_run_by_idempotency(
            db,
            tenant_id=user.tenant_id,
            pack_id=pack_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.destination_id != destination_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency-Key already used with a different destination_id "
                        "for this active pack run"
                    ),
                )
            if existing.dial_target != dial_target:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency-Key already used with a different dial_target "
                        "for this active pack run"
                    ),
                )
            return PackRunStartResponse(
                pack_run_id=existing.pack_run_id,
                state=existing.state,
                total_scenarios=existing.total_scenarios,
                destination_id=existing.destination_id,
                transport_profile_id=existing.transport_profile_id,
                dial_target=existing.dial_target,
            )

    try:
        snapshot = await create_pack_run_snapshot(
            db,
            pack_id=pack_id,
            tenant_id=user.tenant_id,
            destination_id=destination_id,
            transport_profile_id=destination_id,
            dial_target=dial_target,
            trigger_source="manual",
            schedule_id=None,
            triggered_by=user.sub,
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await arq_pool.enqueue_job(
            "dispatch_pack_run",
            payload={
                "pack_run_id": snapshot.pack_run_id,
                "tenant_id": snapshot.tenant_id,
            },
            _queue_name="arq:scheduler",
        )
    except Exception:
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Failed to enqueue pack dispatcher job",
        )

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="pack.run.enqueued",
        resource_type="pack_run",
        resource_id=snapshot.pack_run_id,
        detail={
            "pack_id": snapshot.pack_id,
            "total_scenarios": snapshot.total_scenarios,
            "trigger_source": "manual",
            "idempotency_key": idempotency_key,
            "transport_profile_id": snapshot.transport_profile_id,
            "dial_target": snapshot.dial_target,
        },
    )
    await db.commit()
    return PackRunStartResponse(
        pack_run_id=snapshot.pack_run_id,
        state=snapshot.state,
        total_scenarios=snapshot.total_scenarios,
        destination_id=snapshot.destination_id,
        transport_profile_id=snapshot.transport_profile_id,
        dial_target=snapshot.dial_target,
    )


@router.post(
    "/internal/{pack_run_id}/dispatch",
    response_model=InternalDispatchPackRunResponse,
)
async def internal_dispatch_pack_run(
    pack_run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    _require_packs_enabled()
    if caller != "scheduler":
        raise HTTPException(status_code=403, detail="Only scheduler may dispatch pack runs")

    dispatch = await start_pack_run_dispatch(
        db,
        pack_run_id=pack_run_id,
    )
    if not dispatch.found:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )

    pack_run = await get_pack_run_for_tenant(
        db,
        pack_run_id=pack_run_id,
        tenant_id=dispatch.tenant_id or settings.tenant_id,
    )
    if pack_run is None:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )

    dispatched_count = 0
    failed_count = 0
    reason = dispatch.reason
    if not _is_pack_run_terminal(pack_run.state):
        dispatched_count, failed_count = await _dispatch_pending_pack_items(
            request=request,
            db=db,
            pack_run=pack_run,
        )
        if not dispatch.applied:
            if dispatched_count > 0 or failed_count > 0:
                reason = "dispatch_progressed"
            else:
                reason = "no_pending_items"

    if dispatch.applied:
        await write_audit_event(
            db,
            tenant_id=dispatch.tenant_id or settings.tenant_id,
            actor_id="scheduler",
            actor_type="service",
            action="pack.dispatch.started",
            resource_type="pack_run",
            resource_id=pack_run_id,
            detail={"state": dispatch.state},
        )
    if dispatched_count > 0 or failed_count > 0:
        await write_audit_event(
            db,
            tenant_id=dispatch.tenant_id or settings.tenant_id,
            actor_id="scheduler",
            actor_type="service",
            action="pack.dispatch.progress",
            resource_type="pack_run",
            resource_id=pack_run_id,
            detail={
                "state": pack_run.state,
                "dispatched": dispatched_count,
                "failed": failed_count,
            },
        )
    await db.commit()

    return InternalDispatchPackRunResponse(
        pack_run_id=pack_run_id,
        found=dispatch.found,
        applied=dispatch.applied,
        state=pack_run.state,
        reason=reason,
    )
