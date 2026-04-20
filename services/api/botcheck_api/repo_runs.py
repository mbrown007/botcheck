"""Run and schedule repository functions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    BotDestinationRow,
    RunRow,
    RunState,
    ScheduleRow,
    SIPTrunkRow,
    TenantTrunkPoolRow,
    TrunkPoolMemberRow,
    TrunkPoolRow,
)


async def add_run_row(db: AsyncSession, run: RunRow) -> None:
    db.add(run)


async def get_run_row(db: AsyncSession, run_id: str) -> RunRow | None:
    return await db.get(RunRow, run_id)


async def list_running_run_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    limit: int,
) -> list[RunRow]:
    result = await db.execute(
        select(RunRow)
        .where(
            RunRow.tenant_id == tenant_id,
            RunRow.state == RunState.RUNNING.value,
        )
        .order_by(func.coalesce(RunRow.run_started_at, RunRow.created_at).asc())
        .limit(limit)
    )
    return result.scalars().all()


async def list_active_run_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    limit: int,
) -> list[RunRow]:
    result = await db.execute(
        select(RunRow)
        .where(
            RunRow.tenant_id == tenant_id,
            RunRow.state.in_((RunState.RUNNING.value, RunState.PENDING.value)),
        )
        .order_by(func.coalesce(RunRow.run_started_at, RunRow.created_at).asc())
        .limit(limit)
    )
    return result.scalars().all()


def update_run_state(row: RunRow, state: str) -> None:
    row.state = state
    row.updated_at = datetime.now(UTC)


def append_run_event(row: RunRow, event_type: str, detail: dict | None = None) -> None:
    event = {
        "ts": datetime.now(UTC).isoformat(),
        "type": event_type,
    }
    if detail:
        event["detail"] = detail
    row.events = [*(row.events or []), event]
    row.updated_at = datetime.now(UTC)


def append_turn_dedup(row: RunRow, turn: dict) -> bool:
    turn_key = (turn.get("turn_id"), turn.get("turn_number"))
    existing_keys = {(t.get("turn_id"), t.get("turn_number")) for t in (row.conversation or [])}
    if turn_key in existing_keys:
        return False

    row.conversation = [*(row.conversation or []), turn]
    row.updated_at = datetime.now(UTC)
    return True


async def add_schedule_row(db: AsyncSession, row: ScheduleRow) -> None:
    db.add(row)


async def get_schedule_row_for_tenant(
    db: AsyncSession,
    schedule_id: str,
    tenant_id: str,
) -> ScheduleRow | None:
    result = await db.execute(
        select(ScheduleRow).where(
            ScheduleRow.schedule_id == schedule_id,
            ScheduleRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_schedule_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[ScheduleRow]:
    result = await db.execute(
        select(ScheduleRow)
        .where(ScheduleRow.tenant_id == tenant_id)
        .order_by(ScheduleRow.created_at.desc())
    )
    return result.scalars().all()


async def list_active_schedule_ids_for_destination_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    destination_id: str,
) -> list[str]:
    result = await db.execute(
        select(ScheduleRow.schedule_id)
        .where(
            ScheduleRow.tenant_id == tenant_id,
            ScheduleRow.active.is_(True),
            ScheduleRow.config_overrides.is_not(None),
            ScheduleRow.config_overrides["destination_id"].as_string() == destination_id,
        )
        .order_by(ScheduleRow.created_at.desc())
    )
    return [str(schedule_id) for schedule_id in result.scalars().all()]


async def list_due_schedules_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    now: datetime,
    limit: int,
) -> list[ScheduleRow]:
    result = await db.execute(
        select(ScheduleRow)
        .where(
            ScheduleRow.tenant_id == tenant_id,
            ScheduleRow.active.is_(True),
            ScheduleRow.next_run_at.is_not(None),
            ScheduleRow.next_run_at <= now,
        )
        .order_by(ScheduleRow.next_run_at.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def list_run_rows_for_schedule(
    db: AsyncSession,
    schedule_id: str,
    tenant_id: str,
    limit: int = 100,
) -> list[RunRow]:
    result = await db.execute(
        select(RunRow)
        .where(
            RunRow.tenant_id == tenant_id,
            RunRow.schedule_id == schedule_id,
        )
        .order_by(RunRow.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def add_bot_destination_row(db: AsyncSession, row: BotDestinationRow) -> None:
    db.add(row)


async def get_bot_destination_row_for_tenant(
    db: AsyncSession,
    destination_id: str,
    tenant_id: str,
) -> BotDestinationRow | None:
    result = await db.execute(
        select(BotDestinationRow).where(
            BotDestinationRow.destination_id == destination_id,
            BotDestinationRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_bot_destination_row_by_name_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
) -> BotDestinationRow | None:
    result = await db.execute(
        select(BotDestinationRow).where(
            BotDestinationRow.tenant_id == tenant_id,
            BotDestinationRow.name == name,
        )
    )
    return result.scalar_one_or_none()


async def list_bot_destination_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[BotDestinationRow]:
    result = await db.execute(
        select(BotDestinationRow)
        .where(BotDestinationRow.tenant_id == tenant_id)
        .order_by(BotDestinationRow.created_at.desc())
    )
    return result.scalars().all()


async def delete_bot_destination_row_for_tenant(
    db: AsyncSession,
    destination_id: str,
    tenant_id: str,
) -> bool:
    row = await get_bot_destination_row_for_tenant(db, destination_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def upsert_sip_trunk_row(db: AsyncSession, row: SIPTrunkRow) -> None:
    db.add(row)


async def get_sip_trunk_row(
    db: AsyncSession,
    trunk_id: str,
) -> SIPTrunkRow | None:
    result = await db.execute(select(SIPTrunkRow).where(SIPTrunkRow.trunk_id == trunk_id))
    return result.scalar_one_or_none()


async def list_sip_trunk_rows(db: AsyncSession) -> list[SIPTrunkRow]:
    result = await db.execute(
        select(SIPTrunkRow).order_by(
            SIPTrunkRow.is_active.desc(),
            SIPTrunkRow.name.asc(),
            SIPTrunkRow.trunk_id.asc(),
        )
    )
    return result.scalars().all()


async def list_sip_trunks_for_ids(
    db: AsyncSession,
    trunk_ids: list[str],
) -> list[SIPTrunkRow]:
    if not trunk_ids:
        return []
    result = await db.execute(select(SIPTrunkRow).where(SIPTrunkRow.trunk_id.in_(trunk_ids)))
    return result.scalars().all()


async def get_trunk_pool_row(
    db: AsyncSession,
    trunk_pool_id: str,
) -> TrunkPoolRow | None:
    result = await db.execute(
        select(TrunkPoolRow).where(TrunkPoolRow.trunk_pool_id == trunk_pool_id)
    )
    return result.scalar_one_or_none()


async def get_active_tenant_trunk_pool_row(
    db: AsyncSession,
    *,
    tenant_id: str,
    trunk_pool_id: str,
) -> TenantTrunkPoolRow | None:
    result = await db.execute(
        select(TenantTrunkPoolRow).where(
            TenantTrunkPoolRow.tenant_id == tenant_id,
            TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id,
            TenantTrunkPoolRow.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def list_active_trunk_pool_members(
    db: AsyncSession,
    trunk_pool_id: str,
) -> list[TrunkPoolMemberRow]:
    result = await db.execute(
        select(TrunkPoolMemberRow)
        .where(
            TrunkPoolMemberRow.trunk_pool_id == trunk_pool_id,
            TrunkPoolMemberRow.is_active.is_(True),
        )
        .order_by(TrunkPoolMemberRow.priority.asc(), TrunkPoolMemberRow.trunk_id.asc())
    )
    return result.scalars().all()


async def list_run_rows_by_ids(
    db: AsyncSession,
    run_ids: list[str],
    *,
    tenant_id: str | None = None,
) -> list[RunRow]:
    if not run_ids:
        return []
    stmt = select(RunRow).where(RunRow.run_id.in_(run_ids))
    if tenant_id is not None:
        stmt = stmt.where(RunRow.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return result.scalars().all()
