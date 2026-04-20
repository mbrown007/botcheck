from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..exceptions import (
    AI_SCENARIO_INACTIVE,
    AI_SCENARIO_NOT_FOUND,
    DESTINATION_NOT_FOUND,
    PRESET_NOT_FOUND,
    PRESET_INVALID_TRANSPORT_PROFILE,
    PRESET_NAME_CONFLICT,
    SCENARIO_NOT_FOUND,
    ApiProblem,
)
from ..models import DestinationProtocol, PlaygroundMode, PlaygroundPresetRow, ScenarioKind
from ..repo_runs import get_bot_destination_row_for_tenant
from ..repo_scenarios import (
    get_ai_scenario_row_by_ai_scenario_id_for_tenant,
    get_scenario_row_for_tenant,
)


def preset_not_found_problem(detail: str = "Playground preset not found") -> ApiProblem:
    return ApiProblem(status=404, error_code=PRESET_NOT_FOUND, detail=detail)


def preset_name_conflict_problem(
    detail: str = "Playground preset with that name already exists",
) -> ApiProblem:
    return ApiProblem(status=409, error_code=PRESET_NAME_CONFLICT, detail=detail)


async def list_playground_presets(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> list[PlaygroundPresetRow]:
    result = await db.execute(
        select(PlaygroundPresetRow)
        .where(PlaygroundPresetRow.tenant_id == tenant_id)
        .order_by(PlaygroundPresetRow.updated_at.desc(), PlaygroundPresetRow.created_at.desc())
    )
    return list(result.scalars().all())


async def get_playground_preset(
    db: AsyncSession,
    *,
    tenant_id: str,
    preset_id: str,
) -> PlaygroundPresetRow | None:
    result = await db.execute(
        select(PlaygroundPresetRow).where(
            PlaygroundPresetRow.tenant_id == tenant_id,
            PlaygroundPresetRow.preset_id == preset_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_preset_by_name(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
) -> PlaygroundPresetRow | None:
    result = await db.execute(
        select(PlaygroundPresetRow).where(
            PlaygroundPresetRow.tenant_id == tenant_id,
            PlaygroundPresetRow.name == name,
        )
    )
    return result.scalar_one_or_none()


async def _assert_target_exists(
    db: AsyncSession,
    *,
    tenant_id: str,
    scenario_id: str | None,
    ai_scenario_id: str | None,
) -> None:
    if scenario_id:
        scenario = await get_scenario_row_for_tenant(db, scenario_id=scenario_id, tenant_id=tenant_id)
        if scenario is None or str(scenario.scenario_kind).strip().lower() != ScenarioKind.GRAPH.value:
            raise ApiProblem(
                status=404,
                error_code=SCENARIO_NOT_FOUND,
                detail="Scenario not found",
            )
        return

    ai_scenario = await get_ai_scenario_row_by_ai_scenario_id_for_tenant(
        db,
        ai_scenario_id=ai_scenario_id or "",
        tenant_id=tenant_id,
    )
    if ai_scenario is None:
        raise ApiProblem(
            status=404,
            error_code=AI_SCENARIO_NOT_FOUND,
            detail="AI scenario not found",
        )
    if not bool(ai_scenario.is_active):
        raise ApiProblem(
            status=409,
            error_code=AI_SCENARIO_INACTIVE,
            detail="AI scenario is inactive",
        )


async def _assert_transport_profile_exists(
    db: AsyncSession,
    *,
    tenant_id: str,
    transport_profile_id: str | None,
) -> None:
    if not transport_profile_id:
        return
    destination = await get_bot_destination_row_for_tenant(
        db,
        destination_id=transport_profile_id,
        tenant_id=tenant_id,
    )
    if destination is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Transport profile not found",
        )
    if str(destination.protocol).strip().lower() != DestinationProtocol.HTTP.value:
        raise ApiProblem(
            status=422,
            error_code=PRESET_INVALID_TRANSPORT_PROFILE,
            detail="Transport profile must be an active HTTP transport profile",
        )
    if not bool(destination.is_active):
        raise ApiProblem(
            status=422,
            error_code=PRESET_INVALID_TRANSPORT_PROFILE,
            detail="Transport profile must be an active HTTP transport profile",
        )


async def _flush_or_raise_preset_integrity(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        text = str(getattr(exc, "orig", exc))
        if (
            "uq_playground_presets_tenant_name" in text
            or "playground_presets.tenant_id, playground_presets.name" in text
            or "UNIQUE constraint failed: playground_presets.tenant_id, playground_presets.name" in text
        ):
            raise preset_name_conflict_problem() from exc
        raise


async def create_playground_preset(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
    name: str,
    description: str | None,
    scenario_id: str | None,
    ai_scenario_id: str | None,
    playground_mode: PlaygroundMode,
    transport_profile_id: str | None,
    system_prompt: str | None,
    tool_stubs: dict[str, object] | None,
) -> PlaygroundPresetRow:
    existing = await _get_preset_by_name(db, tenant_id=tenant_id, name=name)
    if existing is not None:
        raise preset_name_conflict_problem()

    await _assert_target_exists(
        db,
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        ai_scenario_id=ai_scenario_id,
    )
    if playground_mode == PlaygroundMode.DIRECT_HTTP:
        await _assert_transport_profile_exists(
            db,
            tenant_id=tenant_id,
            transport_profile_id=transport_profile_id,
        )

    row = PlaygroundPresetRow(
        preset_id=f"preset_{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        name=name,
        description=description,
        scenario_id=scenario_id,
        ai_scenario_id=ai_scenario_id,
        playground_mode=playground_mode.value,
        transport_profile_id=transport_profile_id,
        system_prompt=system_prompt,
        tool_stubs=tool_stubs,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(row)
    await _flush_or_raise_preset_integrity(db)
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="playground.preset.create",
        resource_type="playground_preset",
        resource_id=row.preset_id,
        detail={
            "name": row.name,
            "scenario_id": row.scenario_id,
            "ai_scenario_id": row.ai_scenario_id,
            "playground_mode": row.playground_mode,
            "transport_profile_id": row.transport_profile_id,
            "has_tool_stubs": bool(row.tool_stubs),
        },
    )
    return row


async def update_playground_preset(
    db: AsyncSession,
    *,
    tenant_id: str,
    preset_id: str,
    actor_id: str,
    name: str,
    description: str | None,
    scenario_id: str | None,
    ai_scenario_id: str | None,
    playground_mode: PlaygroundMode,
    transport_profile_id: str | None,
    system_prompt: str | None,
    tool_stubs: dict[str, object] | None,
) -> PlaygroundPresetRow:
    row = await get_playground_preset(db, tenant_id=tenant_id, preset_id=preset_id)
    if row is None:
        raise preset_not_found_problem()

    existing = await _get_preset_by_name(db, tenant_id=tenant_id, name=name)
    if existing is not None and existing.preset_id != preset_id:
        raise preset_name_conflict_problem()

    await _assert_target_exists(
        db,
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        ai_scenario_id=ai_scenario_id,
    )
    if playground_mode == PlaygroundMode.DIRECT_HTTP:
        await _assert_transport_profile_exists(
            db,
            tenant_id=tenant_id,
            transport_profile_id=transport_profile_id,
        )

    detail: dict[str, object] = {}

    if row.name != name:
        detail["from_name"] = row.name
        detail["to_name"] = name
    if row.description != description:
        detail["from_description"] = row.description
        detail["to_description"] = description
    if row.scenario_id != scenario_id:
        detail["from_scenario_id"] = row.scenario_id
        detail["to_scenario_id"] = scenario_id
    if row.ai_scenario_id != ai_scenario_id:
        detail["from_ai_scenario_id"] = row.ai_scenario_id
        detail["to_ai_scenario_id"] = ai_scenario_id
    if row.playground_mode != playground_mode.value:
        detail["from_playground_mode"] = row.playground_mode
        detail["to_playground_mode"] = playground_mode.value
    if row.transport_profile_id != transport_profile_id:
        detail["from_transport_profile_id"] = row.transport_profile_id
        detail["to_transport_profile_id"] = transport_profile_id
    if row.system_prompt != system_prompt:
        detail["system_prompt_changed"] = True
    if row.tool_stubs != tool_stubs:
        detail["tool_stubs_changed"] = True

    row.name = name
    row.description = description
    row.scenario_id = scenario_id
    row.ai_scenario_id = ai_scenario_id
    row.playground_mode = playground_mode.value
    row.transport_profile_id = transport_profile_id
    row.system_prompt = system_prompt
    row.tool_stubs = tool_stubs
    row.updated_by = actor_id
    row.updated_at = datetime.now(UTC)
    await _flush_or_raise_preset_integrity(db)
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="playground.preset.update",
        resource_type="playground_preset",
        resource_id=row.preset_id,
        detail=detail or {"updated": True},
    )
    return row


async def delete_playground_preset(
    db: AsyncSession,
    *,
    tenant_id: str,
    preset_id: str,
    actor_id: str,
) -> None:
    row = await get_playground_preset(db, tenant_id=tenant_id, preset_id=preset_id)
    if row is None:
        raise preset_not_found_problem()

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="playground.preset.delete",
        resource_type="playground_preset",
        resource_id=row.preset_id,
        detail={
            "name": row.name,
            "scenario_id": row.scenario_id,
            "ai_scenario_id": row.ai_scenario_id,
            "playground_mode": row.playground_mode,
            "transport_profile_id": row.transport_profile_id,
        },
    )
    await db.delete(row)
