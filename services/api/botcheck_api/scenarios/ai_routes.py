from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_scenarios import ScenarioConfig

from ..audit import write_audit_event
from ..auth import UserContext, require_admin, require_viewer
from ..config import settings
from ..database import get_db
from ..exceptions import (
    AI_PERSONA_NOT_FOUND,
    AI_SCENARIO_NOT_FOUND,
    AI_SCENARIO_RECORD_NOT_FOUND,
    AI_SCENARIOS_DISABLED,
    ApiProblem,
    SCENARIO_NOT_FOUND,
)
from ..stt_provider import assert_tenant_stt_config_available
from ..tts_provider import assert_tenant_tts_voice_available
from .schemas import (
    AIPersonaDetailResponse,
    AIPersonaSummaryResponse,
    AIPersonaUpsertRequest,
    AIScenarioDetailResponse,
    AIScenarioRecordResponse,
    AIScenarioRecordUpsertRequest,
    AIScenarioSummaryResponse,
    AIScenarioUpsertRequest,
)
from .store_service import (
    ai_persona_in_use,
    create_or_replace_ai_persona as upsert_ai_persona,
    create_or_replace_ai_scenario as upsert_ai_scenario,
    create_or_replace_ai_scenario_record as upsert_ai_scenario_record,
    delete_ai_persona as delete_ai_persona_record,
    delete_ai_scenario as delete_ai_scenario_row,
    delete_ai_scenario_record as delete_ai_scenario_item_record,
    get_ai_persona as get_ai_persona_record,
    get_ai_scenario as get_ai_scenario_record,
    list_ai_personas as list_ai_persona_rows,
    list_ai_scenario_records as list_ai_scenario_record_rows,
    list_ai_scenarios as list_ai_scenario_rows,
    sanitize_ai_scenario_config,
)

router = APIRouter()


def _require_ai_scenarios_enabled() -> None:
    if not settings.feature_ai_scenarios_enabled:
        raise ApiProblem(
            status=503,
            error_code=AI_SCENARIOS_DISABLED,
            detail="AI scenarios are disabled",
        )


def _lookup_problem_for_detail(detail: str) -> ApiProblem:
    normalized = detail.strip().lower()
    if normalized == "ai persona not found":
        return ApiProblem(status=404, error_code=AI_PERSONA_NOT_FOUND, detail=detail)
    if normalized == "ai scenario not found":
        return ApiProblem(status=404, error_code=AI_SCENARIO_NOT_FOUND, detail=detail)
    if normalized == "ai scenario record not found":
        return ApiProblem(status=404, error_code=AI_SCENARIO_RECORD_NOT_FOUND, detail=detail)
    return ApiProblem(status=404, error_code=SCENARIO_NOT_FOUND, detail=detail)


async def _assert_ai_scenario_speech_config_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    config: dict[str, object],
    status_code: int,
) -> None:
    sanitized_config = sanitize_ai_scenario_config(config)
    tts_voice = sanitized_config.get("tts_voice")
    if isinstance(tts_voice, str) and tts_voice.strip():
        await assert_tenant_tts_voice_available(
            db,
            tenant_id=tenant_id,
            tts_voice=tts_voice,
            status_code=status_code,
            runtime_scope="agent",
        )
    if "stt_provider" in sanitized_config or "stt_model" in sanitized_config:
        default_config = ScenarioConfig()
        await assert_tenant_stt_config_available(
            db,
            tenant_id=tenant_id,
            stt_provider=str(sanitized_config.get("stt_provider", default_config.stt_provider)),
            stt_model=str(sanitized_config.get("stt_model", default_config.stt_model)),
            status_code=status_code,
            runtime_scope="agent",
        )


