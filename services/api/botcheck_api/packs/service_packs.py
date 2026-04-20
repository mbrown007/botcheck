"""Scenario pack CRUD business logic."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_packs as packs_repo
from .. import repo_scenarios as scenarios_repo
from ..models import ScenarioPackItemRow, ScenarioPackRow
from .service_models import StoredScenarioPack, StoredScenarioPackItem


def _as_stored_pack(
    row: ScenarioPackRow,
    items: list[ScenarioPackItemRow],
    ai_scenario_ids_by_scenario_id: dict[str, str] | None = None,
) -> StoredScenarioPack:
    ai_scenario_ids_by_scenario_id = ai_scenario_ids_by_scenario_id or {}
    return StoredScenarioPack(
        pack_id=row.pack_id,
        name=row.name,
        description=row.description,
        tags=[str(tag) for tag in (row.tags or [])],
        execution_mode=row.execution_mode,
        created_at=row.created_at,
        updated_at=row.updated_at,
        items=[
            StoredScenarioPackItem(
                scenario_id=item.scenario_id,
                ai_scenario_id=ai_scenario_ids_by_scenario_id.get(item.scenario_id),
                order_index=item.order_index,
            )
            for item in items
        ],
    )


async def list_scenario_packs(
    db: AsyncSession,
    tenant_id: str,
) -> list[StoredScenarioPack]:
    rows = await packs_repo.list_scenario_pack_rows_for_tenant(db, tenant_id)
    pack_ids = [row.pack_id for row in rows]
    item_rows = await packs_repo.list_scenario_pack_item_rows_for_packs(db, pack_ids)

    items_by_pack: dict[str, list[ScenarioPackItemRow]] = {pack_id: [] for pack_id in pack_ids}
    for item in item_rows:
        items_by_pack.setdefault(item.pack_id, []).append(item)
    ai_rows = await scenarios_repo.list_ai_scenario_rows_for_tenant(db, tenant_id)
    ai_scenario_ids_by_scenario_id = {
        ai_row.scenario_id: ai_row.ai_scenario_id for ai_row in ai_rows
    }

    return [
        _as_stored_pack(
            row,
            items_by_pack.get(row.pack_id, []),
            ai_scenario_ids_by_scenario_id,
        )
        for row in rows
    ]


async def get_scenario_pack(
    db: AsyncSession,
    pack_id: str,
    tenant_id: str,
) -> StoredScenarioPack | None:
    row = await packs_repo.get_scenario_pack_row_for_tenant(db, pack_id, tenant_id)
    if row is None:
        return None
    items = await packs_repo.list_scenario_pack_item_rows_for_pack(db, row.pack_id)
    ai_rows = await scenarios_repo.list_ai_scenario_rows_for_tenant(db, tenant_id)
    ai_scenario_ids_by_scenario_id = {
        ai_row.scenario_id: ai_row.ai_scenario_id for ai_row in ai_rows
    }
    return _as_stored_pack(row, items, ai_scenario_ids_by_scenario_id)


async def create_or_replace_scenario_pack(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    description: str | None,
    tags: list[str],
    execution_mode: str,
    scenario_ids: list[str],
    pack_id: str | None = None,
) -> StoredScenarioPack:
    normalized_ids = [scenario_id.strip() for scenario_id in scenario_ids if scenario_id.strip()]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("Duplicate scenario_id in pack items")

    row: ScenarioPackRow | None
    if pack_id is None:
        row = None
    else:
        row = await packs_repo.get_scenario_pack_row_for_tenant(db, pack_id, tenant_id)
        if row is None:
            raise LookupError("Pack not found")

    existing_scenarios = await scenarios_repo.list_scenario_rows_by_ids_for_tenant(
        db,
        tenant_id,
        normalized_ids,
    )
    existing_ids = {row.scenario_id for row in existing_scenarios}
    missing = sorted(set(normalized_ids) - existing_ids)
    if missing:
        raise LookupError(f"Scenario not found for tenant: {missing}")

    if row is None:
        row = ScenarioPackRow(
            pack_id=f"pack_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            description=description,
            tags=tags,
            execution_mode=execution_mode,
        )
        await packs_repo.add_scenario_pack_row(db, row)
    else:
        row.name = name
        row.description = description
        row.tags = tags
        row.execution_mode = execution_mode
        await packs_repo.delete_scenario_pack_item_rows_for_pack(db, row.pack_id)

    for index, scenario_id in enumerate(normalized_ids):
        item = ScenarioPackItemRow(
            item_id=f"pitem_{uuid4().hex[:12]}",
            pack_id=row.pack_id,
            scenario_id=scenario_id,
            order_index=index,
        )
        await packs_repo.add_scenario_pack_item_row(db, item)

    items = await packs_repo.list_scenario_pack_item_rows_for_pack(db, row.pack_id)
    ai_rows = await scenarios_repo.list_ai_scenario_rows_for_tenant(db, tenant_id)
    ai_scenario_ids_by_scenario_id = {
        ai_row.scenario_id: ai_row.ai_scenario_id for ai_row in ai_rows
    }
    return _as_stored_pack(row, items, ai_scenario_ids_by_scenario_id)


async def delete_scenario_pack(
    db: AsyncSession,
    pack_id: str,
    tenant_id: str,
) -> bool:
    row = await packs_repo.get_scenario_pack_row_for_tenant(db, pack_id, tenant_id)
    if row is None:
        return False
    await packs_repo.delete_scenario_pack_item_rows_for_pack(db, row.pack_id)
    return await packs_repo.delete_scenario_pack_row_for_tenant(db, pack_id, tenant_id)


async def has_active_pack_runs_for_pack(
    db: AsyncSession,
    *,
    pack_id: str,
    tenant_id: str,
) -> bool:
    count = await packs_repo.count_active_pack_runs_for_pack(
        db,
        tenant_id=tenant_id,
        pack_id=pack_id,
    )
    return count > 0
