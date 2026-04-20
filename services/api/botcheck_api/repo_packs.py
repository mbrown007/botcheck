"""Pack and pack-run repository functions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    PackRunItemRow,
    PackRunRow,
    PackRunState,
    ScenarioPackItemRow,
    ScenarioPackRow,
)


async def add_scenario_pack_row(db: AsyncSession, row: ScenarioPackRow) -> None:
    db.add(row)


async def get_scenario_pack_row_for_tenant(
    db: AsyncSession,
    pack_id: str,
    tenant_id: str,
) -> ScenarioPackRow | None:
    result = await db.execute(
        select(ScenarioPackRow).where(
            ScenarioPackRow.pack_id == pack_id,
            ScenarioPackRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_scenario_pack_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[ScenarioPackRow]:
    result = await db.execute(
        select(ScenarioPackRow)
        .where(ScenarioPackRow.tenant_id == tenant_id)
        .order_by(ScenarioPackRow.created_at.desc())
    )
    return result.scalars().all()


async def delete_scenario_pack_row_for_tenant(
    db: AsyncSession,
    pack_id: str,
    tenant_id: str,
) -> bool:
    row = await get_scenario_pack_row_for_tenant(db, pack_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def count_active_pack_runs_for_pack(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(PackRunRow)
        .where(
            PackRunRow.tenant_id == tenant_id,
            PackRunRow.pack_id == pack_id,
            PackRunRow.state.in_(["pending", "running"]),
        )
    )
    return int(result.scalar_one() or 0)


async def add_scenario_pack_item_row(db: AsyncSession, row: ScenarioPackItemRow) -> None:
    db.add(row)


async def list_scenario_pack_item_rows_for_pack(
    db: AsyncSession,
    pack_id: str,
) -> list[ScenarioPackItemRow]:
    result = await db.execute(
        select(ScenarioPackItemRow)
        .where(ScenarioPackItemRow.pack_id == pack_id)
        .order_by(ScenarioPackItemRow.order_index.asc())
    )
    return result.scalars().all()


async def list_scenario_pack_item_rows_for_packs(
    db: AsyncSession,
    pack_ids: list[str],
) -> list[ScenarioPackItemRow]:
    if not pack_ids:
        return []
    result = await db.execute(
        select(ScenarioPackItemRow)
        .where(ScenarioPackItemRow.pack_id.in_(pack_ids))
        .order_by(ScenarioPackItemRow.pack_id.asc(), ScenarioPackItemRow.order_index.asc())
    )
    return result.scalars().all()


async def delete_scenario_pack_item_rows_for_pack(
    db: AsyncSession,
    pack_id: str,
) -> None:
    await db.execute(delete(ScenarioPackItemRow).where(ScenarioPackItemRow.pack_id == pack_id))


async def add_pack_run_row(db: AsyncSession, row: PackRunRow) -> None:
    db.add(row)


async def add_pack_run_item_row(db: AsyncSession, row: PackRunItemRow) -> None:
    db.add(row)


async def get_pack_run_row(db: AsyncSession, pack_run_id: str) -> PackRunRow | None:
    return await db.get(PackRunRow, pack_run_id)


async def get_pack_run_row_for_tenant(
    db: AsyncSession,
    pack_run_id: str,
    tenant_id: str,
) -> PackRunRow | None:
    result = await db.execute(
        select(PackRunRow).where(
            PackRunRow.pack_run_id == pack_run_id,
            PackRunRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_pack_run_by_idempotency(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str,
    idempotency_key: str,
) -> PackRunRow | None:
    result = await db.execute(
        select(PackRunRow)
        .where(
            PackRunRow.tenant_id == tenant_id,
            PackRunRow.pack_id == pack_id,
            PackRunRow.idempotency_key == idempotency_key,
            PackRunRow.state.in_(["pending", "running"]),
        )
        .order_by(PackRunRow.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_pack_run_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    *,
    pack_id: str | None = None,
    state: str | None = None,
    limit: int = 100,
) -> list[PackRunRow]:
    stmt = select(PackRunRow).where(PackRunRow.tenant_id == tenant_id)
    if pack_id:
        stmt = stmt.where(PackRunRow.pack_id == pack_id)
    if state:
        stmt = stmt.where(PackRunRow.state == state)
    result = await db.execute(stmt.order_by(PackRunRow.created_at.desc()).limit(limit))
    return result.scalars().all()


async def list_active_pack_run_ids_for_destination_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    destination_id: str,
) -> list[str]:
    result = await db.execute(
        select(PackRunRow.pack_run_id)
        .where(
            PackRunRow.tenant_id == tenant_id,
            PackRunRow.destination_id == destination_id,
            PackRunRow.state.in_([PackRunState.PENDING.value, PackRunState.RUNNING.value]),
        )
        .order_by(PackRunRow.created_at.desc())
    )
    return [str(pack_run_id) for pack_run_id in result.scalars().all()]


async def get_previous_pack_run_row_for_tenant_pack(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str,
    created_before: datetime,
    pack_run_id: str,
) -> PackRunRow | None:
    result = await db.execute(
        select(PackRunRow)
        .where(
            PackRunRow.tenant_id == tenant_id,
            PackRunRow.pack_id == pack_id,
            PackRunRow.pack_run_id != pack_run_id,
            or_(
                PackRunRow.created_at < created_before,
                and_(
                    PackRunRow.created_at == created_before,
                    PackRunRow.pack_run_id < pack_run_id,
                ),
            ),
        )
        .order_by(PackRunRow.created_at.desc(), PackRunRow.pack_run_id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_pack_run_item_rows_for_pack_run(
    db: AsyncSession,
    pack_run_id: str,
) -> list[PackRunItemRow]:
    result = await db.execute(
        select(PackRunItemRow)
        .where(PackRunItemRow.pack_run_id == pack_run_id)
        .order_by(PackRunItemRow.order_index.asc())
    )
    return result.scalars().all()


async def get_pack_run_item_row_for_run_id(
    db: AsyncSession,
    run_id: str,
) -> PackRunItemRow | None:
    result = await db.execute(select(PackRunItemRow).where(PackRunItemRow.run_id == run_id))
    return result.scalar_one_or_none()


def update_pack_run_state(row: PackRunRow, state: str) -> None:
    row.state = state
    row.updated_at = datetime.now(UTC)
