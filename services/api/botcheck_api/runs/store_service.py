"""Runs feature store-service helpers.

Canonical home for run and schedule persistence helpers. Shared compatibility
facades may re-export these symbols while the feature-folder migration
completes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_runs as runs_repo
from ..models import RunRow, ScheduleRow


async def store_run(db: AsyncSession, run: RunRow) -> None:
    await runs_repo.add_run_row(db, run)


async def get_run(db: AsyncSession, run_id: str) -> RunRow | None:
    """Return run by ID with no tenant check.

    Only use for service-to-service callback paths where caller identity is
    already verified by service secret. Use get_run_for_tenant() for user APIs.
    """
    return await runs_repo.get_run_row(db, run_id)


async def list_running_runs(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int,
) -> list[RunRow]:
    return await runs_repo.list_running_run_rows_for_tenant(db, tenant_id, limit)


async def list_active_runs(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int,
) -> list[RunRow]:
    return await runs_repo.list_active_run_rows_for_tenant(db, tenant_id, limit)


async def get_run_for_tenant(
    db: AsyncSession,
    run_id: str,
    tenant_id: str,
) -> RunRow | None:
    row = await runs_repo.get_run_row(db, run_id)
    if row is None:
        return None
    if row.tenant_id != tenant_id:
        return None
    return row


async def update_run_state(db: AsyncSession, run_id: str, state: str) -> None:
    row = await runs_repo.get_run_row(db, run_id)
    if row is not None:
        runs_repo.update_run_state(row, state)


async def append_run_event(
    db: AsyncSession,
    run_id: str,
    event_type: str,
    detail: dict | None = None,
) -> None:
    row = await runs_repo.get_run_row(db, run_id)
    if row is None:
        return
    runs_repo.append_run_event(row, event_type, detail)


async def append_turn(db: AsyncSession, run_id: str, turn: dict) -> bool:
    row = await runs_repo.get_run_row(db, run_id)
    if row is None:
        return False
    return runs_repo.append_turn_dedup(row, turn)


async def store_schedule(db: AsyncSession, row: ScheduleRow) -> None:
    await runs_repo.add_schedule_row(db, row)


async def get_schedule_for_tenant(
    db: AsyncSession,
    schedule_id: str,
    tenant_id: str,
) -> ScheduleRow | None:
    return await runs_repo.get_schedule_row_for_tenant(db, schedule_id, tenant_id)


async def list_schedules(db: AsyncSession, tenant_id: str) -> list[ScheduleRow]:
    return await runs_repo.list_schedule_rows_for_tenant(db, tenant_id)


async def list_due_schedules(
    db: AsyncSession,
    tenant_id: str,
    now: datetime,
    limit: int,
) -> list[ScheduleRow]:
    return await runs_repo.list_due_schedules_for_tenant(db, tenant_id, now, limit)


async def list_runs_by_ids(
    db: AsyncSession,
    *,
    run_ids: list[str],
    tenant_id: str,
) -> list[RunRow]:
    return await runs_repo.list_run_rows_by_ids(db, run_ids, tenant_id=tenant_id)


__all__ = [
    "append_run_event",
    "append_turn",
    "get_run",
    "get_run_for_tenant",
    "get_schedule_for_tenant",
    "list_active_runs",
    "list_due_schedules",
    "list_running_runs",
    "list_runs_by_ids",
    "list_schedules",
    "store_run",
    "store_schedule",
    "update_run_state",
]
