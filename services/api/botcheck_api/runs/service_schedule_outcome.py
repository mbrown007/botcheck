from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("botcheck.api.schedule_outcome")

from .. import metrics as api_metrics
from ..models import RetentionProfile, RunState, ScheduleRow, ScheduleTargetType
from .store_service import append_run_event, get_schedule_for_tenant
from .runs import RunCreate


@dataclass(slots=True)
class ScheduleRunOutcomeResult:
    applied: bool
    reason: str
    outcome: str | None = None
    consecutive_failures: int | None = None
    retry_attempted: bool = False
    retry_outcome: str | None = None
    retry_run_id: str | None = None


def _already_recorded(run_events: list[dict[str, Any]] | None) -> bool:
    for event in run_events or []:
        if event.get("type") == "schedule_outcome_recorded":
            return True
    return False


def _schedule_ai_scenario_id(overrides: dict[str, Any] | None) -> str | None:
    if not isinstance(overrides, dict):
        return None
    raw = overrides.get("ai_scenario_id")
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    return normalized or None


def _schedule_override_string(overrides: dict[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(overrides, dict):
        return None
    for key in keys:
        raw = overrides.get(key)
        if isinstance(raw, str):
            normalized = raw.strip()
            if normalized:
                return normalized
    return None


def _schedule_retry_allowed(*, row: ScheduleRow, run_state: RunState, triggered_by: str | None) -> bool:
    if row.target_type != ScheduleTargetType.SCENARIO.value:
        return False
    if not row.retry_on_failure:
        return False
    if run_state not in {RunState.FAILED, RunState.ERROR}:
        return False
    if isinstance(triggered_by, str) and triggered_by.endswith(":retry"):
        return False
    return True


async def apply_schedule_run_outcome(
    *,
    request: Request,
    db: AsyncSession,
    run: Any,
    terminal_state: RunState,
) -> ScheduleRunOutcomeResult:
    if not run.schedule_id:
        return ScheduleRunOutcomeResult(applied=False, reason="not_scheduled")
    if _already_recorded(run.events):
        return ScheduleRunOutcomeResult(applied=False, reason="already_recorded")

    schedule = await get_schedule_for_tenant(db, run.schedule_id, run.tenant_id)
    if schedule is None:
        return ScheduleRunOutcomeResult(applied=False, reason="schedule_missing")
    if schedule.target_type != ScheduleTargetType.SCENARIO.value:
        return ScheduleRunOutcomeResult(applied=False, reason="target_not_scenario")

    outcome = "success" if terminal_state == RunState.COMPLETE else terminal_state.value
    retry_outcome: str | None = None
    retry_run_id: str | None = None

    if outcome == "success":
        schedule.last_run_outcome = outcome
        schedule.consecutive_failures = 0
        api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL.labels(
            outcome=outcome,
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        ).inc()
        api_metrics.SCHEDULE_CONSECUTIVE_FAILURES.labels(
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        ).set(0)
    else:
        schedule.last_run_outcome = outcome
        schedule.consecutive_failures = int(schedule.consecutive_failures or 0) + 1
        api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL.labels(
            outcome=outcome,
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        ).inc()
        api_metrics.SCHEDULE_CONSECUTIVE_FAILURES.labels(
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        ).set(schedule.consecutive_failures)

        if _schedule_retry_allowed(
            row=schedule,
            run_state=terminal_state,
            triggered_by=run.triggered_by,
        ):
            retry_outcome = "skipped"
            retry_triggered_by = f"{(run.triggered_by or 'scheduler')}:retry"
            overrides = schedule.config_overrides or {}
            retention_value = _schedule_override_string(overrides, "retention_profile")
            retention_profile = (
                RetentionProfile(retention_value)
                if retention_value in {profile.value for profile in RetentionProfile}
                else RetentionProfile(run.retention_profile or RetentionProfile.STANDARD.value)
            )
            try:
                from .service_lifecycle import create_run_internal

                retry_run = await create_run_internal(
                    request=request,
                    body=RunCreate(
                        scenario_id=schedule.scenario_id,
                        ai_scenario_id=_schedule_ai_scenario_id(overrides),
                        destination_id=_schedule_override_string(
                            overrides,
                            "transport_profile_id",
                            "destination_id",
                        ),
                        transport_profile_id=_schedule_override_string(
                            overrides,
                            "transport_profile_id",
                            "destination_id",
                        ),
                        dial_target=_schedule_override_string(overrides, "dial_target", "bot_endpoint"),
                        bot_endpoint=_schedule_override_string(overrides, "dial_target", "bot_endpoint"),
                        retention_profile=retention_profile,
                    ),
                    tenant_id=run.tenant_id,
                    trigger_source="scheduled",
                    triggered_by=retry_triggered_by,
                    schedule_id=schedule.schedule_id,
                    db=db,
                    auto_commit=False,
                )
                retry_outcome = "dispatched"
                retry_run_id = retry_run.run_id
            except Exception:
                logger.exception(
                    "Schedule retry dispatch failed for schedule %s run %s",
                    schedule.schedule_id,
                    run.run_id,
                )
                retry_outcome = "failed"
            api_metrics.SCHEDULE_RETRY_TOTAL.labels(outcome=retry_outcome).inc()

    await append_run_event(
        db,
        run.run_id,
        "schedule_outcome_recorded",
        {
            "schedule_id": schedule.schedule_id,
            "outcome": outcome,
            "consecutive_failures": schedule.consecutive_failures,
            "retry_attempted": retry_outcome is not None,
            "retry_outcome": retry_outcome,
            "retry_run_id": retry_run_id,
        },
    )
    return ScheduleRunOutcomeResult(
        applied=True,
        reason="recorded",
        outcome=outcome,
        consecutive_failures=schedule.consecutive_failures,
        retry_attempted=retry_outcome is not None,
        retry_outcome=retry_outcome,
        retry_run_id=retry_run_id,
    )
