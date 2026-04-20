import asyncio
import logging
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..audit import write_audit_event
from ..auth import UserContext, get_service_caller, require_editor, require_operator
from ..capacity import release_sip_slot as capacity_release_sip_slot
from ..config import settings
from ..database import get_db
from ..models import RunRow, RunState
from ..redaction import redact_turn_payload
from .runs import (
    EndReason,
    ErrorCode,
    HeartbeatStatus,
    PlaygroundEventCreate,
    PlaygroundEventResponse,
    RunHeartbeatRequest,
    RunHeartbeatResponse,
    RunOperatorActionRequest,
    RunOperatorActionResponse,
)
from .service import delete_livekit_room as service_delete_livekit_room
from .service import TERMINAL_PLAYGROUND_EVENT
from .service_judge import build_judge_job_payload
from .service_lifecycle import redis_pool_from_request
from .service_playground_events import (
    append_playground_event,
    format_sse_event,
    iter_live_playground_events,
    list_playground_events,
    parse_last_event_id,
    publish_playground_event,
    serialize_playground_event,
    supports_live_playground_pubsub,
)
from .service_schedule_outcome import apply_schedule_run_outcome
from .service_state import (
    append_path_event_dedup,
    apply_run_heartbeat,
    derive_end_reason,
    derive_turn_visit,
    normalize_branch_snippet,
    parse_end_reason,
    parse_end_source,
    parse_error_code,
    parse_loop_guard_event_detail,
    parse_run_state,
    parse_turn_number,
    parse_turn_visit,
    release_run_sip_slot_if_held,
    transition_run_state,
)
from .store_service import append_run_event, append_turn, get_run
from ..packs.service import aggregate_pack_run_child_terminal_state
from ..exceptions import ApiProblem, RUN_NOT_FOUND

router = APIRouter()

event_logger = structlog.get_logger("botcheck.api.runs.lifecycle")


# Wrappers expose stable patch points inside this split module.
async def release_sip_slot(*args, **kwargs):
    return await capacity_release_sip_slot(*args, **kwargs)


async def delete_livekit_room(*args, **kwargs):
    return await service_delete_livekit_room(*args, **kwargs)


