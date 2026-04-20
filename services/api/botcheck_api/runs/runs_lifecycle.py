import logging
from datetime import UTC

import structlog
from botcheck_scenarios import RunRoomMetadata
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from livekit import api as lk_api
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from . import service_playground_presets as _playground_presets
from . import service_playground_tools as _playground_tools
from . import service_webrtc
from .runs import (
    HarnessRunContextResponse,
    PlaygroundExtractToolsRequest,
    PlaygroundExtractedTool,
    PlaygroundGenerateStubsRequest,
    PlaygroundPresetDetail,
    PlaygroundPresetPatch,
    PlaygroundPresetSummary,
    PlaygroundPresetWrite,
    PlaygroundRunCreate,
    RunCreate,
    RunPatch,
    RunResponse,
    ScheduledRunCreate,
)
from .service_schedule_outcome import apply_schedule_run_outcome
from .service_state import release_run_sip_slot_if_held
from .store_service import (
    append_run_event,
    get_run as get_run_row,
    get_run_for_tenant as get_run_row_for_tenant,
)
from .. import metrics as api_metrics
from ..audit import write_audit_event
from ..auth import (
    UserContext,
    get_current_user,
    get_service_caller,
    require_editor,
    require_operator,
    require_viewer,
)
from ..capacity import release_sip_slot as _release_sip_slot
from ..config import settings
from ..database import get_db
from ..models import PlaygroundMode, RetentionProfile, RunRow, RunState, RunType
from ..packs.service import aggregate_pack_run_child_terminal_state
from ..repo_runs import get_bot_destination_row_for_tenant
from ..exceptions import ApiProblem, RUN_NOT_FOUND
from ..retention import delete_report_artifact as _delete_report_artifact
from .service import (
    create_run_internal,
    delete_livekit_room as _delete_livekit_room,
    deserialize_scores,
    livekit_room_exists as _livekit_room_exists,
    normalize_cache_status,
    normalize_scores,
    parse_error_code,
    parse_run_state,
    redis_pool_from_request,
    transition_run_state,
)

logger = logging.getLogger("botcheck.api.runs")
event_logger = structlog.get_logger("botcheck.api.runs.lifecycle")
router = APIRouter()


async def extract_tool_signatures(*args, **kwargs):
    return await _playground_tools.extract_tool_signatures(*args, **kwargs)


async def generate_stub_values(*args, **kwargs):
    return await _playground_tools.generate_stub_values(*args, **kwargs)


async def list_playground_presets(*args, **kwargs):
    return await _playground_presets.list_playground_presets(*args, **kwargs)


async def get_playground_preset(*args, **kwargs):
    return await _playground_presets.get_playground_preset(*args, **kwargs)


async def create_playground_preset(*args, **kwargs):
    return await _playground_presets.create_playground_preset(*args, **kwargs)


async def update_playground_preset(*args, **kwargs):
    return await _playground_presets.update_playground_preset(*args, **kwargs)


async def delete_playground_preset(*args, **kwargs):
    return await _playground_presets.delete_playground_preset(*args, **kwargs)


def preset_not_found_problem(*args, **kwargs):
    return _playground_presets.preset_not_found_problem(*args, **kwargs)


# Wrappers expose stable patch points inside this split module.
async def delete_report_artifact(*args, **kwargs):
    return await _delete_report_artifact(*args, **kwargs)


async def livekit_room_exists(*args, **kwargs):
    return await _livekit_room_exists(*args, **kwargs)


async def delete_livekit_room(*args, **kwargs):
    return await _delete_livekit_room(*args, **kwargs)


async def release_sip_slot(*args, **kwargs):
    return await _release_sip_slot(*args, **kwargs)


async def _get_livekit_room_metadata(room_name: str) -> str | None:
    candidate = room_name.strip()
    if not candidate:
        return None
    lkapi = lk_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        resp = await lkapi.room.list_rooms(lk_api.ListRoomsRequest(names=[candidate]))
        rooms = list(getattr(resp, "rooms", []) or [])
        for room in rooms:
            if str(getattr(room, "name", "") or "") == candidate:
                metadata = str(getattr(room, "metadata", "") or "").strip()
                return metadata or None
        return None
    finally:
        await lkapi.aclose()


