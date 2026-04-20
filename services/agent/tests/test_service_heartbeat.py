from __future__ import annotations

import threading
from datetime import datetime

from src import service_heartbeat


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[dict[str, object]] = []

    def warning(self, message: str, **kwargs: object) -> None:
        self.warnings.append({"message": message, **kwargs})


def test_run_service_heartbeat_loop_sends_immediately() -> None:
    logger = _Logger()
    stop_event = threading.Event()
    observed: list[datetime] = []

    async def _send_heartbeat(observed_at: datetime) -> None:
        observed.append(observed_at)
        stop_event.set()

    service_heartbeat.run_service_heartbeat_loop(
        stop_event=stop_event,
        send_heartbeat_fn=_send_heartbeat,
        interval_s=30.0,
        jitter_s=0.0,
        logger_obj=logger,
    )

    assert len(observed) == 1
    assert logger.warnings == []


def test_run_service_heartbeat_loop_logs_send_failures() -> None:
    logger = _Logger()
    stop_event = threading.Event()

    async def _send_heartbeat(_: datetime) -> None:
        stop_event.set()
        raise RuntimeError("network")

    service_heartbeat.run_service_heartbeat_loop(
        stop_event=stop_event,
        send_heartbeat_fn=_send_heartbeat,
        interval_s=30.0,
        jitter_s=0.0,
        logger_obj=logger,
    )

    assert len(logger.warnings) == 1
    assert logger.warnings[0]["message"] == "service_heartbeat_send_failed"
