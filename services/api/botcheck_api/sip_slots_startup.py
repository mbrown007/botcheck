from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Awaitable, Callable

from fastapi import FastAPI

from . import metrics as api_metrics
from .capacity import count_active_sip_slots

logger = logging.getLogger("botcheck.api.sip_slots_startup")


async def reconcile_sip_slots_active_gauge(*, redis_pool: object) -> int:
    ping_fn = getattr(redis_pool, "ping", None)
    if ping_fn is not None and callable(ping_fn):
        ping_result = ping_fn()
        if inspect.isawaitable(ping_result):
            ping_result = await ping_result
        if not ping_result:
            raise RuntimeError(f"Redis ping returned unexpected result: {ping_result!r}")

    active_slots = await count_active_sip_slots(redis_pool=redis_pool)
    api_metrics.SIP_SLOTS_ACTIVE.set(active_slots)
    return active_slots


async def attempt_sip_slot_reconciliation(
    app: FastAPI,
    *,
    create_pools_fn: Callable[[], Awaitable[tuple[object, object]]],
) -> bool:
    redis_pool = getattr(app.state, "arq_pool", None)
    cache_pool = getattr(app.state, "arq_cache_pool", None)

    if redis_pool is None or cache_pool is None:
        redis_pool, cache_pool = await create_pools_fn()
        app.state.arq_pool = redis_pool
        app.state.arq_cache_pool = cache_pool
        logger.info("ARQ pool connected to Redis during SIP slot gauge reconciliation")

    active_slots = await reconcile_sip_slots_active_gauge(redis_pool=redis_pool)
    app.state.sip_slots_reconcile_pending = False
    logger.info("SIP slot gauge reconciled from Redis", extra={"active_slots": active_slots})
    return True


async def retry_sip_slot_reconciliation_until_ready(
    app: FastAPI,
    *,
    create_pools_fn: Callable[[], Awaitable[tuple[object, object]]],
    retry_delay_s: float = 5.0,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_attempts: int | None = None,
) -> bool:
    attempts = 0
    while getattr(app.state, "sip_slots_reconcile_pending", False):
        attempts += 1
        try:
            return await attempt_sip_slot_reconciliation(
                app,
                create_pools_fn=create_pools_fn,
            )
        except Exception:
            logger.warning(
                "SIP slot gauge reconciliation deferred until Redis is ready",
                exc_info=True,
            )
            if max_attempts is not None and attempts >= max_attempts:
                return False
            await sleep_fn(retry_delay_s)
    return True