def _run_row_to_response(run: RunRow, *, include_full_payload: bool = False) -> RunResponse:
    return RunResponse(
        run_id=run.run_id,
        scenario_id=run.scenario_id,
        state=RunState(run.state),
        run_type=RunType(run.run_type or "standard"),
        playground_mode=(
            PlaygroundMode(run.playground_mode)
            if str(run.playground_mode or "").strip()
            else None
        ),
        livekit_room=run.livekit_room,
        trigger_source=run.trigger_source or "manual",
        schedule_id=run.schedule_id,
        triggered_by=run.triggered_by,
        transport=run.transport or "none",
        tts_cache_status_at_start=normalize_cache_status(run.tts_cache_status_at_start),
        destination_id_at_start=run.destination_id_at_start,
        transport_profile_id_at_start=run.transport_profile_id_at_start,
        dial_target_at_start=run.dial_target_at_start,
        capacity_scope_at_start=run.capacity_scope_at_start,
        capacity_limit_at_start=run.capacity_limit_at_start,
        retention_profile=RetentionProfile(run.retention_profile or "standard"),
        created_at=run.created_at,
        gate_result=run.gate_result,
        failed_dimensions=run.failed_dimensions or [],
        error_code=run.error_code,
        end_reason=run.end_reason,
        end_source=run.end_source,
        report_s3_key=run.report_s3_key,
        recording_s3_key=run.recording_s3_key,
        summary=run.summary,
        cost_pence=run.cost_pence,
        scores=deserialize_scores(run.scores),
        findings=run.findings or [],
        events=(run.events or []) if include_full_payload else [],
        conversation=(run.conversation or []) if include_full_payload else [],
    )


@router.post("/", response_model=RunResponse, status_code=202)
async def create_run(
    body: RunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    """Trigger a new manual test run for a scenario."""
    return await create_run_internal(
        request=request,
        body=body,
        tenant_id=user.tenant_id,
        trigger_source="manual",
        triggered_by=user.sub,
        schedule_id=None,
        db=db,
    )


@router.post("/playground", response_model=RunResponse, status_code=202)
async def create_playground_run(
    body: PlaygroundRunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    """Create a playground run on the shared run pipeline."""
    return await create_run_internal(
        request=request,
        body=body,
        tenant_id=user.tenant_id,
        trigger_source="playground",
        triggered_by=user.sub,
        schedule_id=None,
        db=db,
        run_type=RunType.PLAYGROUND,
        playground_mode=body.playground_mode,
        playground_system_prompt=body.system_prompt,
        playground_tool_stubs=body.tool_stubs,
    )


def _serialize_playground_preset_summary(row) -> PlaygroundPresetSummary:
    return PlaygroundPresetSummary(
        preset_id=row.preset_id,
        name=row.name,
        description=row.description,
        scenario_id=row.scenario_id,
        ai_scenario_id=row.ai_scenario_id,
        playground_mode=PlaygroundMode(row.playground_mode),
        transport_profile_id=row.transport_profile_id,
        has_tool_stubs=bool(row.tool_stubs),
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC),
        updated_at=row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=UTC),
    )


def _serialize_playground_preset_detail(row) -> PlaygroundPresetDetail:
    return PlaygroundPresetDetail(
        **_serialize_playground_preset_summary(row).model_dump(),
        system_prompt=row.system_prompt,
        tool_stubs=dict(row.tool_stubs or {}) or None,
    )


