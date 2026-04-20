import logging
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import runs_lifecycle as _runs_lifecycle
from .runs import (
    RetentionSweepRequest,
    RetentionSweepResponse,
    RunReaperSweepRequest,
    RunReaperSweepResponse,
)
from .service import (
    EndReason,
    is_tts_cache_s3_key,
    parse_error_code,
    parse_run_state,
    redis_pool_from_request,
    run_effective_max_duration_s,
    run_elapsed_seconds,
    run_last_heartbeat_age_s,
    transition_run_state,
)
from .service_state import release_run_sip_slot_if_held
from .store_service import append_run_event, list_active_runs as list_active_run_rows
from .. import metrics as api_metrics
from ..audit import write_audit_event
from ..auth import get_service_caller
from ..config import settings
from ..database import get_db
from ..models import RunRow, RunState
from ..retention import build_retention_plan

logger = logging.getLogger("botcheck.api.runs")
event_logger = structlog.get_logger("botcheck.api.runs.lifecycle")
router = APIRouter()


# Wrappers preserve the existing test patch points on runs_lifecycle.
async def delete_report_artifact(*args, **kwargs):
    return await _runs_lifecycle.delete_report_artifact(*args, **kwargs)


async def livekit_room_exists(*args, **kwargs):
    return await _runs_lifecycle.livekit_room_exists(*args, **kwargs)


async def delete_livekit_room(*args, **kwargs):
    return await _runs_lifecycle.delete_livekit_room(*args, **kwargs)


async def release_sip_slot(*args, **kwargs):
    return await _runs_lifecycle.release_sip_slot(*args, **kwargs)


