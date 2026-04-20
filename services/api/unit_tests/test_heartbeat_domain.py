"""Unit tests for heartbeat state transition semantics."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from botcheck_api.models import RunRow
from botcheck_api.runs.service import (
    HeartbeatStatus,
    apply_run_heartbeat,
    run_effective_max_duration_s,
    run_last_heartbeat_age_s,
)


def _run_row(*, state: str = "running", seq: int | None = None) -> RunRow:
    return RunRow(
        run_id="run_hb_unit",
        scenario_id="scenario-1",
        tenant_id="default",
        state=state,
        livekit_room="",
        trigger_source="manual",
        transport="none",
        last_heartbeat_seq=seq,
    )


def test_apply_run_heartbeat_updates_running_run() -> None:
    row = _run_row(state="running")
    received = datetime.now(UTC)

    status = apply_run_heartbeat(row, seq=1, received_at=received)

    assert status == HeartbeatStatus.UPDATED
    assert row.last_heartbeat_seq == 1
    assert row.last_heartbeat_at is not None
    assert row.last_heartbeat_at == received


def test_apply_run_heartbeat_ignores_duplicate_or_stale_seq() -> None:
    row = _run_row(state="running", seq=5)
    baseline = datetime.now(UTC) - timedelta(seconds=10)
    row.last_heartbeat_at = baseline

    duplicate = apply_run_heartbeat(row, seq=5, received_at=datetime.now(UTC))
    stale = apply_run_heartbeat(row, seq=4, received_at=datetime.now(UTC))

    assert duplicate == HeartbeatStatus.DUPLICATE_OR_STALE
    assert stale == HeartbeatStatus.DUPLICATE_OR_STALE
    assert row.last_heartbeat_seq == 5
    assert row.last_heartbeat_at == baseline


@pytest.mark.parametrize("state", ["judging", "complete", "failed", "error"])
def test_apply_run_heartbeat_returns_ignored_terminal(state: str) -> None:
    row = _run_row(state=state)

    status = apply_run_heartbeat(row, seq=1, received_at=datetime.now(UTC))

    assert status == HeartbeatStatus.IGNORED_TERMINAL
    assert row.last_heartbeat_seq is None
    assert row.last_heartbeat_at is None


def test_apply_run_heartbeat_rejects_non_running_pending() -> None:
    row = _run_row(state="pending")

    with pytest.raises(HTTPException) as exc_info:
        apply_run_heartbeat(row, seq=1, received_at=datetime.now(UTC))

    assert exc_info.value.status_code == 409
    assert "pending" in str(exc_info.value.detail)


def test_run_effective_max_duration_s_uses_default_when_runtime_snapshot_missing() -> None:
    row = _run_row(state="running")
    row.max_duration_s_at_start = None

    assert run_effective_max_duration_s(row) == 300.0


def test_run_last_heartbeat_age_s_returns_none_when_missing() -> None:
    row = _run_row(state="running")
    row.last_heartbeat_at = None

    assert run_last_heartbeat_age_s(row, now=datetime.now(UTC)) is None


def test_run_last_heartbeat_age_s_clamps_negative_skew_to_zero() -> None:
    row = _run_row(state="running")
    now = datetime.now(UTC)
    row.last_heartbeat_at = now + timedelta(seconds=5)

    assert run_last_heartbeat_age_s(row, now=now) == 0.0