@router.get("/playground/presets", response_model=list[PlaygroundPresetSummary])
async def list_playground_presets_route(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    rows = await list_playground_presets(db, tenant_id=user.tenant_id)
    return [_serialize_playground_preset_summary(row) for row in rows]


@router.post("/playground/presets", response_model=PlaygroundPresetDetail, status_code=201)
async def create_playground_preset_route(
    body: PlaygroundPresetWrite,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    row = await create_playground_preset(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        name=body.name,
        description=body.description,
        scenario_id=body.scenario_id,
        ai_scenario_id=body.ai_scenario_id,
        playground_mode=body.playground_mode,
        transport_profile_id=body.transport_profile_id,
        system_prompt=body.system_prompt,
        tool_stubs=body.tool_stubs,
    )
    return _serialize_playground_preset_detail(row)


@router.get("/playground/presets/{preset_id}", response_model=PlaygroundPresetDetail)
async def get_playground_preset_route(
    preset_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    row = await get_playground_preset(db, tenant_id=user.tenant_id, preset_id=preset_id)
    if row is None:
        raise preset_not_found_problem()
    return _serialize_playground_preset_detail(row)


@router.patch("/playground/presets/{preset_id}", response_model=PlaygroundPresetDetail)
async def update_playground_preset_route(
    preset_id: str,
    body: PlaygroundPresetPatch,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    existing = await get_playground_preset(db, tenant_id=user.tenant_id, preset_id=preset_id)
    if existing is None:
        raise preset_not_found_problem()
    merged = {
        "name": existing.name,
        "description": existing.description,
        "scenario_id": existing.scenario_id,
        "ai_scenario_id": existing.ai_scenario_id,
        "playground_mode": existing.playground_mode,
        "transport_profile_id": existing.transport_profile_id,
        "system_prompt": existing.system_prompt,
        "tool_stubs": existing.tool_stubs,
    }
    merged.update(body.model_dump(exclude_unset=True))
    try:
        validated = PlaygroundPresetWrite.model_validate(merged)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(status_code=422, detail=first.get("msg", str(exc))) from exc
    row = await update_playground_preset(
        db,
        tenant_id=user.tenant_id,
        preset_id=preset_id,
        actor_id=user.sub,
        name=validated.name,
        description=validated.description,
        scenario_id=validated.scenario_id,
        ai_scenario_id=validated.ai_scenario_id,
        playground_mode=validated.playground_mode,
        transport_profile_id=validated.transport_profile_id,
        system_prompt=validated.system_prompt,
        tool_stubs=validated.tool_stubs,
    )
    return _serialize_playground_preset_detail(row)


@router.delete("/playground/presets/{preset_id}", status_code=204)
async def delete_playground_preset_route(
    preset_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    await delete_playground_preset(
        db,
        tenant_id=user.tenant_id,
        preset_id=preset_id,
        actor_id=user.sub,
    )
    return Response(status_code=204)


@router.post("/playground/extract-tools", response_model=list[PlaygroundExtractedTool])
async def playground_extract_tools(
    body: PlaygroundExtractToolsRequest,
    user: UserContext = Depends(require_editor),
):
    del user
    if not body.system_prompt:
        return []
    try:
        return await extract_tool_signatures(
            system_prompt=body.system_prompt,
            openai_api_key=settings.openai_api_key,
        )
    except Exception:
        logger.warning("playground_extract_tools_failed", exc_info=True)
        return []


@router.post("/playground/generate-stubs", response_model=dict[str, dict[str, object]])
async def playground_generate_stubs(
    body: PlaygroundGenerateStubsRequest,
    user: UserContext = Depends(require_editor),
):
    """Generate scenario-grounded stub return values for extracted tools."""
    del user
    if not body.tools:
        return {}
    try:
        return await generate_stub_values(
            tools=[t.model_dump() for t in body.tools],
            scenario_summary=body.scenario_summary,
            openai_api_key=settings.openai_api_key,
        )
    except Exception:
        logger.warning("playground_generate_stubs_failed", exc_info=True)
        return {t.name: {} for t in body.tools}


@router.post("/scheduled", response_model=RunResponse, status_code=202)
async def create_run_from_schedule(
    body: ScheduledRunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """Scheduler-only entrypoint for capacity-aware scheduled run creation."""
    if caller != "scheduler":
        raise HTTPException(status_code=403, detail="Only scheduler may create scheduled runs")
    return await create_run_internal(
        request=request,
        body=RunCreate(
            scenario_id=body.scenario_id,
            bot_endpoint=body.bot_endpoint,
            destination_id=body.destination_id,
            retention_profile=body.retention_profile,
        ),
        tenant_id=settings.tenant_id,
        trigger_source="scheduled",
        triggered_by=body.triggered_by,
        schedule_id=body.schedule_id,
        db=db,
    )


@router.get("/{run_id}/transport-context", response_model=HarnessRunContextResponse)
async def get_run_transport_context(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may fetch transport context")

    run = await get_run_row(db, run_id)
    if run is None:
        raise ApiProblem(status=404, error_code=RUN_NOT_FOUND, detail="Run not found")
    run_type = str(run.run_type or "").strip().lower()
    playground_mode = str(run.playground_mode or "").strip().lower()
    transport = str(run.transport or "").strip().lower()
    if run_type == "playground" and playground_mode == "mock":
        return HarnessRunContextResponse(
            run_id=run.run_id,
            playground_mode=PlaygroundMode.MOCK,
            playground_system_prompt=str(run.playground_system_prompt or "").strip() or None,
            playground_tool_stubs=dict(run.playground_tool_stubs or {}) or None,
        )
    if transport != "http":
        if transport != "webrtc":
            raise HTTPException(status_code=404, detail="Run has no harness transport context")

        room_metadata_raw = await _get_livekit_room_metadata(run.livekit_room)
        if not room_metadata_raw:
            raise HTTPException(status_code=404, detail="Run has no WebRTC bootstrap metadata")
        try:
            room_metadata = RunRoomMetadata.model_validate_json(room_metadata_raw)
        except ValidationError as exc:
            raise HTTPException(status_code=502, detail="Run WebRTC bootstrap metadata is invalid") from exc

        room_metadata_items = room_metadata.model_dump(mode="json", exclude_none=True)
        session_id = str(room_metadata_items.get("webrtc_session_id") or "").strip()
        if not session_id:
            raise HTTPException(status_code=404, detail="Run has no WebRTC session id")

        transport_profile_id = str(run.transport_profile_id_at_start or "").strip()
        # Snapshot-first for new runs; fall back to the live destination row only
        # when the snapshot column is NULL — i.e. runs created before migration 0058.
        # An explicit None check is used (not truthiness) so an empty-dict snapshot
        # is never silently treated as a missing one.
        webrtc_config: dict[str, object] | None = run.webrtc_config_at_start
        if webrtc_config is None:
            if not transport_profile_id:
                raise HTTPException(status_code=404, detail="Run has no WebRTC transport profile")
            destination = await get_bot_destination_row_for_tenant(db, transport_profile_id, run.tenant_id)
            if destination is None:
                raise HTTPException(status_code=404, detail="Run transport profile not found")
            webrtc_config = dict(destination.webrtc_config or {}) or None
            if not webrtc_config:
                raise HTTPException(status_code=404, detail="Run transport profile has no WebRTC config")

        try:
            token = await service_webrtc.resolve_bot_builder_preview_token(
                webrtc_config=webrtc_config,
                session_id=session_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Failed to refresh WebRTC participant token") from exc

        join_timeout_s = room_metadata_items.get("webrtc_join_timeout_s")
        normalized_join_timeout_s = int(join_timeout_s) if join_timeout_s is not None else None
        return HarnessRunContextResponse(
            run_id=run.run_id,
            transport_profile_id=transport_profile_id,
            webrtc_provider=str(room_metadata_items.get("webrtc_provider") or "").strip() or None,
            webrtc_session_mode=(
                str(room_metadata_items.get("webrtc_session_mode") or "").strip() or None
            ),
            webrtc_session_id=session_id,
            webrtc_remote_room_name=(
                str(room_metadata_items.get("webrtc_remote_room_name") or "").strip() or None
            ),
            webrtc_participant_name=(
                str(room_metadata_items.get("webrtc_participant_name") or "").strip() or None
            ),
            webrtc_server_url=token.server_url,
            webrtc_participant_token=token.participant_token,
            webrtc_join_timeout_s=normalized_join_timeout_s,
            playground_mode=(
                PlaygroundMode(run.playground_mode)
                if str(run.playground_mode or "").strip()
                else None
            ),
            playground_system_prompt=str(run.playground_system_prompt or "").strip() or None,
            playground_tool_stubs=dict(run.playground_tool_stubs or {}) or None,
        )

    transport_profile_id = str(run.transport_profile_id_at_start or "").strip()
    endpoint = str(run.dial_target_at_start or "").strip()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Run has no direct HTTP endpoint")

    # Direct HTTP credentials/config must be immutable for a run once created.
    # Read them from the run snapshot, not the mutable destination row.
    return HarnessRunContextResponse(
        run_id=run.run_id,
        transport_profile_id=transport_profile_id or None,
        endpoint=endpoint,
        headers=dict(run.direct_http_headers_at_start or {}),
        direct_http_config=dict(run.direct_http_config_at_start or {}),
        playground_mode=(
            PlaygroundMode(run.playground_mode)
            if str(run.playground_mode or "").strip()
            else None
        ),
        playground_system_prompt=str(run.playground_system_prompt or "").strip() or None,
        playground_tool_stubs=dict(run.playground_tool_stubs or {}) or None,
    )


@router.get("/", response_model=list[RunResponse])
async def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    result = await db.execute(
        select(RunRow)
        .where(RunRow.tenant_id == user.tenant_id)
        .order_by(RunRow.created_at.desc())
        .options(defer(RunRow.conversation), defer(RunRow.events))
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [_run_row_to_response(row) for row in rows]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    run = await get_run_row_for_tenant(db, run_id, user.tenant_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    return _run_row_to_response(run, include_full_payload=True)


@router.patch("/{run_id}")
async def patch_run(
    run_id: str,
    body: RunPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """
    Called by the ARQ judge worker to write scoring results back.
    Only provided fields are updated.
    """
    if caller != "judge":
        raise HTTPException(status_code=403, detail="Only judge may patch runs")

    run = await get_run_row(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )

    transition_event_emitted = False
    if body.state is not None:
        new_state = parse_run_state(body.state)
        await transition_run_state(
            db,
            run,
            new_state,
            "judge_state_patch",
            {"source": "judge"},
        )
        transition_event_emitted = True
    if body.gate_result is not None:
        run.gate_result = body.gate_result
    if body.overall_status is not None:
        run.overall_status = body.overall_status
    if body.failed_dimensions is not None:
        run.failed_dimensions = body.failed_dimensions
    if body.error_code is not None:
        run.error_code = parse_error_code(body.error_code)
    if body.summary is not None:
        run.summary = body.summary
    if body.scores is not None:
        run.scores = normalize_scores(body.scores)
    if body.findings is not None:
        run.findings = body.findings
    if body.report_s3_key is not None:
        run.report_s3_key = body.report_s3_key
    if "cost_pence" in body.model_fields_set:
        run.cost_pence = body.cost_pence

    if body.state is None and body.gate_result is not None:
        await transition_run_state(
            db,
            run,
            RunState.COMPLETE,
            "judge_completed",
            {"source": "judge", "gate_result": body.gate_result},
        )
        transition_event_emitted = True

    if (
        not transition_event_emitted
        and (body.gate_result is not None or body.error_code is not None)
    ):
        await append_run_event(
            db,
            run_id,
            "judge_patch_applied",
            {
                "gate_result": body.gate_result,
                "overall_status": body.overall_status,
                "error_code": body.error_code,
            },
        )

    if body.gate_result is not None or body.error_code is not None:
        api_metrics.JUDGE_PATCH_TOTAL.labels(
            gate_result=body.gate_result or "none",
            error_code=body.error_code or "none",
        ).inc()

    terminal_state = parse_run_state(run.state)
    if run.transport == "sip" and run.sip_slot_held and terminal_state in {
        RunState.JUDGING,
        RunState.COMPLETE,
        RunState.FAILED,
        RunState.ERROR,
    }:
        await release_run_sip_slot_if_held(
            db,
            run,
            redis_pool=redis_pool_from_request(request),
            slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
            release_sip_slot=release_sip_slot,
            reason=f"judge_patch_{terminal_state.value}",
        )

    pack_aggregate = None
    if run.pack_run_id and terminal_state in {
        RunState.COMPLETE,
        RunState.FAILED,
        RunState.ERROR,
    }:
        pack_aggregate = await aggregate_pack_run_child_terminal_state(db, run=run)
        if pack_aggregate.applied:
            await append_run_event(
                db,
                run_id,
                "pack_run_item_terminal",
                {
                    "pack_run_id": pack_aggregate.pack_run_id,
                    "item_state": pack_aggregate.item_state,
                    "pack_run_state": pack_aggregate.pack_run_state,
                },
            )

    schedule_outcome = None
    if terminal_state in {RunState.COMPLETE, RunState.FAILED, RunState.ERROR}:
        schedule_outcome = await apply_schedule_run_outcome(
            request=request,
            db=db,
            run=run,
            terminal_state=terminal_state,
        )

    audit_detail: dict[str, object] = {
        "state": run.state,
        "gate_result": run.gate_result,
        "error_code": run.error_code,
        "cost_pence": run.cost_pence,
    }
    if pack_aggregate is not None and pack_aggregate.pack_run_id:
        audit_detail["pack_run_id"] = pack_aggregate.pack_run_id
        audit_detail["pack_aggregate_reason"] = pack_aggregate.reason
    if pack_aggregate is not None and pack_aggregate.applied:
        audit_detail["pack_item_state"] = pack_aggregate.item_state
        audit_detail["pack_run_state"] = pack_aggregate.pack_run_state
    if schedule_outcome is not None and schedule_outcome.applied:
        audit_detail["schedule_outcome"] = schedule_outcome.outcome
        audit_detail["schedule_consecutive_failures"] = schedule_outcome.consecutive_failures
        if schedule_outcome.retry_outcome is not None:
            audit_detail["schedule_retry_outcome"] = schedule_outcome.retry_outcome
        if schedule_outcome.retry_run_id is not None:
            audit_detail["schedule_retry_run_id"] = schedule_outcome.retry_run_id

    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id="judge",
        actor_type="service",
        action="run.judge_patch",
        resource_type="run",
        resource_id=run_id,
        detail=audit_detail,
    )
    await db.commit()
    return {"ok": True}
