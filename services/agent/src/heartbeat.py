from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import Awaitable, Callable


def heartbeat_sleep_s(
    *,
    interval_s: float,
    jitter_s: float,
    rand_uniform: Callable[[float, float], float] = random.uniform,
) -> float:
    if jitter_s <= 0:
        return max(1.0, interval_s)
    bounded_jitter = min(jitter_s, interval_s)
    return max(1.0, interval_s + rand_uniform(-bounded_jitter, bounded_jitter))


async def heartbeat_pump(
    *,
    run_id: str,
    stop_event: asyncio.Event,
    send_heartbeat_fn: Callable[[int, datetime], Awaitable[None]],
    interval_s: float,
    jitter_s: float,
    logger_obj,
) -> None:
    """Emit run heartbeat callbacks until stop_event is set.

    The first heartbeat is sent immediately so pending runs can transition to
    running quickly even if no turn callback is emitted yet.
    """
    seq = 1
    sent_first = False
    while not stop_event.is_set():
        if not sent_first:
            sent_at = datetime.now(UTC)
            try:
                await send_heartbeat_fn(seq, sent_at)
            except Exception:
                logger_obj.warning(
                    "run_heartbeat_send_failed",
                    run_id=run_id,
                    seq=seq,
                    exc_info=True,
                )
            seq += 1
            sent_first = True
            if stop_event.is_set():
                break

        sleep_s = heartbeat_sleep_s(interval_s=interval_s, jitter_s=jitter_s)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_s)
            break
        except asyncio.TimeoutError:
            pass

        sent_at = datetime.now(UTC)
        try:
            await send_heartbeat_fn(seq, sent_at)
        except Exception:
            logger_obj.warning(
                "run_heartbeat_send_failed",
                run_id=run_id,
                seq=seq,
                exc_info=True,
            )
        # Seq tracks attempted sends (not only acknowledged writes). This can
        # create gaps after transient failures, which is compatible with the
        # API contract: server applies updates only for seq > last_seq.
        seq += 1
