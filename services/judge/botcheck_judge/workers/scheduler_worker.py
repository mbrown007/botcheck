"""ARQ worker for periodic scheduler and retention tasks.

Separated from judge_worker so schedule/retention cron jobs can scale
independently from CPU-heavy judge scoring workers.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from arq import cron
from arq.connections import RedisSettings as ArqRedisSettings

from ..config import settings

logger = logging.getLogger("botcheck.judge.scheduler")


def _api_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.judge_secret}"}


def _scheduler_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.scheduler_secret}"}


async def sweep_retention(ctx: dict) -> dict:
    """Periodic retention sweep for terminal runs."""
    if not settings.retention_sweep_enabled:
        return {"disabled": True}

    payload = {
        "dry_run": settings.retention_sweep_dry_run,
        "limit": settings.retention_sweep_limit,
    }
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
    ) as http:
        resp = await http.post("/runs/retention/sweep", json=payload)
        resp.raise_for_status()
        result = resp.json()
    logger.info("retention.sweep", extra=result)
    return result


async def reap_orphan_runs(ctx: dict) -> dict:
    """Periodic run-state reconciler for overdue runs stuck in RUNNING."""
    if not settings.run_reaper_enabled:
        return {"disabled": True}

    payload = {
        "dry_run": False,
        "limit": settings.run_reaper_limit,
        "grace_s": settings.run_reaper_grace_s,
    }
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
    ) as http:
        resp = await http.post("/runs/reaper/sweep", json=payload)
        resp.raise_for_status()
        result = resp.json()
    logger.info("runs.reaper", extra=result)
    return result


async def tick_schedules(ctx: dict) -> dict:
    """Periodic schedule dispatcher trigger."""
    if not settings.schedule_tick_enabled:
        return {"disabled": True}

    payload = {"limit": settings.schedule_tick_limit}
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_scheduler_headers(),
    ) as http:
        resp = await http.post("/schedules/dispatch-due", json=payload)
        resp.raise_for_status()
        result = resp.json()
    logger.info("schedules.tick", extra=result)
    return result


async def dispatch_pack_run(ctx: dict, *, payload: dict) -> dict:
    """Asynchronous pack dispatcher scaffold (Phase 9)."""
    pack_run_id = str(payload.get("pack_run_id") or "").strip()
    if not pack_run_id:
        raise ValueError("dispatch_pack_run requires pack_run_id")

    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_scheduler_headers(),
    ) as http:
        resp = await http.post(f"/packs/internal/{pack_run_id}/dispatch")
        resp.raise_for_status()
        result = resp.json()
    logger.info("packs.dispatch", extra=result)
    return result


def _redis_settings() -> ArqRedisSettings:
    p = urlparse(settings.redis_url)
    return ArqRedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int(p.path.lstrip("/") or 0),
    )


class WorkerSettings:
    functions = [sweep_retention, reap_orphan_runs, tick_schedules, dispatch_pack_run]
    cron_jobs = [
        cron(sweep_retention, minute={0, 15, 30, 45}),
        cron(reap_orphan_runs, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(tick_schedules, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
    queue_name = "arq:scheduler"
    redis_settings = _redis_settings()
    max_jobs = 5
    job_timeout = 120
