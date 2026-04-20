from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..admin.quota_service import assert_tenant_quota_available
from ..auth import UserContext, get_service_caller, require_editor, require_viewer
from ..auth.core import get_tenant_row
from ..audit import write_audit_event
from ..config import settings
from ..database import get_db
from ..exceptions import (
    AI_SCENARIOS_DISABLED,
    ApiProblem,
    DESTINATION_INACTIVE,
    DESTINATION_NOT_FOUND,
    DESTINATIONS_DISABLED,
    PACK_NOT_FOUND,
    SCENARIO_PACKS_DISABLED,
    SCHEDULE_NOT_FOUND,
)
from ..models import PlaygroundMode, RetentionProfile, RunState, RunType, ScheduleRow, ScheduleTargetType
from ..repo_runs import list_run_rows_for_schedule
from .runs import RunCreate
from .service_lifecycle import create_run_internal as _create_run_internal
from .service_models import RunResponse
from .service_state import deserialize_scores, normalize_cache_status
from ..packs.service import create_pack_run_snapshot, get_bot_destination, get_scenario_pack
from ..scenarios.store_service import get_ai_scenario, get_scenario
from ..scheduling import (
    compute_next_run_at,
    compute_next_run_occurrences,
    normalize_cron_expr,
    normalize_timezone,
)
from .store_service import (
    get_schedule_for_tenant,
    list_due_schedules,
    list_schedules as list_schedule_rows,
    store_schedule,
)

router = APIRouter()
logger = logging.getLogger("botcheck.api.schedules")


class MisfirePolicy(str, Enum):
    SKIP = "skip"
    RUN_ONCE = "run_once"


class ScheduleCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    target_type: ScheduleTargetType = ScheduleTargetType.SCENARIO
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    pack_id: str | None = None
    cron_expr: str
    timezone: str | None = None
    active: bool = True
    retry_on_failure: bool = False
    misfire_policy: MisfirePolicy = MisfirePolicy.SKIP
    config_overrides: dict[str, Any] | None = None


class SchedulePatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    target_type: ScheduleTargetType | None = None
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    pack_id: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    active: bool | None = None
    retry_on_failure: bool | None = None
    misfire_policy: MisfirePolicy | None = None
    config_overrides: dict[str, Any] | None = None


class ScheduleResponse(BaseModel):
    schedule_id: str
    name: str | None = None
    target_type: ScheduleTargetType
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    pack_id: str | None = None
    active: bool
    cron_expr: str
    timezone: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_run_outcome: str | None = None
    retry_on_failure: bool
    consecutive_failures: int
    misfire_policy: MisfirePolicy
    config_overrides: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DispatchDueRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


class DispatchDueResponse(BaseModel):
    checked: int
    dispatched: int
    throttled: int
    failed: int
    now: datetime


class SchedulePreviewRequest(BaseModel):
    cron_expr: str
    timezone: str | None = None
    count: int = Field(default=5, ge=1, le=500)


class SchedulePreviewResponse(BaseModel):
    cron_expr: str
    timezone: str
    occurrences: list[datetime]


def _schedule_ai_scenario_id(overrides: dict[str, Any] | None) -> str | None:
    if not overrides or not isinstance(overrides, dict):
        return None
    raw = overrides.get("ai_scenario_id")
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    return normalized or None


def _with_internal_ai_schedule_target(
    overrides: dict[str, Any] | None,
    ai_scenario_id: str | None,
) -> dict[str, Any] | None:
    next_overrides = dict(overrides or {})
    next_overrides.pop("ai_scenario_id", None)
    if ai_scenario_id:
        next_overrides["ai_scenario_id"] = ai_scenario_id
    return next_overrides or None