@router.post("/{run_id}/events", response_model=PlaygroundEventResponse)
async def record_playground_event(
    run_id: str,
    body: PlaygroundEventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may record playground events")
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(status=404, error_code=RUN_NOT_FOUND, detail="Run not found")
    if str(run.run_type or "").strip().lower() != "playground":
        raise HTTPException(status_code=404, detail="Run has no playground event stream")
    if parse_run_state(run.state) == RunState.PENDING:
        await transition_run_state(
            db,
            run,
            RunState.RUNNING,
            "run_started",
            {"source": "playground_event"},
        )

    row = await append_playground_event(
        db,
        run=run,
        event_type=body.event_type,
        payload=body.payload,
    )
    await db.commit()
    await db.refresh(row)
    event = serialize_playground_event(row)
    await publish_playground_event(redis_pool_from_request(request), event)
    return PlaygroundEventResponse(
        run_id=run.run_id,
        sequence_number=row.sequence_number,
        event_type=row.event_type,
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


@router.get("/{run_id}/stream")
async def stream_playground_events(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_editor),
):
    del user
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(status=404, error_code=RUN_NOT_FOUND, detail="Run not found")
    if str(run.run_type or "").strip().lower() != "playground":
        raise HTTPException(status_code=404, detail="Run has no playground event stream")

    last_event_id = parse_last_event_id(request.headers.get("Last-Event-ID"))
    replay_rows = await list_playground_events(
        db,
        run_id=run_id,
        after_sequence_number=last_event_id,
    )
    replay_events = [serialize_playground_event(row) for row in replay_rows]
    redis_pool = redis_pool_from_request(request)

    async def _stream():
        seen = last_event_id
        for event in replay_events:
            seen = int(event["sequence_number"])
            yield format_sse_event(event)
            if str(event["event_type"]) == TERMINAL_PLAYGROUND_EVENT:
                await asyncio.sleep(0.2)
                return
        if not supports_live_playground_pubsub(redis_pool):
            while True:
                if await request.is_disconnected():
                    return
                catchup_rows = await list_playground_events(
                    db,
                    run_id=run_id,
                    after_sequence_number=seen,
                )
                for row in catchup_rows:
                    catchup_event = serialize_playground_event(row)
                    seen = int(catchup_event["sequence_number"])
                    yield format_sse_event(catchup_event)
                    if str(catchup_event["event_type"]) == TERMINAL_PLAYGROUND_EVENT:
                        await asyncio.sleep(0.2)
                        return
                await asyncio.sleep(0.1)

        async for event in iter_live_playground_events(
            redis_pool=redis_pool,
            run_id=run_id,
            after_sequence_number=seen,
        ):
            seen = int(event["sequence_number"])
            yield format_sse_event(event)
            if str(event["event_type"]) == TERMINAL_PLAYGROUND_EVENT:
                await asyncio.sleep(0.2)
                return
            # Catch up from persisted rows in case pub/sub delivery is missed.
            catchup_rows = await list_playground_events(
                db,
                run_id=run_id,
                after_sequence_number=seen,
            )
            for row in catchup_rows:
                catchup_event = serialize_playground_event(row)
                seen = int(catchup_event["sequence_number"])
                yield format_sse_event(catchup_event)
                if str(catchup_event["event_type"]) == TERMINAL_PLAYGROUND_EVENT:
                    await asyncio.sleep(0.2)
                    return

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.post("/{run_id}/heartbeat", response_model=RunHeartbeatResponse)
async def record_run_heartbeat(
    run_id: str,
    body: RunHeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may record run heartbeats")
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    state = parse_run_state(run.state)
    if state == RunState.PENDING:
        await transition_run_state(
            db,
            run,
            RunState.RUNNING,
            "run_started",
            {"source": "harness_heartbeat"},
        )

    received_at = datetime.now(UTC)
    try:
        status = apply_run_heartbeat(
            run,
            seq=body.seq,
            received_at=received_at,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            api_metrics.RUN_HEARTBEATS_TOTAL.labels(outcome="invalid_state").inc()
        raise

    lag_s = max(0.0, (received_at - body.sent_at).total_seconds())
    outcome = status.value
    api_metrics.RUN_HEARTBEATS_TOTAL.labels(outcome=outcome).inc()
    api_metrics.RUN_HEARTBEAT_LAG_SECONDS.labels(outcome=outcome).observe(lag_s)
    event_logger.info(
        "run_heartbeat_received",
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        state=run.state,
        status=outcome,
        seq=body.seq,
        turn_number=body.turn_number,
        listener_state=body.listener_state,
        lag_s=round(lag_s, 3),
    )

    if status == HeartbeatStatus.UPDATED:
        await db.commit()

    return RunHeartbeatResponse(
        status=outcome,
        state=parse_run_state(run.state),
        last_heartbeat_at=run.last_heartbeat_at,
        last_heartbeat_seq=run.last_heartbeat_seq,
    )


@router.post("/{run_id}/turns")
async def record_turn(
    run_id: str,
    turn: dict,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """Called by the harness agent to record each conversation turn."""
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may record turns")
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    state = parse_run_state(run.state)
    if state in {RunState.COMPLETE, RunState.FAILED, RunState.ERROR, RunState.JUDGING}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot record turn while run is {state.value}",
        )
    if state == RunState.PENDING:
        await transition_run_state(
            db,
            run,
            RunState.RUNNING,
            "run_started",
            {"source": "harness_turn"},
        )
    redacted_turn = redact_turn_payload(turn)
    turn_id = str(redacted_turn.get("turn_id") or "").strip()
    turn_number = parse_turn_number(redacted_turn.get("turn_number"))
    if not turn_id or turn_number is None:
        raise HTTPException(status_code=422, detail="turn_id and turn_number are required")

    prior_conversation = run.conversation or []

    stored_turn = dict(redacted_turn)
    stored_turn.pop("visit", None)
    stored_turn.pop("branch_condition_matched", None)
    stored_turn.pop("branch_response_snippet", None)

    appended = await append_turn(db, run_id, stored_turn)
    if appended:
        visit = parse_turn_visit(redacted_turn.get("visit")) or derive_turn_visit(
            conversation=prior_conversation,
            turn_id=turn_id,
        )
        await append_path_event_dedup(
            db=db,
            run=run,
            event_type="turn_executed",
            turn_id=turn_id,
            visit=visit,
            turn_number=turn_number,
            detail={"source": "harness_turn"},
        )

        branch_condition = redacted_turn.get("branch_condition_matched")
        if isinstance(branch_condition, str) and branch_condition.strip():
            snippet_redacted = normalize_branch_snippet(
                redacted_turn.get("branch_response_snippet")
            )
            branch_detail: dict[str, object] = {
                "source": "harness_turn",
                "condition_matched": branch_condition.strip(),
            }
            if snippet_redacted is not None:
                branch_detail["bot_response_snippet_redacted"] = snippet_redacted
            await append_path_event_dedup(
                db=db,
                run=run,
                event_type="branch_decision",
                turn_id=turn_id,
                visit=visit,
                turn_number=turn_number,
                detail=branch_detail,
            )
    speaker = str(redacted_turn.get("speaker", "unknown"))
    api_metrics.RUN_TURNS_RECORDED_TOTAL.labels(speaker=speaker).inc()
    return {"ok": True}


@router.post("/{run_id}/complete")
async def complete_run(
    run_id: str,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """
    Called when the scenario finishes.
    Accepts the full conversation, transitions state to JUDGING, and enqueues
    the run to the ARQ judge worker via Redis.

    Body: {"conversation": [...], "tool_context": [optional tool events]}
    """
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may complete runs")

    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    state = parse_run_state(run.state)
    if state == RunState.JUDGING:
        # Idempotent success for harness retry after a delayed/lost 200 response.
        return {"ok": True, "state": "judging"}
    if state in {RunState.COMPLETE, RunState.FAILED, RunState.ERROR}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot complete run while in {state.value}",
        )

    # Merge any turns not already stored
    conversation_payload = body.get("conversation", [])
    tool_context_payload = body.get("tool_context")
    if tool_context_payload is None:
        tool_context_payload = []
    if not isinstance(tool_context_payload, list):
        raise HTTPException(status_code=422, detail="'tool_context' must be a list")

    end_reason = parse_end_reason(body.get("end_reason")) or derive_end_reason(
        conversation_payload
    )
    end_source = parse_end_source(body.get("end_source"))
    run.end_reason = end_reason
    run.end_source = end_source

    for turn in conversation_payload:
        await append_turn(db, run_id, redact_turn_payload(turn))

    if state == RunState.PENDING:
        await transition_run_state(
            db,
            run,
            RunState.RUNNING,
            "run_started",
            {"source": "harness_complete"},
        )

    await transition_run_state(
        db,
        run,
        RunState.JUDGING,
        "judge_enqueued",
        {
            "source": "harness_complete",
            "end_reason": end_reason,
            "end_source": end_source,
        },
    )
    await release_run_sip_slot_if_held(
        db,
        run,
        redis_pool=redis_pool_from_request(request),
        slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
        release_sip_slot=release_sip_slot,
        reason="run_complete",
    )
    if run.livekit_room:
        room_name = run.livekit_room
        try:
            await delete_livekit_room(room_name)
            await append_run_event(
                db,
                run_id,
                "run_room_deleted_on_complete",
                {"room": room_name},
            )
        except Exception:
            event_logger.warning(
                "run_room_delete_on_complete_failed",
                run_id=run_id,
                room=room_name,
            )
    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id="harness",
        actor_type="service",
        action="run.complete_callback",
        resource_type="run",
        resource_id=run_id,
        detail={"end_reason": end_reason, "end_source": end_source},
    )
    # Commit so the judge worker sees all turns and the state change.
    await db.commit()

    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is not None:
        payload = await build_judge_job_payload(
            db,
            run=run,
            tool_context=tool_context_payload,
        )
        await arq_pool.enqueue_job(
            "judge_run",
            payload=payload,
            _queue_name="arq:judge",
        )
        api_metrics.JUDGE_ENQUEUE_TOTAL.labels(outcome="success").inc()
        event_logger.info(
            "run_enqueued_for_judging",
            run_id=run_id,
            tenant_id=run.tenant_id,
            trigger_source=run.trigger_source or "manual",
        )
    else:
        api_metrics.JUDGE_ENQUEUE_TOTAL.labels(outcome="unavailable").inc()
        event_logger.warning(
            "judge_queue_unavailable",
            run_id=run_id,
            tenant_id=run.tenant_id,
        )

    return {"ok": True, "state": "judging"}


@router.post("/{run_id}/fail")
async def fail_run(
    run_id: str,
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """
    Called by the harness agent when a run fails before completing.
    Prevents runs from getting stuck in PENDING or RUNNING indefinitely.
    """
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may fail runs")

    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )

    state = parse_run_state(run.state)
    if state == RunState.FAILED:
        # Idempotent retry from harness.
        return {"ok": True, "state": "failed"}
    if state == RunState.JUDGING:
        # complete() already succeeded; the harness is retrying fail() because the
        # complete 200 was lost. Do not transition back from JUDGING to FAILED.
        return {"ok": True, "state": "judging"}
    if state in {RunState.COMPLETE, RunState.ERROR}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot fail run in state {state.value}",
        )

    reason = body.get("reason", "Agent reported failure")
    parsed_error_code = (
        parse_error_code(body.get("error_code"), strict=False)
        or ErrorCode.HARNESS_TIMEOUT.value
    )
    end_reason = parse_end_reason(body.get("end_reason")) or EndReason.SERVICE_NOT_AVAILABLE.value
    end_source = parse_end_source(body.get("end_source"))
    loop_guard_detail = parse_loop_guard_event_detail(
        body.get("loop_guard"),
        end_reason=end_reason,
        end_source=end_source,
    )
    await transition_run_state(
        db,
        run,
        RunState.FAILED,
        "run_failed",
        {
            "source": "harness_fail",
            "reason": reason,
            "error_code": parsed_error_code,
            "end_reason": end_reason,
            "end_source": end_source,
        },
    )
    if loop_guard_detail is not None:
        if reason:
            loop_guard_detail["reason"] = reason
        await append_run_event(
            db,
            run_id,
            "loop_guard_triggered",
            loop_guard_detail,
        )
    run.error_code = parsed_error_code
    run.end_reason = end_reason
    run.end_source = end_source
    run.summary = reason
    await release_run_sip_slot_if_held(
        db,
        run,
        redis_pool=redis_pool_from_request(request),
        slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
        release_sip_slot=release_sip_slot,
        reason="run_fail",
    )
    if run.livekit_room:
        room_name = run.livekit_room
        try:
            await delete_livekit_room(room_name)
            await append_run_event(
                db,
                run_id,
                "run_room_deleted_on_fail",
                {"room": room_name},
            )
        except Exception:
            event_logger.warning(
                "run_room_delete_on_fail_failed",
                run_id=run_id,
                room=room_name,
            )
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
    schedule_outcome = await apply_schedule_run_outcome(
        request=request,
        db=db,
        run=run,
        terminal_state=RunState.FAILED,
    )
    audit_detail: dict[str, object] = {
        "error_code": parsed_error_code,
        "end_reason": end_reason,
        "end_source": end_source,
        "reason": reason,
    }
    if pack_aggregate.pack_run_id:
        audit_detail["pack_run_id"] = pack_aggregate.pack_run_id
        audit_detail["pack_aggregate_reason"] = pack_aggregate.reason
    if pack_aggregate.applied:
        audit_detail["pack_item_state"] = pack_aggregate.item_state
        audit_detail["pack_run_state"] = pack_aggregate.pack_run_state
    if schedule_outcome.applied:
        audit_detail["schedule_outcome"] = schedule_outcome.outcome
        audit_detail["schedule_consecutive_failures"] = schedule_outcome.consecutive_failures
        if schedule_outcome.retry_outcome is not None:
            audit_detail["schedule_retry_outcome"] = schedule_outcome.retry_outcome
        if schedule_outcome.retry_run_id is not None:
            audit_detail["schedule_retry_run_id"] = schedule_outcome.retry_run_id
    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id="harness",
        actor_type="service",
        action="run.fail_callback",
        resource_type="run",
        resource_id=run_id,
        detail=audit_detail,
    )
    api_metrics.RUN_FAILURES_TOTAL.labels(
        source="harness",
        error_code=parsed_error_code,
    ).inc()
    await db.commit()
    event_logger.info(
        "run_marked_failed",
        run_id=run_id,
        tenant_id=run.tenant_id,
        reason=reason,
        error_code=parsed_error_code,
        end_reason=end_reason,
    )
    return {"ok": True, "state": "failed"}


