from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Awaitable, Callable

from .heartbeat import heartbeat_sleep_s


def run_service_heartbeat_loop(
    *,
    stop_event: threading.Event,
    send_heartbeat_fn: Callable[[datetime], Awaitable[None]],
    interval_s: float,
    jitter_s: float,
    logger_obj,
) -> None:
    """Emit process-level service heartbeat callbacks until stop_event is set."""

    while not stop_event.is_set():
        observed_at = datetime.now(UTC)
        try:
            asyncio.run(send_heartbeat_fn(observed_at))
        except Exception:
            logger_obj.warning(
                "service_heartbeat_send_failed",
                observed_at=observed_at.isoformat(),
                exc_info=True,
            )
        if stop_event.is_set():
            break
        sleep_s = heartbeat_sleep_s(interval_s=interval_s, jitter_s=jitter_s)
        if stop_event.wait(timeout=sleep_s):
            break