def _public_schedule_overrides(overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    next_overrides = dict(overrides or {})
    next_overrides.pop("ai_scenario_id", None)
    return next_overrides or None


def _response_from_row(row: ScheduleRow) -> ScheduleResponse:
    return ScheduleResponse(
        schedule_id=row.schedule_id,
        name=row.name,
        target_type=ScheduleTargetType(row.target_type or ScheduleTargetType.SCENARIO.value),
        scenario_id=row.scenario_id,
        ai_scenario_id=_schedule_ai_scenario_id(row.config_overrides),
        pack_id=row.pack_id,
        active=row.active,
        cron_expr=row.cron_expr,
        timezone=row.timezone,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_status=row.last_status,
        last_run_outcome=row.last_run_outcome,
        retry_on_failure=row.retry_on_failure,
        consecutive_failures=row.consecutive_failures,
        misfire_policy=MisfirePolicy(row.misfire_policy or "skip"),
        config_overrides=_public_schedule_overrides(row.config_overrides),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _schedule_error_status_from_api_problem(exc: ApiProblem) -> str:
    code = str(exc.error_code or "").strip().lower()
    if code:
        return f"error_{code}"
    return f"error_{exc.status}"


def _normalize_schedule_target_inputs(
    *,
    target_type: ScheduleTargetType,
    scenario_id: str | None,
    ai_scenario_id: str | None,
    pack_id: str | None,
) -> tuple[ScheduleTargetType, str | None, str | None, str | None]:
    scenario = str(scenario_id or "").strip() or None
    ai_scenario = str(ai_scenario_id or "").strip() or None
    pack = str(pack_id or "").strip() or None

    if target_type == ScheduleTargetType.SCENARIO:
        if scenario is None and ai_scenario is None:
            raise HTTPException(
                status_code=422,
                detail="scenario schedules require scenario_id or ai_scenario_id",
            )
        if pack is not None:
            raise HTTPException(
                status_code=422,
                detail="scenario schedules must not include pack_id",
            )
        return target_type, scenario, ai_scenario, None

    if target_type == ScheduleTargetType.PACK:
        if pack is None:
            raise HTTPException(
                status_code=422,
                detail="pack schedules require pack_id",
            )
        if scenario is not None or ai_scenario is not None:
            raise HTTPException(
                status_code=422,
                detail="pack schedules must not include scenario_id or ai_scenario_id",
            )
        return target_type, None, None, pack

    raise HTTPException(status_code=422, detail=f"Unsupported target_type: {target_type.value}")


def _normalize_overrides(overrides: dict[str, Any] | None) -> dict[str, Any] | None:
    if overrides is None:
        return None
    allowed = {
        "bot_endpoint",
        "destination_id",
        "retention_profile",
        "triggered_by",
        "transport_profile_id",
        "dial_target",
    }
    unknown = set(overrides.keys()) - allowed
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported schedule override keys: {sorted(unknown)}",
        )

    out: dict[str, Any] = {}
    bot_endpoint = (
        str(overrides["bot_endpoint"]).strip() if "bot_endpoint" in overrides else None
    )
    dial_target = (
        str(overrides["dial_target"]).strip() if "dial_target" in overrides else None
    )
    if bot_endpoint == "":
        raise HTTPException(status_code=422, detail="bot_endpoint override must not be empty")
    if dial_target == "":
        raise HTTPException(status_code=422, detail="dial_target override must not be empty")
    if bot_endpoint is not None and dial_target is not None and bot_endpoint != dial_target:
        raise HTTPException(
            status_code=422,
            detail="bot_endpoint override must match dial_target override",
        )
    normalized_dial_target = dial_target or bot_endpoint
    if normalized_dial_target is not None:
        out["bot_endpoint"] = normalized_dial_target
        out["dial_target"] = normalized_dial_target

    destination_id = (
        str(overrides["destination_id"]).strip() if "destination_id" in overrides else None
    )
    transport_profile_id = (
        str(overrides["transport_profile_id"]).strip()
        if "transport_profile_id" in overrides
        else None
    )
    if destination_id == "":
        raise HTTPException(
            status_code=422,
            detail="destination_id override must not be empty",
        )
    if transport_profile_id == "":
        raise HTTPException(
            status_code=422,
            detail="transport_profile_id override must not be empty",
        )
    if (
        destination_id is not None
        and transport_profile_id is not None
        and destination_id != transport_profile_id
    ):
        raise HTTPException(
            status_code=422,
            detail="destination_id override must match transport_profile_id override",
        )
    normalized_transport_profile_id = transport_profile_id or destination_id
    if normalized_transport_profile_id is not None:
        out["destination_id"] = normalized_transport_profile_id
        out["transport_profile_id"] = normalized_transport_profile_id
    if "retention_profile" in overrides:
        try:
            out["retention_profile"] = RetentionProfile(
                str(overrides["retention_profile"])
            ).value
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="retention_profile override must be one of "
                "ephemeral|standard|compliance|no_audio",
            ) from exc
    if "triggered_by" in overrides:
        triggered_by = str(overrides["triggered_by"]).strip()
        if not triggered_by:
            raise HTTPException(status_code=422, detail="triggered_by override must not be empty")
        out["triggered_by"] = triggered_by[:255]
    return out or None


