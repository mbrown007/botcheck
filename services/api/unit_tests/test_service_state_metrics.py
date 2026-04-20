from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from botcheck_api import metrics as api_metrics
from botcheck_api.models import RunRow, RunState
from botcheck_api.runs import service_state


def _hist_count(histogram, **labels):
    labeled = histogram.labels(**labels)
    for metric in labeled.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    raise AssertionError("Histogram count sample not found")


def _run_row(*, state: str, transport: str = "sip", trigger_source: str = "manual") -> RunRow:
    return RunRow(
        run_id="run_test",
        scenario_id="scenario-test",
        tenant_id="tenant-test",
        state=state,
        livekit_room="room-test",
        transport=transport,
        trigger_source=trigger_source,
        events=[
            {
                "type": "run_created",
                "detail": {
                    "scenario_kind": "graph",
                    "sip_trunk_id": "trunk-uk-1",
                },
            }
        ],
        created_at=datetime.now(UTC) - timedelta(seconds=42),
    )


@pytest.mark.asyncio
async def test_transition_run_state_records_sip_answer_latency(monkeypatch) -> None:
    run = _run_row(state=RunState.PENDING.value, transport="sip")
    append_event = AsyncMock()
    monkeypatch.setattr(service_state, "append_run_event", append_event)
    before = _hist_count(
        api_metrics.SIP_ANSWER_LATENCY_SECONDS,
        trunk_id="trunk-uk-1",
    )

    await service_state.transition_run_state(
        db=object(),
        run=run,
        new_state=RunState.RUNNING,
        event_type="run_started",
        detail={"source": "test"},
    )

    assert run.run_started_at is not None
    assert (
        _hist_count(
            api_metrics.SIP_ANSWER_LATENCY_SECONDS,
            trunk_id="trunk-uk-1",
        )
        == before + 1
    )
    append_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_transition_run_state_records_run_e2e_latency(monkeypatch) -> None:
    run = _run_row(state=RunState.JUDGING.value, transport="mock", trigger_source="scheduled")
    append_event = AsyncMock()
    monkeypatch.setattr(service_state, "append_run_event", append_event)
    before = _hist_count(
        api_metrics.RUN_E2E_LATENCY_SECONDS,
        scenario_kind="graph",
        trigger_source="scheduled",
    )

    await service_state.transition_run_state(
        db=object(),
        run=run,
        new_state=RunState.COMPLETE,
        event_type="judge_completed",
        detail={"source": "judge"},
    )

    assert (
        _hist_count(
            api_metrics.RUN_E2E_LATENCY_SECONDS,
            scenario_kind="graph",
            trigger_source="scheduled",
        )
        == before + 1
    )
    append_event.assert_awaited_once()
