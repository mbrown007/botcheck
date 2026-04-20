from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from botcheck_api import metrics as api_metrics
from botcheck_api.models import RunState, ScheduleTargetType

_stub_runs = types.ModuleType("botcheck_api.runs.runs")
_stub_runs.RunCreate = dict
sys.modules.setdefault("botcheck_api.runs.runs", _stub_runs)

from botcheck_api.runs import service_schedule_outcome
from botcheck_api.runs.service_schedule_outcome import apply_schedule_run_outcome


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


@pytest.mark.asyncio
async def test_apply_schedule_run_outcome_records_schedule_labeled_failure_metric(
    monkeypatch,
) -> None:
    schedule = SimpleNamespace(
        schedule_id="sched_123",
        tenant_id="tenant_a",
        target_type=ScheduleTargetType.SCENARIO.value,
        retry_on_failure=False,
        consecutive_failures=0,
        last_run_outcome=None,
        config_overrides=None,
        scenario_id="scenario_1",
    )
    run = SimpleNamespace(
        run_id="run_123",
        schedule_id=schedule.schedule_id,
        tenant_id="tenant_a",
        events=[],
        triggered_by="scheduler",
    )
    monkeypatch.setattr(
        service_schedule_outcome,
        "get_schedule_for_tenant",
        AsyncMock(return_value=schedule),
    )
    append_event = AsyncMock()
    monkeypatch.setattr(service_schedule_outcome, "append_run_event", append_event)

    before = _counter_value(
        api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL,
        outcome="failed",
        schedule_id=schedule.schedule_id,
        target_type=schedule.target_type,
    )

    result = await apply_schedule_run_outcome(
        request=SimpleNamespace(),
        db=SimpleNamespace(),
        run=run,
        terminal_state=RunState.FAILED,
    )

    assert result.applied is True
    assert result.outcome == "failed"
    assert result.consecutive_failures == 1
    assert (
        _counter_value(
            api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL,
            outcome="failed",
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        )
        == before + 1
    )
    append_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_schedule_run_outcome_records_schedule_labeled_success_metric(
    monkeypatch,
) -> None:
    schedule = SimpleNamespace(
        schedule_id="sched_456",
        tenant_id="tenant_a",
        target_type=ScheduleTargetType.SCENARIO.value,
        retry_on_failure=False,
        consecutive_failures=2,
        last_run_outcome="failed",
        config_overrides=None,
        scenario_id="scenario_1",
    )
    run = SimpleNamespace(
        run_id="run_456",
        schedule_id=schedule.schedule_id,
        tenant_id="tenant_a",
        events=[],
        triggered_by="scheduler",
    )
    monkeypatch.setattr(
        service_schedule_outcome,
        "get_schedule_for_tenant",
        AsyncMock(return_value=schedule),
    )
    append_event = AsyncMock()
    monkeypatch.setattr(service_schedule_outcome, "append_run_event", append_event)

    before = _counter_value(
        api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL,
        outcome="success",
        schedule_id=schedule.schedule_id,
        target_type=schedule.target_type,
    )

    result = await apply_schedule_run_outcome(
        request=SimpleNamespace(),
        db=SimpleNamespace(),
        run=run,
        terminal_state=RunState.COMPLETE,
    )

    assert result.applied is True
    assert result.outcome == "success"
    assert result.consecutive_failures == 0
    assert (
        _counter_value(
            api_metrics.SCHEDULE_RUN_OUTCOMES_TOTAL,
            outcome="success",
            schedule_id=schedule.schedule_id,
            target_type=schedule.target_type,
        )
        == before + 1
    )
    append_event.assert_awaited_once()