def _normalize_schedule_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _next_run_or_none(*, active: bool, cron_expr: str, timezone: str) -> datetime | None:
    if not active:
        return None
    return compute_next_run_at(cron_expr=cron_expr, timezone=timezone)


async def _validate_schedule_target_exists(
    *,
    db: AsyncSession,
    tenant_id: str,
    target_type: ScheduleTargetType,
    scenario_id: str | None,
    ai_scenario_id: str | None,
    pack_id: str | None,
) -> tuple[str | None, str | None]:
    if target_type == ScheduleTargetType.SCENARIO:
        if ai_scenario_id is not None:
            if not settings.feature_ai_scenarios_enabled:
                raise ApiProblem(
                    status=503,
                    error_code=AI_SCENARIOS_DISABLED,
                    detail="AI scenarios are disabled",
                )
            ai_scenario = await get_ai_scenario(
                db,
                ai_scenario_id=ai_scenario_id,
                tenant_id=tenant_id,
            )
            if ai_scenario is None:
                raise HTTPException(status_code=404, detail="AI scenario not found")
            if scenario_id is not None and scenario_id != ai_scenario.scenario_id:
                raise HTTPException(
                    status_code=422,
                    detail="scenario_id does not match ai_scenario_id",
                )
            return ai_scenario.scenario_id, ai_scenario.ai_scenario_id

        assert scenario_id is not None
        scenario = await get_scenario(db, scenario_id, tenant_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return scenario_id, None

    assert pack_id is not None
    pack = await get_scenario_pack(db, pack_id, tenant_id)
    if pack is None:
        raise ApiProblem(
            status=404,
            error_code=PACK_NOT_FOUND,
            detail="Pack not found",
        )
    return None, None


async def _validate_schedule_override_destination(
    *,
    db: AsyncSession,
    tenant_id: str,
    overrides: dict[str, Any] | None,
) -> None:
    if not overrides:
        return
    destination_id_raw = overrides.get("transport_profile_id") or overrides.get("destination_id")
    if not isinstance(destination_id_raw, str):
        return
    destination_id = destination_id_raw.strip()
    if not destination_id:
        return
    if not settings.feature_destinations_enabled:
        raise ApiProblem(
            status=503,
            error_code=DESTINATIONS_DISABLED,
            detail="Destinations are disabled",
        )
    destination = await get_bot_destination(db, destination_id, tenant_id)
    if destination is None:
        raise ApiProblem(
            status=422,
            error_code=DESTINATION_NOT_FOUND,
            detail="destination_id override not found",
        )
    if not destination.is_active:
        raise ApiProblem(
            status=422,
            error_code=DESTINATION_INACTIVE,
            detail="Destination is inactive",
        )


async def _dispatch_schedule_target(
    *,
    request: Request,
    db: AsyncSession,
    row: ScheduleRow,
    tenant_id: str,
    triggered_by: str,
    bot_endpoint: str | None,
    destination_id: str | None,
    dial_target: str | None,
    transport_profile_id: str | None,
    retention_profile: RetentionProfile | None,
) -> None:
    target_type = ScheduleTargetType(row.target_type or ScheduleTargetType.SCENARIO.value)
    if target_type == ScheduleTargetType.SCENARIO:
        scenario_id = str(row.scenario_id or "").strip()
        ai_scenario_id = _schedule_ai_scenario_id(row.config_overrides)
        if not scenario_id:
            raise HTTPException(status_code=422, detail="Scenario schedule missing scenario_id")
        await _create_run_internal(
            request=request,
            body=RunCreate(
                scenario_id=scenario_id,
                ai_scenario_id=ai_scenario_id,
                bot_endpoint=bot_endpoint,
                destination_id=destination_id,
                dial_target=dial_target,
                transport_profile_id=transport_profile_id,
                retention_profile=retention_profile,
            ),
            tenant_id=tenant_id,
            trigger_source="scheduled",
            triggered_by=triggered_by,
            schedule_id=row.schedule_id,
            db=db,
        )
        return

    if not settings.feature_packs_enabled:
        raise ApiProblem(
            status=503,
            error_code=SCENARIO_PACKS_DISABLED,
            detail="Scenario packs are disabled",
        )
    if transport_profile_id:
        if not settings.feature_destinations_enabled:
            raise ApiProblem(
                status=503,
                error_code=DESTINATIONS_DISABLED,
                detail="Destinations are disabled",
            )
        destination = await get_bot_destination(db, transport_profile_id, tenant_id)
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
    pack_id = str(row.pack_id or "").strip()
    if not pack_id:
        raise HTTPException(status_code=422, detail="Pack schedule missing pack_id")
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise HTTPException(status_code=503, detail="Job queue unavailable")
    try:
        snapshot = await create_pack_run_snapshot(
            db,
            pack_id=pack_id,
            tenant_id=tenant_id,
            destination_id=destination_id,
            transport_profile_id=transport_profile_id,
            dial_target=dial_target,
            trigger_source="scheduled",
            schedule_id=row.schedule_id,
            triggered_by=triggered_by,
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
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to enqueue pack run: {exc}") from exc


@router.get("/", response_model=list[ScheduleResponse])
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    rows = await list_schedule_rows(db, user.tenant_id)
    return [_response_from_row(row) for row in rows]


@router.get("/{schedule_id}/runs", response_model=list[RunResponse])
async def list_schedule_runs(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    schedule = await get_schedule_for_tenant(db, schedule_id, user.tenant_id)
    if schedule is None:
        raise ApiProblem(status=404, error_code=SCHEDULE_NOT_FOUND, detail="Schedule not found")
    run_rows = await list_run_rows_for_schedule(db, schedule_id, user.tenant_id)
    return [
        RunResponse(
            run_id=row.run_id,
            scenario_id=row.scenario_id,
            state=RunState(row.state),
            run_type=RunType(row.run_type or "standard"),
            playground_mode=(
                PlaygroundMode(row.playground_mode)
                if str(row.playground_mode or "").strip()
                else None
            ),
            livekit_room=row.livekit_room,
            trigger_source=row.trigger_source or "manual",
            schedule_id=row.schedule_id,
            triggered_by=row.triggered_by,
            transport=row.transport or "none",
            tts_cache_status_at_start=normalize_cache_status(row.tts_cache_status_at_start),
            destination_id_at_start=row.destination_id_at_start,
            transport_profile_id_at_start=row.transport_profile_id_at_start,
            dial_target_at_start=row.dial_target_at_start,
            capacity_scope_at_start=row.capacity_scope_at_start,
            capacity_limit_at_start=row.capacity_limit_at_start,
            retention_profile=RetentionProfile(row.retention_profile or "standard"),
            created_at=row.created_at,
            gate_result=row.gate_result,
            failed_dimensions=row.failed_dimensions or [],
            error_code=row.error_code,
            end_reason=row.end_reason,
            end_source=row.end_source,
            report_s3_key=row.report_s3_key,
            recording_s3_key=row.recording_s3_key,
            summary=row.summary,
            cost_pence=row.cost_pence,
            scores=deserialize_scores(row.scores),
            findings=row.findings or [],
            events=[],
            conversation=[],
        )
        for row in run_rows
    ]


@router.post("/", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
    await assert_tenant_quota_available(
        db,
        tenant=tenant,
        tenant_id=user.tenant_id,
        quota_name="max_schedules",
    )
    target_type, scenario_id, ai_scenario_id, pack_id = _normalize_schedule_target_inputs(
        target_type=body.target_type,
        scenario_id=body.scenario_id,
        ai_scenario_id=body.ai_scenario_id,
        pack_id=body.pack_id,
    )
    resolved_scenario_id, resolved_ai_scenario_id = await _validate_schedule_target_exists(
        db=db,
        tenant_id=user.tenant_id,
        target_type=target_type,
        scenario_id=scenario_id,
        ai_scenario_id=ai_scenario_id,
        pack_id=pack_id,
    )
    if target_type == ScheduleTargetType.PACK and body.retry_on_failure:
        raise HTTPException(
            status_code=422,
            detail="retry_on_failure is only supported for scenario schedules",
        )

    try:
        cron_expr = normalize_cron_expr(body.cron_expr)
        timezone = normalize_timezone(
            body.timezone,
            default_timezone=settings.instance_timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config_overrides = _normalize_overrides(body.config_overrides)
    config_overrides = _with_internal_ai_schedule_target(
        config_overrides,
        resolved_ai_scenario_id if target_type == ScheduleTargetType.SCENARIO else None,
    )
    await _validate_schedule_override_destination(
        db=db,
        tenant_id=user.tenant_id,
        overrides=config_overrides,
    )
    next_run_at = _next_run_or_none(
        active=body.active,
        cron_expr=cron_expr,
        timezone=timezone,
    )
    row = ScheduleRow(
        schedule_id=f"sched_{uuid.uuid4().hex[:12]}",
        tenant_id=user.tenant_id,
        name=_normalize_schedule_name(body.name),
        target_type=target_type.value,
        scenario_id=resolved_scenario_id,
        pack_id=pack_id,
        active=body.active,
        retry_on_failure=body.retry_on_failure,
        cron_expr=cron_expr,
        timezone=timezone,
        next_run_at=next_run_at,
        misfire_policy=body.misfire_policy.value,
        config_overrides=config_overrides,
    )
    await store_schedule(db, row)
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="schedule.create",
        resource_type="schedule",
        resource_id=row.schedule_id,
        detail={
            "name": row.name,
            "target_type": row.target_type,
            "scenario_id": row.scenario_id,
            "ai_scenario_id": resolved_ai_scenario_id,
            "pack_id": row.pack_id,
            "cron_expr": row.cron_expr,
            "timezone": row.timezone,
            "active": row.active,
            "retry_on_failure": row.retry_on_failure,
        },
    )
    await db.commit()
    return _response_from_row(row)


@router.post("/preview", response_model=SchedulePreviewResponse)
async def preview_schedule(
    body: SchedulePreviewRequest,
    _: UserContext = Depends(require_viewer),
):
    try:
        cron_expr = normalize_cron_expr(body.cron_expr)
        timezone = normalize_timezone(
            body.timezone,
            default_timezone=settings.instance_timezone,
        )
        occurrences = compute_next_run_occurrences(
            cron_expr=cron_expr,
            timezone=timezone,
            count=body.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SchedulePreviewResponse(
        cron_expr=cron_expr,
        timezone=timezone,
        occurrences=occurrences,
    )


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: SchedulePatch,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    row = await get_schedule_for_tenant(db, schedule_id, user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=SCHEDULE_NOT_FOUND,
            detail="Schedule not found",
        )
    fields_set = body.model_fields_set
    needs_recompute = bool(fields_set & {"active", "cron_expr", "timezone"})
    target_fields = {"target_type", "scenario_id", "ai_scenario_id", "pack_id"}
    if fields_set & target_fields:
        target_type = (
            body.target_type
            if "target_type" in fields_set and body.target_type is not None
            else ScheduleTargetType(row.target_type or ScheduleTargetType.SCENARIO.value)
        )
        scenario_id = row.scenario_id
        pack_id = row.pack_id
        if "scenario_id" in fields_set:
            scenario_id = body.scenario_id
        if "pack_id" in fields_set:
            pack_id = body.pack_id

        existing_ai_scenario_id = _schedule_ai_scenario_id(row.config_overrides)
        ai_scenario_id = existing_ai_scenario_id
        if "ai_scenario_id" in fields_set:
            ai_scenario_id = body.ai_scenario_id

        target_type, scenario_id, ai_scenario_id, pack_id = _normalize_schedule_target_inputs(
            target_type=target_type,
            scenario_id=scenario_id,
            ai_scenario_id=ai_scenario_id,
            pack_id=pack_id,
        )
        resolved_scenario_id, resolved_ai_scenario_id = await _validate_schedule_target_exists(
            db=db,
            tenant_id=user.tenant_id,
            target_type=target_type,
            scenario_id=scenario_id,
            ai_scenario_id=ai_scenario_id,
            pack_id=pack_id,
        )
        row.target_type = target_type.value
        row.scenario_id = resolved_scenario_id
        row.pack_id = pack_id
        row.config_overrides = _with_internal_ai_schedule_target(
            row.config_overrides,
            resolved_ai_scenario_id if target_type == ScheduleTargetType.SCENARIO else None,
        )
        if target_type == ScheduleTargetType.PACK and row.retry_on_failure:
            row.retry_on_failure = False

    if "cron_expr" in fields_set and body.cron_expr is not None:
        try:
            row.cron_expr = normalize_cron_expr(body.cron_expr)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "timezone" in fields_set and body.timezone is not None:
        try:
            row.timezone = normalize_timezone(
                body.timezone,
                default_timezone=settings.instance_timezone,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "active" in fields_set and body.active is not None:
        row.active = body.active
    if "retry_on_failure" in fields_set and body.retry_on_failure is not None:
        if (
            ScheduleTargetType(row.target_type or ScheduleTargetType.SCENARIO.value)
            == ScheduleTargetType.PACK
            and body.retry_on_failure
        ):
            raise HTTPException(
                status_code=422,
                detail="retry_on_failure is only supported for scenario schedules",
            )
        row.retry_on_failure = body.retry_on_failure
    if "name" in fields_set:
        row.name = _normalize_schedule_name(body.name)
    if "misfire_policy" in fields_set and body.misfire_policy is not None:
        row.misfire_policy = body.misfire_policy.value
    if "config_overrides" in fields_set:
        next_overrides = _normalize_overrides(body.config_overrides)
        next_overrides = _with_internal_ai_schedule_target(
            next_overrides,
            _schedule_ai_scenario_id(row.config_overrides)
            if row.target_type == ScheduleTargetType.SCENARIO.value
            else None,
        )
        row.config_overrides = next_overrides
        await _validate_schedule_override_destination(
            db=db,
            tenant_id=user.tenant_id,
            overrides=row.config_overrides,
        )

    if needs_recompute:
        row.next_run_at = _next_run_or_none(
            active=row.active,
            cron_expr=row.cron_expr,
            timezone=row.timezone,
        )
    row.updated_at = datetime.now(UTC)

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="schedule.update",
        resource_type="schedule",
        resource_id=row.schedule_id,
        detail={
            "name": row.name,
            "target_type": row.target_type,
            "scenario_id": row.scenario_id,
            "ai_scenario_id": _schedule_ai_scenario_id(row.config_overrides),
            "pack_id": row.pack_id,
            "cron_expr": row.cron_expr,
            "timezone": row.timezone,
            "active": row.active,
            "retry_on_failure": row.retry_on_failure,
            "misfire_policy": row.misfire_policy,
        },
    )
    await db.commit()

    return _response_from_row(row)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    row = await get_schedule_for_tenant(db, schedule_id, user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=SCHEDULE_NOT_FOUND,
            detail="Schedule not found",
        )
    await db.delete(row)
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="schedule.delete",
        resource_type="schedule",
        resource_id=schedule_id,
        detail={
            "name": row.name,
            "target_type": row.target_type,
            "scenario_id": row.scenario_id,
            "ai_scenario_id": _schedule_ai_scenario_id(row.config_overrides),
            "pack_id": row.pack_id,
        },
    )
    await db.commit()
    return None


@router.post("/dispatch-due", response_model=DispatchDueResponse)
async def dispatch_due_schedules(
    request: Request,
    body: DispatchDueRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    if caller != "scheduler":
        raise HTTPException(status_code=403, detail="Only scheduler may dispatch due schedules")

    now = datetime.now(UTC)
    due = await list_due_schedules(db, settings.tenant_id, now, body.limit)
    dispatched = 0
    throttled = 0
    failed = 0

    for row in due:
        try:
            overrides = _normalize_overrides(_public_schedule_overrides(row.config_overrides) or {})
            retention_profile = None
            if overrides and "retention_profile" in overrides:
                retention_profile = RetentionProfile(str(overrides["retention_profile"]))
            bot_endpoint = overrides.get("bot_endpoint") if overrides else None
            destination_id = overrides.get("destination_id") if overrides else None
            dial_target = overrides.get("dial_target") if overrides else None
            transport_profile_id = (
                overrides.get("transport_profile_id") if overrides else None
            )
            triggered_by = (
                str(overrides.get("triggered_by"))
                if overrides and overrides.get("triggered_by")
                else None
            ) or "scheduler-worker"
            await _dispatch_schedule_target(
                request=request,
                db=db,
                row=row,
                tenant_id=settings.tenant_id,
                triggered_by=triggered_by,
                bot_endpoint=bot_endpoint,
                destination_id=destination_id,
                dial_target=dial_target,
                transport_profile_id=transport_profile_id,
                retention_profile=retention_profile,
            )
            row.last_run_at = now
            row.last_status = "dispatched"
            dispatched += 1
            api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="dispatched").inc()
        except ApiProblem as exc:
            if exc.status == 429:
                row.last_status = "throttled"
                throttled += 1
                api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="throttled").inc()
            else:
                row.last_status = _schedule_error_status_from_api_problem(exc)
                failed += 1
                api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="failed").inc()
            row.last_run_at = now
        except HTTPException as exc:
            if exc.status_code == 429:
                row.last_status = "throttled"
                throttled += 1
                api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="throttled").inc()
            else:
                row.last_status = f"error_{exc.status_code}"
                failed += 1
                api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="failed").inc()
            row.last_run_at = now
        except Exception:
            row.last_status = "error_internal"
            row.last_run_at = now
            failed += 1
            api_metrics.SCHEDULES_DISPATCH_TOTAL.labels(outcome="failed").inc()

        if row.active:
            if row.last_status == "throttled" and row.misfire_policy == MisfirePolicy.RUN_ONCE.value:
                row.next_run_at = now + timedelta(seconds=settings.schedule_dispatch_backoff_s)
            else:
                row.next_run_at = compute_next_run_at(
                    cron_expr=row.cron_expr,
                    timezone=row.timezone,
                    now=now,
                )
        else:
            row.next_run_at = None
        row.updated_at = datetime.now(UTC)
        try:
            # Commit per schedule row so one bad row does not roll back the full batch.
            await db.commit()
        except Exception:
            await db.rollback()
            if row.last_status == "dispatched" and dispatched > 0:
                dispatched -= 1
            if row.last_status == "throttled" and throttled > 0:
                throttled -= 1
            if not (row.last_status or "").startswith("error_"):
                failed += 1
            logger.exception(
                "Failed to persist schedule dispatch outcome",
                extra={"schedule_id": row.schedule_id},
            )

    return DispatchDueResponse(
        checked=len(due),
        dispatched=dispatched,
        throttled=throttled,
        failed=failed,
        now=now,
    )