@router.get("/personas", response_model=list[AIPersonaSummaryResponse])
async def list_ai_personas(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_ai_scenarios_enabled()
    rows = await list_ai_persona_rows(db, user.tenant_id)
    return [
        AIPersonaSummaryResponse(
            persona_id=row.persona_id,
            name=row.name,
            display_name=row.display_name,
            avatar_url=row.avatar_url,
            backstory_summary=row.backstory_summary,
            style=row.style,
            voice=row.voice,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/personas", response_model=AIPersonaDetailResponse, status_code=201)
async def create_ai_persona(
    body: AIPersonaUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        stored = await upsert_ai_persona(
            db,
            tenant_id=user.tenant_id,
            persona_id=None,
            name=body.name.strip(),
            display_name=(body.display_name.strip() if body.display_name else None),
            avatar_url=(body.avatar_url.strip() if body.avatar_url else None),
            backstory_summary=(body.backstory_summary.strip() if body.backstory_summary else None),
            system_prompt=body.system_prompt.strip(),
            style=(body.style.strip() if body.style else None),
            voice=(body.voice.strip() if body.voice else None),
            is_active=bool(body.is_active),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_persona.create",
        resource_type="ai_persona",
        resource_id=stored.persona_id,
        detail={"name": stored.name},
    )
    await db.commit()
    return AIPersonaDetailResponse(
        persona_id=stored.persona_id,
        name=stored.name,
        display_name=stored.display_name,
        avatar_url=stored.avatar_url,
        backstory_summary=stored.backstory_summary,
        system_prompt=stored.system_prompt,
        style=stored.style,
        voice=stored.voice,
        is_active=stored.is_active,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.get("/personas/{persona_id}", response_model=AIPersonaDetailResponse)
async def get_ai_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_ai_scenarios_enabled()
    stored = await get_ai_persona_record(
        db,
        persona_id=persona_id,
        tenant_id=user.tenant_id,
    )
    if stored is None:
        raise ApiProblem(
            status=404,
            error_code=AI_PERSONA_NOT_FOUND,
            detail="AI persona not found",
        )
    return AIPersonaDetailResponse(
        persona_id=stored.persona_id,
        name=stored.name,
        display_name=stored.display_name,
        avatar_url=stored.avatar_url,
        backstory_summary=stored.backstory_summary,
        system_prompt=stored.system_prompt,
        style=stored.style,
        voice=stored.voice,
        is_active=stored.is_active,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.put("/personas/{persona_id}", response_model=AIPersonaDetailResponse)
async def update_ai_persona(
    persona_id: str,
    body: AIPersonaUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        stored = await upsert_ai_persona(
            db,
            tenant_id=user.tenant_id,
            persona_id=persona_id,
            name=body.name.strip(),
            display_name=(body.display_name.strip() if body.display_name else None),
            avatar_url=(body.avatar_url.strip() if body.avatar_url else None),
            backstory_summary=(body.backstory_summary.strip() if body.backstory_summary else None),
            system_prompt=body.system_prompt.strip(),
            style=(body.style.strip() if body.style else None),
            voice=(body.voice.strip() if body.voice else None),
            is_active=bool(body.is_active),
        )
    except LookupError as exc:
        raise ApiProblem(
            status=404,
            error_code=AI_PERSONA_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_persona.update",
        resource_type="ai_persona",
        resource_id=stored.persona_id,
        detail={"name": stored.name},
    )
    await db.commit()
    return AIPersonaDetailResponse(
        persona_id=stored.persona_id,
        name=stored.name,
        display_name=stored.display_name,
        avatar_url=stored.avatar_url,
        backstory_summary=stored.backstory_summary,
        system_prompt=stored.system_prompt,
        style=stored.style,
        voice=stored.voice,
        is_active=stored.is_active,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.delete("/personas/{persona_id}", status_code=204)
async def delete_ai_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    if await ai_persona_in_use(db, persona_id=persona_id, tenant_id=user.tenant_id):
        raise HTTPException(status_code=409, detail="AI persona is in use")
    try:
        deleted = await delete_ai_persona_record(
            db,
            persona_id=persona_id,
            tenant_id=user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise ApiProblem(
            status=404,
            error_code=AI_PERSONA_NOT_FOUND,
            detail="AI persona not found",
        )

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_persona.delete",
        resource_type="ai_persona",
        resource_id=persona_id,
        detail={},
    )
    await db.commit()


@router.get("/ai-scenarios", response_model=list[AIScenarioSummaryResponse])
async def list_ai_scenarios(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_ai_scenarios_enabled()
    rows = await list_ai_scenario_rows(db, user.tenant_id)
    return [
        AIScenarioSummaryResponse(
            ai_scenario_id=row.ai_scenario_id,
            scenario_id=row.scenario_id,
            name=row.name,
            namespace=row.namespace,
            persona_id=row.persona_id,
            scenario_brief=row.scenario_brief,
            scenario_facts=dict(row.scenario_facts),
            evaluation_objective=row.evaluation_objective,
            opening_strategy=row.opening_strategy,  # type: ignore[arg-type]
            is_active=row.is_active,
            scoring_profile=row.scoring_profile,
            dataset_source=row.dataset_source,
            record_count=row.record_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/ai-scenarios", response_model=AIScenarioDetailResponse, status_code=201)
async def create_ai_scenario(
    body: AIScenarioUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        config = dict(body.config or {})
        if body.ai_scenario_id:
            config["ai_scenario_id"] = body.ai_scenario_id.strip()
        await _assert_ai_scenario_speech_config_available(
            db,
            tenant_id=user.tenant_id,
            config=config,
            status_code=422,
        )
        stored = await upsert_ai_scenario(
            db,
            tenant_id=user.tenant_id,
            scenario_id=body.scenario_id.strip(),
            namespace=(body.namespace.strip() if body.namespace else None),
            persona_id=body.persona_id.strip(),
            name=(body.name.strip() if body.name else None),
            scenario_brief=(body.scenario_brief.strip() if body.scenario_brief else None),
            scenario_facts=dict(body.scenario_facts or {}),
            evaluation_objective=(
                body.evaluation_objective.strip() if body.evaluation_objective else None
            ),
            opening_strategy=body.opening_strategy,
            is_active=bool(body.is_active),
            scoring_profile=(body.scoring_profile.strip() if body.scoring_profile else None),
            dataset_source=(body.dataset_source.strip() if body.dataset_source else None),
            config=config,
        )
    except LookupError as exc:
        raise _lookup_problem_for_detail(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.create",
        resource_type="ai_scenario",
        resource_id=stored.ai_scenario_id,
        detail={"persona_id": stored.persona_id, "name": stored.name},
    )
    await db.commit()
    return AIScenarioDetailResponse(
        ai_scenario_id=stored.ai_scenario_id,
        scenario_id=stored.scenario_id,
        name=stored.name,
        namespace=stored.namespace,
        persona_id=stored.persona_id,
        scenario_brief=stored.scenario_brief,
        scenario_facts=dict(stored.scenario_facts),
        evaluation_objective=stored.evaluation_objective,
        opening_strategy=stored.opening_strategy,  # type: ignore[arg-type]
        is_active=stored.is_active,
        scoring_profile=stored.scoring_profile,
        dataset_source=stored.dataset_source,
        config=dict(stored.config),
        record_count=stored.record_count,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.get("/ai-scenarios/{ai_scenario_id}", response_model=AIScenarioDetailResponse)
async def get_ai_scenario(
    ai_scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_ai_scenarios_enabled()
    stored = await get_ai_scenario_record(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=user.tenant_id,
    )
    if stored is None:
        raise ApiProblem(
            status=404,
            error_code=AI_SCENARIO_NOT_FOUND,
            detail="AI scenario not found",
        )
    return AIScenarioDetailResponse(
        ai_scenario_id=stored.ai_scenario_id,
        scenario_id=stored.scenario_id,
        name=stored.name,
        namespace=stored.namespace,
        persona_id=stored.persona_id,
        scenario_brief=stored.scenario_brief,
        scenario_facts=dict(stored.scenario_facts),
        evaluation_objective=stored.evaluation_objective,
        opening_strategy=stored.opening_strategy,  # type: ignore[arg-type]
        is_active=stored.is_active,
        scoring_profile=stored.scoring_profile,
        dataset_source=stored.dataset_source,
        config=dict(stored.config),
        record_count=stored.record_count,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.put("/ai-scenarios/{ai_scenario_id}", response_model=AIScenarioDetailResponse)
async def update_ai_scenario(
    ai_scenario_id: str,
    body: AIScenarioUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        config = dict(body.config or {})
        config["ai_scenario_id"] = ai_scenario_id
        await _assert_ai_scenario_speech_config_available(
            db,
            tenant_id=user.tenant_id,
            config=config,
            status_code=422,
        )
        stored = await upsert_ai_scenario(
            db,
            tenant_id=user.tenant_id,
            scenario_id=body.scenario_id.strip(),
            namespace=(body.namespace.strip() if body.namespace else None),
            persona_id=body.persona_id.strip(),
            name=(body.name.strip() if body.name else None),
            scenario_brief=(body.scenario_brief.strip() if body.scenario_brief else None),
            scenario_facts=dict(body.scenario_facts or {}),
            evaluation_objective=(
                body.evaluation_objective.strip() if body.evaluation_objective else None
            ),
            opening_strategy=body.opening_strategy,
            is_active=bool(body.is_active),
            scoring_profile=(body.scoring_profile.strip() if body.scoring_profile else None),
            dataset_source=(body.dataset_source.strip() if body.dataset_source else None),
            config=config,
        )
    except LookupError as exc:
        raise _lookup_problem_for_detail(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.update",
        resource_type="ai_scenario",
        resource_id=stored.ai_scenario_id,
        detail={"persona_id": stored.persona_id, "name": stored.name},
    )
    await db.commit()
    return AIScenarioDetailResponse(
        ai_scenario_id=stored.ai_scenario_id,
        scenario_id=stored.scenario_id,
        name=stored.name,
        namespace=stored.namespace,
        persona_id=stored.persona_id,
        scenario_brief=stored.scenario_brief,
        scenario_facts=dict(stored.scenario_facts),
        evaluation_objective=stored.evaluation_objective,
        opening_strategy=stored.opening_strategy,  # type: ignore[arg-type]
        is_active=stored.is_active,
        scoring_profile=stored.scoring_profile,
        dataset_source=stored.dataset_source,
        config=dict(stored.config),
        record_count=stored.record_count,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.delete("/ai-scenarios/{ai_scenario_id}", status_code=204)
async def delete_ai_scenario(
    ai_scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    deleted = await delete_ai_scenario_row(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=user.tenant_id,
    )
    if not deleted:
        raise ApiProblem(
            status=404,
            error_code=AI_SCENARIO_NOT_FOUND,
            detail="AI scenario not found",
        )

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.delete",
        resource_type="ai_scenario",
        resource_id=ai_scenario_id,
        detail={},
    )
    await db.commit()


@router.get(
    "/ai-scenarios/{ai_scenario_id}/records",
    response_model=list[AIScenarioRecordResponse],
)
async def list_ai_scenario_records(
    ai_scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_ai_scenarios_enabled()
    scenario = await get_ai_scenario_record(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=user.tenant_id,
    )
    if scenario is None:
        raise ApiProblem(
            status=404,
            error_code=AI_SCENARIO_NOT_FOUND,
            detail="AI scenario not found",
        )
    rows = await list_ai_scenario_record_rows(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=user.tenant_id,
    )
    return [
        AIScenarioRecordResponse(
            record_id=row.record_id,
            ai_scenario_id=scenario.ai_scenario_id,
            order_index=row.order_index,
            input_text=row.input_text,
            expected_output=row.expected_output,
            metadata=row.metadata_json,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/ai-scenarios/{ai_scenario_id}/records",
    response_model=AIScenarioRecordResponse,
    status_code=201,
)
async def create_ai_scenario_record(
    ai_scenario_id: str,
    body: AIScenarioRecordUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        stored = await upsert_ai_scenario_record(
            db,
            ai_scenario_id=ai_scenario_id,
            tenant_id=user.tenant_id,
            record_id=None,
            order_index=body.order_index,
            input_text=body.input_text.strip(),
            expected_output=body.expected_output.strip(),
            metadata_json=dict(body.metadata or {}),
            is_active=bool(body.is_active),
        )
    except LookupError as exc:
        raise _lookup_problem_for_detail(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.record_create",
        resource_type="ai_scenario_record",
        resource_id=stored.record_id,
        detail={"ai_scenario_id": ai_scenario_id, "order_index": stored.order_index},
    )
    await db.commit()
    return AIScenarioRecordResponse(
        record_id=stored.record_id,
        ai_scenario_id=ai_scenario_id,
        order_index=stored.order_index,
        input_text=stored.input_text,
        expected_output=stored.expected_output,
        metadata=stored.metadata_json,
        is_active=stored.is_active,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.put(
    "/ai-scenarios/{ai_scenario_id}/records/{record_id}",
    response_model=AIScenarioRecordResponse,
)
async def update_ai_scenario_record(
    ai_scenario_id: str,
    record_id: str,
    body: AIScenarioRecordUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    try:
        stored = await upsert_ai_scenario_record(
            db,
            ai_scenario_id=ai_scenario_id,
            tenant_id=user.tenant_id,
            record_id=record_id,
            order_index=body.order_index,
            input_text=body.input_text.strip(),
            expected_output=body.expected_output.strip(),
            metadata_json=dict(body.metadata or {}),
            is_active=bool(body.is_active),
        )
    except LookupError as exc:
        raise _lookup_problem_for_detail(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.record_update",
        resource_type="ai_scenario_record",
        resource_id=stored.record_id,
        detail={"ai_scenario_id": ai_scenario_id, "order_index": stored.order_index},
    )
    await db.commit()
    return AIScenarioRecordResponse(
        record_id=stored.record_id,
        ai_scenario_id=ai_scenario_id,
        order_index=stored.order_index,
        input_text=stored.input_text,
        expected_output=stored.expected_output,
        metadata=stored.metadata_json,
        is_active=stored.is_active,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.delete("/ai-scenarios/{ai_scenario_id}/records/{record_id}", status_code=204)
async def delete_ai_scenario_record(
    ai_scenario_id: str,
    record_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
):
    _require_ai_scenarios_enabled()
    deleted = await delete_ai_scenario_item_record(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=user.tenant_id,
        record_id=record_id,
    )
    if not deleted:
        raise ApiProblem(
            status=404,
            error_code=AI_SCENARIO_RECORD_NOT_FOUND,
            detail="AI scenario record not found",
        )

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="ai_scenario.record_delete",
        resource_type="ai_scenario_record",
        resource_id=record_id,
        detail={"ai_scenario_id": ai_scenario_id},
    )
    await db.commit()