@router.post("/retention/sweep", response_model=RetentionSweepResponse)
async def sweep_retention(
    body: RetentionSweepRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """Judge-internal retention sweeper for transcript/artifact lifecycle controls."""
    if caller != "judge":
        raise HTTPException(status_code=403, detail="Only judge may run retention sweep")

    terminal_states = {
        RunState.COMPLETE.value,
        RunState.FAILED.value,
        RunState.ERROR.value,
    }
    rows = (
        (
            await db.execute(
                select(RunRow)
                .where(
                    RunRow.tenant_id == settings.tenant_id,
                    RunRow.state.in_(terminal_states),
                )
                .order_by(RunRow.created_at.asc())
                .limit(body.limit)
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    checked = len(rows)
    mutated = 0
    artifacts_deleted = 0
    artifacts_failed = 0

    for run in rows:
        plan = build_retention_plan(
            retention_profile=run.retention_profile or settings.default_retention_profile,
            created_at=run.created_at,
            has_artifact=bool(run.report_s3_key or run.recording_s3_key),
            has_transcript_data=bool(run.conversation or run.findings),
            now=now,
        )
        if not plan.has_action:
            continue

        mutated += 1
        artifact_delete_error: str | None = None
        artifact_deleted_this_run = False

        if not body.dry_run:
            if plan.delete_artifact and run.report_s3_key:
                if is_tts_cache_s3_key(run.report_s3_key):
                    logger.warning(
                        "Retention sweep skipped cache-key report artifact on run %s: %s",
                        run.run_id,
                        run.report_s3_key,
                    )
                else:
                    try:
                        await delete_report_artifact(settings, run.report_s3_key)
                        run.report_s3_key = None
                        artifacts_deleted += 1
                        artifact_deleted_this_run = True
                    except Exception as exc:
                        artifacts_failed += 1
                        artifact_delete_error = f"{type(exc).__name__}: {exc}"
            if plan.delete_artifact and run.recording_s3_key:
                if is_tts_cache_s3_key(run.recording_s3_key):
                    logger.warning(
                        "Retention sweep skipped cache-key recording artifact on run %s: %s",
                        run.run_id,
                        run.recording_s3_key,
                    )
                else:
                    try:
                        await delete_report_artifact(settings, run.recording_s3_key)
                        run.recording_s3_key = None
                        artifacts_deleted += 1
                        artifact_deleted_this_run = True
                    except Exception as exc:
                        artifacts_failed += 1
                        if artifact_delete_error is None:
                            artifact_delete_error = f"{type(exc).__name__}: {exc}"

            if plan.purge_transcript:
                run.conversation = []
                run.findings = []

            await append_run_event(
                db,
                run.run_id,
                "retention_sweep_applied",
                {
                    "source": "retention_sweeper",
                    "retention_profile": run.retention_profile,
                    "reason": plan.reason,
                    "purge_transcript": plan.purge_transcript,
                    "delete_artifact": plan.delete_artifact,
                    "artifact_deleted": artifact_deleted_this_run,
                    "artifact_delete_error": artifact_delete_error,
                },
            )

    return RetentionSweepResponse(
        dry_run=body.dry_run,
        checked=checked,
        mutated=mutated,
        artifacts_deleted=artifacts_deleted,
        artifacts_failed=artifacts_failed,
    )


@router.post("/reaper/sweep", response_model=RunReaperSweepResponse)
async def sweep_run_reaper(
    body: RunReaperSweepRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    """Judge-internal run-state reconciler that force-closes orphaned/overdue active runs."""
    if caller != "judge":
        raise HTTPException(status_code=403, detail="Only judge may run reaper sweep")

    rows = await list_active_run_rows(db, settings.tenant_id, limit=body.limit)
    now = datetime.now(UTC)
    checked = len(rows)
    overdue = 0
    heartbeat_stale = 0
    closed = 0
    room_active = 0
    room_missing = 0
    livekit_errors = 0
    sip_slots_released = 0
    close_errors = 0

    for run in rows:
        try:
            state = parse_run_state(run.state)
            elapsed_s = run_elapsed_seconds(run, now=now)
            max_duration_s = run_effective_max_duration_s(run)
            pending_stale_s = float(settings.run_pending_stale_s)
            overdue_threshold_s = pending_stale_s if state == RunState.PENDING else max_duration_s
            heartbeat_age_s = (
                run_last_heartbeat_age_s(run, now=now)
                if settings.run_heartbeat_enabled
                else None
            )
            is_heartbeat_stale = (
                isinstance(heartbeat_age_s, (int, float))
                and heartbeat_age_s >= settings.run_heartbeat_stale_s
            )
            if is_heartbeat_stale:
                heartbeat_stale += 1
                api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="heartbeat_stale").inc()
            overdue_candidate = elapsed_s > (overdue_threshold_s + body.grace_s)
            orphan_stale_candidate = (
                state == RunState.RUNNING
                and settings.run_heartbeat_enabled
                and is_heartbeat_stale
                and bool(run.livekit_room)
            )
            room_exists: bool | None = None
            if (overdue_candidate or orphan_stale_candidate) and run.livekit_room:
                try:
                    # Room existence check runs even in dry-run so callers get
                    # accurate room_active/room_missing counters.
                    room_exists = await livekit_room_exists(run.livekit_room)
                except Exception:
                    room_exists = None
                    livekit_errors += 1
                    api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="livekit_error").inc()
                    event_logger.warning(
                        "reaper_room_existence_check_failed",
                        run_id=run.run_id,
                        tenant_id=run.tenant_id,
                        room=run.livekit_room,
                        exc_info=True,
                    )
            if room_exists:
                room_active += 1
                api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="room_active").inc()
            elif room_exists is False:
                room_missing += 1
                api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="room_missing").inc()

            orphan_stale_close = not overdue_candidate and orphan_stale_candidate and room_exists is False
            if not overdue_candidate and not orphan_stale_close:
                outcome = "pending_not_overdue" if state == RunState.PENDING else "not_overdue"
                api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome=outcome).inc()
                continue

            if overdue_candidate:
                overdue += 1
            if orphan_stale_close:
                api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="orphan_stale").inc()

            if body.dry_run:
                continue

            # If room still exists, attempt best-effort room deletion before closure.
            if room_exists and run.livekit_room:
                try:
                    await delete_livekit_room(run.livekit_room)
                except Exception:
                    livekit_errors += 1
                    api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="livekit_error").inc()
                    event_logger.warning(
                        "reaper_room_delete_failed",
                        run_id=run.run_id,
                        tenant_id=run.tenant_id,
                        room=run.livekit_room,
                        exc_info=True,
                    )

            if state == RunState.PENDING:
                end_reason = EndReason.TIMEOUT_ORPHAN.value
                event_type = "run_reaped_pending_timeout"
            elif orphan_stale_close:
                end_reason = EndReason.TIMEOUT_ORPHAN.value
                event_type = "run_reaped_orphan_stale"
            else:
                end_reason = EndReason.MAX_DURATION_EXCEEDED.value
                if room_exists is False:
                    end_reason = EndReason.TIMEOUT_ORPHAN.value
                event_type = (
                    "run_reaped_max_duration"
                    if end_reason == EndReason.MAX_DURATION_EXCEEDED.value
                    else "run_reaped_orphan"
                )
            try:
                await transition_run_state(
                    db,
                    run,
                    RunState.ERROR,
                    event_type,
                    {
                        "source": "reaper",
                        "from_state": state.value,
                        "elapsed_s": round(elapsed_s, 3),
                        "max_duration_s": (max_duration_s if state == RunState.RUNNING else None),
                        "pending_stale_s": (
                            pending_stale_s if state == RunState.PENDING else None
                        ),
                        "grace_s": body.grace_s,
                        "room_exists": room_exists,
                        "heartbeat_stale": is_heartbeat_stale,
                        "heartbeat_age_s": (
                            round(float(heartbeat_age_s), 3)
                            if isinstance(heartbeat_age_s, (int, float))
                            else None
                        ),
                    },
                )
            except HTTPException as exc:
                if exc.status_code == 409:
                    await db.rollback()
                    continue
                raise
            run.end_reason = end_reason
            run.error_code = (
                parse_error_code("harness_timeout")
                if state == RunState.PENDING
                else (
                    parse_error_code("reaper_force_closed")
                    if end_reason == EndReason.MAX_DURATION_EXCEEDED.value
                    else parse_error_code("harness_timeout")
                )
            )
            run.end_source = "system"
            if state == RunState.PENDING:
                run.summary = (
                    "Run force-closed by reaper after pending start timeout "
                    f"(elapsed={elapsed_s:.1f}s, pending_stale={pending_stale_s:.1f}s, grace={body.grace_s:.1f}s)."
                )
            elif orphan_stale_close:
                run.summary = (
                    "Run force-closed by reaper after stale heartbeat and missing room "
                    f"(elapsed={elapsed_s:.1f}s, heartbeat_age={float(heartbeat_age_s or 0):.1f}s)."
                )
            else:
                run.summary = (
                    "Run force-closed by reaper after timeout budget exceeded "
                    f"(elapsed={elapsed_s:.1f}s, max_duration={max_duration_s:.1f}s, grace={body.grace_s:.1f}s)."
                )

            if run.transport == "sip" and run.sip_slot_held:
                try:
                    await release_run_sip_slot_if_held(
                        db,
                        run,
                        redis_pool=redis_pool_from_request(request),
                        slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
                        release_sip_slot=release_sip_slot,
                        reason="run_reaper",
                    )
                    sip_slots_released += 1
                except Exception:
                    event_logger.warning(
                        "reaper_sip_slot_release_failed",
                        run_id=run.run_id,
                        tenant_id=run.tenant_id,
                        exc_info=True,
                    )

            await write_audit_event(
                db,
                tenant_id=run.tenant_id,
                actor_id="reaper",
                actor_type="service",
                action="run.reaper_force_closed",
                resource_type="run",
                resource_id=run.run_id,
                detail={
                    "end_reason": end_reason,
                    "from_state": state.value,
                    "elapsed_s": round(elapsed_s, 3),
                    "max_duration_s": (max_duration_s if state == RunState.RUNNING else None),
                    "pending_stale_s": pending_stale_s if state == RunState.PENDING else None,
                    "grace_s": body.grace_s,
                    "room_exists": room_exists,
                    "heartbeat_stale": is_heartbeat_stale,
                    "heartbeat_age_s": (
                        round(float(heartbeat_age_s), 3)
                        if isinstance(heartbeat_age_s, (int, float))
                        else None
                    ),
                },
            )
            await db.commit()
            closed += 1
            api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="closed").inc()
        except Exception:
            await db.rollback()
            close_errors += 1
            api_metrics.RUN_REAPER_ACTIONS_TOTAL.labels(outcome="close_error").inc()
            event_logger.exception(
                "reaper_run_processing_failed",
                run_id=run.run_id,
                tenant_id=run.tenant_id,
            )

    return RunReaperSweepResponse(
        dry_run=body.dry_run,
        checked=checked,
        overdue=overdue,
        heartbeat_stale=heartbeat_stale,
        closed=closed,
        room_active=room_active,
        room_missing=room_missing,
        livekit_errors=livekit_errors,
        sip_slots_released=sip_slots_released,
        close_errors=close_errors,
    )
