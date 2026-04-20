"""Scenario and AI scenario repository functions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AIPersonaRow,
    AIScenarioRecordRow,
    AIScenarioRow,
    CacheStatus,
    ScenarioKind,
    ScenarioRow,
    ScheduleRow,
)


_UNSET = object()


async def get_scenario_row_for_tenant(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> ScenarioRow | None:
    result = await db.execute(
        select(ScenarioRow).where(
            ScenarioRow.scenario_id == scenario_id,
            ScenarioRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_scenario_row_by_id(db: AsyncSession, scenario_id: str) -> ScenarioRow | None:
    return await db.get(ScenarioRow, scenario_id)


async def get_scenario_kind_for_tenant(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> str | None:
    result = await db.execute(
        select(ScenarioRow.scenario_kind).where(
            ScenarioRow.scenario_id == scenario_id,
            ScenarioRow.tenant_id == tenant_id,
        )
    )
    value = result.scalar_one_or_none()
    return str(value) if value is not None else None


async def list_scenario_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[ScenarioRow]:
    result = await db.execute(
        select(ScenarioRow)
        .where(ScenarioRow.tenant_id == tenant_id)
        .order_by(ScenarioRow.created_at.desc())
    )
    return result.scalars().all()


def create_scenario_row(
    *,
    scenario_id: str,
    tenant_id: str,
    scenario_kind: str = ScenarioKind.GRAPH.value,
    version_hash: str,
    name: str,
    namespace: str | None = None,
    scenario_type: str,
    yaml_content: str,
) -> ScenarioRow:
    return ScenarioRow(
        scenario_id=scenario_id,
        tenant_id=tenant_id,
        scenario_kind=scenario_kind,
        version_hash=version_hash,
        name=name,
        namespace=namespace,
        type=scenario_type,
        yaml_content=yaml_content,
        cache_status=CacheStatus.COLD.value,
    )


def update_scenario_row(
    row: ScenarioRow,
    *,
    version_hash: str,
    name: str,
    namespace: str | None | object = _UNSET,
    scenario_type: str,
    yaml_content: str,
) -> None:
    row.version_hash = version_hash
    row.name = name
    if namespace is not _UNSET:
        row.namespace = namespace if isinstance(namespace, str) else None
    row.type = scenario_type
    row.yaml_content = yaml_content
    row.cache_status = CacheStatus.COLD.value
    row.cache_updated_at = None


def update_scenario_cache_state(
    row: ScenarioRow,
    *,
    cache_status: str,
) -> None:
    row.cache_status = cache_status
    row.cache_updated_at = datetime.now(UTC)


async def add_scenario_row(db: AsyncSession, row: ScenarioRow) -> None:
    db.add(row)


async def delete_scenario_row_for_tenant(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> bool:
    row = await get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def count_schedules_for_scenario(
    db: AsyncSession,
    tenant_id: str,
    scenario_id: str,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(ScheduleRow)
        .where(
            ScheduleRow.tenant_id == tenant_id,
            ScheduleRow.scenario_id == scenario_id,
        )
    )
    return int(result.scalar_one() or 0)


async def add_ai_persona_row(db: AsyncSession, row: AIPersonaRow) -> None:
    db.add(row)


async def get_ai_persona_row_for_tenant(
    db: AsyncSession,
    persona_id: str,
    tenant_id: str,
) -> AIPersonaRow | None:
    result = await db.execute(
        select(AIPersonaRow).where(
            AIPersonaRow.persona_id == persona_id,
            AIPersonaRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_ai_persona_row_by_name_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
) -> AIPersonaRow | None:
    result = await db.execute(
        select(AIPersonaRow).where(
            AIPersonaRow.tenant_id == tenant_id,
            AIPersonaRow.name == name,
        )
    )
    return result.scalar_one_or_none()


async def list_ai_persona_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[AIPersonaRow]:
    result = await db.execute(
        select(AIPersonaRow)
        .where(AIPersonaRow.tenant_id == tenant_id)
        .order_by(AIPersonaRow.created_at.desc())
    )
    return result.scalars().all()


async def delete_ai_persona_row_for_tenant(
    db: AsyncSession,
    persona_id: str,
    tenant_id: str,
) -> bool:
    row = await get_ai_persona_row_for_tenant(db, persona_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def count_ai_scenarios_for_persona_for_tenant(
    db: AsyncSession,
    *,
    persona_id: str,
    tenant_id: str,
) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(AIScenarioRow)
        .where(
            AIScenarioRow.persona_id == persona_id,
            AIScenarioRow.tenant_id == tenant_id,
        )
    )
    return int(result.scalar_one() or 0)


async def add_ai_scenario_row(db: AsyncSession, row: AIScenarioRow) -> None:
    db.add(row)


async def get_ai_scenario_row_for_tenant(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> AIScenarioRow | None:
    result = await db.execute(
        select(AIScenarioRow).where(
            AIScenarioRow.scenario_id == scenario_id,
            AIScenarioRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_ai_scenario_row_by_ai_scenario_id_for_tenant(
    db: AsyncSession,
    ai_scenario_id: str,
    tenant_id: str,
) -> AIScenarioRow | None:
    result = await db.execute(
        select(AIScenarioRow).where(
            AIScenarioRow.ai_scenario_id == ai_scenario_id,
            AIScenarioRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_ai_scenario_rows_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> list[AIScenarioRow]:
    result = await db.execute(
        select(AIScenarioRow)
        .where(AIScenarioRow.tenant_id == tenant_id)
        .order_by(AIScenarioRow.created_at.desc())
    )
    return result.scalars().all()


async def list_ai_scenario_record_counts_for_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> dict[str, int]:
    result = await db.execute(
        select(
            AIScenarioRecordRow.scenario_id,
            func.count(AIScenarioRecordRow.record_id),
        )
        .where(AIScenarioRecordRow.tenant_id == tenant_id)
        .group_by(AIScenarioRecordRow.scenario_id)
    )
    return {str(scenario_id): int(count or 0) for scenario_id, count in result.all()}


async def delete_ai_scenario_row_for_tenant(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> bool:
    row = await get_ai_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def add_ai_scenario_record_row(db: AsyncSession, row: AIScenarioRecordRow) -> None:
    db.add(row)


async def get_ai_scenario_record_row_for_tenant(
    db: AsyncSession,
    record_id: str,
    tenant_id: str,
) -> AIScenarioRecordRow | None:
    result = await db.execute(
        select(AIScenarioRecordRow).where(
            AIScenarioRecordRow.record_id == record_id,
            AIScenarioRecordRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_ai_scenario_record_rows_for_scenario_for_tenant(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
) -> list[AIScenarioRecordRow]:
    result = await db.execute(
        select(AIScenarioRecordRow)
        .where(
            AIScenarioRecordRow.scenario_id == scenario_id,
            AIScenarioRecordRow.tenant_id == tenant_id,
        )
        .order_by(AIScenarioRecordRow.order_index.asc(), AIScenarioRecordRow.created_at.asc())
    )
    return result.scalars().all()


async def get_preferred_ai_scenario_record_row_for_scenario_for_tenant(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
) -> AIScenarioRecordRow | None:
    result = await db.execute(
        select(AIScenarioRecordRow)
        .where(
            AIScenarioRecordRow.scenario_id == scenario_id,
            AIScenarioRecordRow.tenant_id == tenant_id,
        )
        .order_by(
            AIScenarioRecordRow.is_active.desc(),
            AIScenarioRecordRow.order_index.asc(),
            AIScenarioRecordRow.created_at.asc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def delete_ai_scenario_record_row_for_tenant(
    db: AsyncSession,
    *,
    record_id: str,
    tenant_id: str,
) -> bool:
    row = await get_ai_scenario_record_row_for_tenant(db, record_id, tenant_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def delete_ai_scenario_record_rows_for_scenario_for_tenant(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
) -> None:
    await db.execute(
        delete(AIScenarioRecordRow).where(
            AIScenarioRecordRow.scenario_id == scenario_id,
            AIScenarioRecordRow.tenant_id == tenant_id,
        )
    )


async def list_scenario_rows_by_ids_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    scenario_ids: list[str],
) -> list[ScenarioRow]:
    if not scenario_ids:
        return []
    result = await db.execute(
        select(ScenarioRow).where(
            ScenarioRow.tenant_id == tenant_id,
            ScenarioRow.scenario_id.in_(scenario_ids),
        )
    )
    return result.scalars().all()