async def _operator_finalize_run(
    *,
    run: RunRow,
    run_id: str,
    user: UserContext,
    request: Request,
    db: AsyncSession,
    target_state: RunState,
    source: str,
    event_type: str,
    action: str,
    reason: str,
    delete_room: bool,
) -> RunOperatorActionResponse:
    state = parse_run_state(run.state)
    if state in {RunState.FAILED, RunState.ERROR}:
        return RunOperatorActionResponse(
            run_id=run_id,
            applied=False,
            state=state.value,
            reason="already_terminal",
        )
    if state == RunState.COMPLETE:
        raise HTTPException(status_code=409, detail=f"Cannot modify run in state {state.value}")

    if delete_room and run.livekit_room:
        room_name = run.livekit_room
        try:
            await delete_livekit_room(room_name)
            await append_run_event(
                db,
                run_id,
                "run_room_delete_requested_by_operator",
                {"room": room_name},
            )
        except Exception:
            await append_run_event(
                db,
                run_id,
                "run_room_delete_failed_by_operator",
                {"room": room_name},
            )
            event_logger.exception(
                "run_room_delete_failed_by_operator",
                run_id=run_id,
                tenant_id=run.tenant_id,
                room=room_name,
            )

    error_code = ErrorCode.OPERATOR_ABORTED.value
    end_reason = EndReason.EXPLICIT_TERMINATION_REQUEST.value
    end_source = "operator"

    await transition_run_state(
        db,
        run,
        target_state,
        event_type,
        {
            "source": source,
            "reason": reason,
            "error_code": error_code,
            "end_reason": end_reason,
            "end_source": end_source,
        },
    )
    run.error_code = error_code
    run.end_reason = end_reason
    run.end_source = end_source
    run.summary = reason
    await release_run_sip_slot_if_held(
        db,
        run,
        redis_pool=redis_pool_from_request(request),
        slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
        release_sip_slot=release_sip_slot,
        reason="run_operator_action",
    )

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

    audit_detail: dict[str, object] = {
        "state": run.state,
        "error_code": error_code,
        "end_reason": end_reason,
        "end_source": end_source,
        "reason": reason,
    }
    if pack_aggregate.pack_run_id:
        audit_detail["pack_run_id"] = pack_aggregate.pack_run_id
        audit_detail["pack_aggregate_reason"] = pack_aggregate.reason
    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action=action,
        resource_type="run",
        resource_id=run_id,
        detail=audit_detail,
    )
    api_metrics.RUN_FAILURES_TOTAL.labels(
        source=source,
        error_code=error_code,
    ).inc()
    await db.commit()
    return RunOperatorActionResponse(
        run_id=run_id,
        applied=True,
        state=run.state,
        reason="applied",
    )


@router.post("/{run_id}/stop", response_model=RunOperatorActionResponse)
async def stop_run(
    run_id: str,
    request: Request,
    body: RunOperatorActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    reason = ((body.reason if body is not None else "") or "").strip() or "Run stopped by operator"
    return await _operator_finalize_run(
        run=run,
        run_id=run_id,
        user=user,
        request=request,
        db=db,
        target_state=RunState.ERROR,
        source="operator_stop",
        event_type="run_stopped_by_operator",
        action="run.operator_stopped",
        reason=reason,
        delete_room=True,
    )


@router.post("/{run_id}/mark-failed", response_model=RunOperatorActionResponse)
async def mark_run_failed_by_operator(
    run_id: str,
    request: Request,
    body: RunOperatorActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
):
    run = await get_run(db, run_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    reason = ((body.reason if body is not None else "") or "").strip() or "Run marked failed by operator"
    return await _operator_finalize_run(
        run=run,
        run_id=run_id,
        user=user,
        request=request,
        db=db,
        target_state=RunState.FAILED,
        source="operator_mark_failed",
        event_type="run_marked_failed_by_operator",
        action="run.operator_marked_failed",
        reason=reason,
        delete_room=False,
    )
