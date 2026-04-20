"""Tests for heartbeat loop helpers."""

import asyncio
from datetime import UTC, datetime

from src import heartbeat


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[dict] = []

    def warning(self, _event: str, **kwargs) -> None:
        self.warnings.append(kwargs)


class TestHeartbeatSleep:
    def test_sleep_without_jitter(self):
        assert heartbeat.heartbeat_sleep_s(interval_s=30.0, jitter_s=0.0) == 30.0

    def test_sleep_with_jitter_bounds(self):
        assert (
            heartbeat.heartbeat_sleep_s(
                interval_s=30.0,
                jitter_s=5.0,
                rand_uniform=lambda _a, _b: -5.0,
            )
            == 25.0
        )
        assert (
            heartbeat.heartbeat_sleep_s(
                interval_s=30.0,
                jitter_s=5.0,
                rand_uniform=lambda _a, _b: 5.0,
            )
            == 35.0
        )


class TestHeartbeatPump:
    async def test_pump_sends_first_heartbeat_immediately(self, monkeypatch):
        monkeypatch.setattr(heartbeat, "heartbeat_sleep_s", lambda **_kwargs: 30.0)
        stop_event = asyncio.Event()
        logger = _Logger()
        sent: list[int] = []

        async def _send(seq: int, sent_at: datetime) -> None:
            del sent_at
            sent.append(seq)
            stop_event.set()

        await heartbeat.heartbeat_pump(
            run_id="run-heartbeat-immediate",
            stop_event=stop_event,
            send_heartbeat_fn=_send,
            interval_s=30.0,
            jitter_s=5.0,
            logger_obj=logger,
        )

        assert sent == [1]
        assert logger.warnings == []

    async def test_pump_sends_sequential_heartbeats_until_stopped(self, monkeypatch):
        monkeypatch.setattr(heartbeat, "heartbeat_sleep_s", lambda **_kwargs: 0.01)
        stop_event = asyncio.Event()
        logger = _Logger()
        sent: list[tuple[int, datetime]] = []

        async def _send(seq: int, sent_at: datetime) -> None:
            sent.append((seq, sent_at))
            if seq >= 3:
                stop_event.set()

        await heartbeat.heartbeat_pump(
            run_id="run-heartbeat",
            stop_event=stop_event,
            send_heartbeat_fn=_send,
            interval_s=30.0,
            jitter_s=5.0,
            logger_obj=logger,
        )

        assert [seq for seq, _ in sent] == [1, 2, 3]
        assert all(ts.tzinfo == UTC for _, ts in sent)
        assert logger.warnings == []

    async def test_pump_does_not_abort_on_send_error(self, monkeypatch):
        monkeypatch.setattr(heartbeat, "heartbeat_sleep_s", lambda **_kwargs: 0.01)
        stop_event = asyncio.Event()
        logger = _Logger()
        attempts = {"count": 0}

        async def _send(seq: int, sent_at: datetime) -> None:
            del sent_at
            attempts["count"] += 1
            if seq == 1:
                raise RuntimeError("transient network error")
            stop_event.set()

        await heartbeat.heartbeat_pump(
            run_id="run-heartbeat-error",
            stop_event=stop_event,
            send_heartbeat_fn=_send,
            interval_s=30.0,
            jitter_s=5.0,
            logger_obj=logger,
        )

        assert attempts["count"] == 2
        assert len(logger.warnings) == 1
