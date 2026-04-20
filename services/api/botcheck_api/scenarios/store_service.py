"""Scenarios feature store-service helpers.

Canonical home for scenario, AI persona, AI scenario, and cache persistence
helpers. Shared compatibility facades may re-export these symbols while the
feature-folder migration completes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple
from uuid import uuid4

import yaml
from botcheck_scenarios import (
    ScenarioConfig,
    ScenarioDefinition,
    parse_stt_config,
    parse_tts_voice,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_scenarios as scenarios_repo
from ..models import (
    AIPersonaRow,
    AIScenarioRecordRow,
    AIScenarioRow,
    CacheStatus,
    ScenarioKind,
    ScenarioRow,
)


class StoredScenario(NamedTuple):
    scenario: ScenarioDefinition
    version_hash: str
    scenario_kind: str
    namespace: str | None
    created_at: datetime
    cache_status: str
    cache_updated_at: datetime | None


class ScenarioCacheRebuildRequest(NamedTuple):
    scenario_id: str
    tenant_id: str
    version_hash: str
    scenario_payload: dict[str, Any]


class ScenarioCacheSyncResult(NamedTuple):
    found: bool
    applied: bool
    reason: str
    cache_status: str


class StoredAIPersona(NamedTuple):
    persona_id: str
    tenant_id: str
    name: str
    display_name: str
    avatar_url: str | None
    backstory_summary: str | None
    system_prompt: str
    style: str | None
    voice: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StoredAIScenarioSummary(NamedTuple):
    scenario_id: str
    ai_scenario_id: str
    name: str
    namespace: str | None
    tenant_id: str
    persona_id: str
    scenario_brief: str
    scenario_facts: dict[str, Any]
    evaluation_objective: str
    opening_strategy: str
    is_active: bool
    scoring_profile: str | None
    dataset_source: str | None
    record_count: int
    created_at: datetime
    updated_at: datetime


class StoredAIScenario(NamedTuple):
    scenario_id: str
    ai_scenario_id: str
    name: str
    namespace: str | None
    tenant_id: str
    persona_id: str
    scenario_brief: str
    scenario_facts: dict[str, Any]
    evaluation_objective: str
    opening_strategy: str
    is_active: bool
    scoring_profile: str | None
    dataset_source: str | None
    config: dict[str, Any]
    record_count: int
    created_at: datetime
    updated_at: datetime


class StoredAIScenarioRecord(NamedTuple):
    record_id: str
    scenario_id: str
    tenant_id: str
    order_index: int
    input_text: str
    expected_output: str
    metadata_json: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


async def store_scenario(
    db: AsyncSession,
    scenario: ScenarioDefinition,
    version_hash: str,
    yaml_content: str,
    tenant_id: str,
) -> ScenarioRow:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario.id, tenant_id)
    if row is None:
        conflicting = await scenarios_repo.get_scenario_row_by_id(db, scenario.id)
        if conflicting is not None and conflicting.tenant_id != tenant_id:
            raise ValueError("Scenario tenant mismatch")
        row = scenarios_repo.create_scenario_row(
            scenario_id=scenario.id,
            tenant_id=tenant_id,
            version_hash=version_hash,
            name=scenario.name,
            namespace=scenario.namespace,
            scenario_type=scenario.type.value,
            yaml_content=yaml_content,
        )
        await scenarios_repo.add_scenario_row(db, row)
        return row

    scenarios_repo.update_scenario_row(
        row,
        version_hash=version_hash,
        name=scenario.name,
        namespace=scenario.namespace,
        scenario_type=scenario.type.value,
        yaml_content=yaml_content,
    )
    return row


async def get_scenario(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> tuple[ScenarioDefinition, str] | None:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    raw = yaml.safe_load(row.yaml_content)
    scenario = ScenarioDefinition.model_validate(raw)
    return scenario, row.version_hash


async def get_scenario_kind(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> str | None:
    return await scenarios_repo.get_scenario_kind_for_tenant(db, scenario_id, tenant_id)


async def get_scenario_yaml(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> str | None:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    return row.yaml_content


async def get_scenario_cache_status(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> str | None:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    return row.cache_status


async def reconcile_scenario_cache_status(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
    cache_status: str,
) -> str | None:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    if row.cache_status != cache_status:
        scenarios_repo.update_scenario_cache_state(row, cache_status=cache_status)
    return row.cache_status


async def list_scenarios(
    db: AsyncSession,
    tenant_id: str,
) -> list[StoredScenario]:
    rows = await scenarios_repo.list_scenario_rows_for_tenant(db, tenant_id)
    out: list[StoredScenario] = []
    for row in rows:
        raw = yaml.safe_load(row.yaml_content)
        scenario = ScenarioDefinition.model_validate(raw)
        out.append(
            StoredScenario(
                scenario=scenario,
                version_hash=row.version_hash,
                scenario_kind=row.scenario_kind,
                namespace=row.namespace,
                created_at=row.created_at,
                cache_status=row.cache_status,
                cache_updated_at=row.cache_updated_at,
            )
        )
    return out


async def delete_scenario(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> bool:
    return await scenarios_repo.delete_scenario_row_for_tenant(db, scenario_id, tenant_id)


def _as_stored_ai_persona(row: AIPersonaRow) -> StoredAIPersona:
    return StoredAIPersona(
        persona_id=row.persona_id,
        tenant_id=row.tenant_id,
        name=row.name,
        display_name=(row.display_name or row.name).strip() or row.name,
        avatar_url=row.avatar_url,
        backstory_summary=row.backstory_summary,
        system_prompt=row.system_prompt,
        style=row.style,
        voice=row.voice,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_ai_personas(
    db: AsyncSession,
    tenant_id: str,
) -> list[StoredAIPersona]:
    rows = await scenarios_repo.list_ai_persona_rows_for_tenant(db, tenant_id)
    return [_as_stored_ai_persona(row) for row in rows]


async def get_ai_persona(
    db: AsyncSession,
    *,
    persona_id: str,
    tenant_id: str,
) -> StoredAIPersona | None:
    row = await scenarios_repo.get_ai_persona_row_for_tenant(db, persona_id, tenant_id)
    if row is None:
        return None
    return _as_stored_ai_persona(row)


async def create_or_replace_ai_persona(
    db: AsyncSession,
    *,
    tenant_id: str,
    persona_id: str | None,
    name: str,
    display_name: str | None,
    avatar_url: str | None,
    backstory_summary: str | None,
    system_prompt: str,
    style: str | None,
    voice: str | None,
    is_active: bool,
) -> StoredAIPersona:
    row = None
    if persona_id:
        row = await scenarios_repo.get_ai_persona_row_for_tenant(db, persona_id, tenant_id)
        if row is None:
            raise LookupError("AI persona not found")
    existing_by_name = await scenarios_repo.get_ai_persona_row_by_name_for_tenant(
        db,
        tenant_id=tenant_id,
        name=name,
    )
    if existing_by_name is not None and (row is None or existing_by_name.persona_id != row.persona_id):
        raise ValueError("AI persona name already exists")

    if row is None:
        row = AIPersonaRow(
            persona_id=f"persona_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            display_name=(display_name or name),
            avatar_url=avatar_url,
            backstory_summary=backstory_summary,
            system_prompt=system_prompt,
            style=style,
            voice=voice,
            is_active=is_active,
        )
        await scenarios_repo.add_ai_persona_row(db, row)
    else:
        row.name = name
        row.display_name = display_name or name
        row.avatar_url = avatar_url
        row.backstory_summary = backstory_summary
        row.system_prompt = system_prompt
        row.style = style
        row.voice = voice
        row.is_active = is_active

    await db.flush()
    return _as_stored_ai_persona(row)


async def delete_ai_persona(
    db: AsyncSession,
    *,
    persona_id: str,
    tenant_id: str,
) -> bool:
    return await scenarios_repo.delete_ai_persona_row_for_tenant(db, persona_id, tenant_id)


async def ai_persona_in_use(
    db: AsyncSession,
    *,
    persona_id: str,
    tenant_id: str,
) -> bool:
    return (
        await scenarios_repo.count_ai_scenarios_for_persona_for_tenant(
            db,
            persona_id=persona_id,
            tenant_id=tenant_id,
        )
    ) > 0


def _normalize_ai_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_ai_facts(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_opening_strategy(value: object) -> str:
    candidate = str(value or "").strip()
    if candidate in {"wait_for_bot_greeting", "caller_opens"}:
        return candidate
    return "wait_for_bot_greeting"


def _normalize_namespace(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().strip("/")
    return normalized or None


_AI_SCENARIO_RUNTIME_CONFIG_KEYS = (
    "language",
    "stt_provider",
    "stt_model",
    "stt_endpointing_ms",
    "transcript_merge_window_s",
    "turn_timeout_s",
    "max_duration_s",
    "max_total_turns",
    "tts_voice",
)
_AI_SCENARIO_RUNTIME_CONFIG_DEFAULTS = ScenarioConfig().model_dump(
    include=set(_AI_SCENARIO_RUNTIME_CONFIG_KEYS)
)


def _normalize_ai_runtime_config_value(key: str, value: object) -> object | None:
    if key == "language":
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value:
            return None
    if key == "tts_voice":
        if not isinstance(value, str):
            return None
        try:
            normalized_tts_voice = parse_tts_voice(value).canonical
        except ValueError:
            return None
        if normalized_tts_voice == _AI_SCENARIO_RUNTIME_CONFIG_DEFAULTS[key]:
            return None
        return normalized_tts_voice
    try:
        validated = ScenarioConfig.model_validate({key: value})
    except ValidationError:
        return None
    normalized = getattr(validated, key)
    if normalized == _AI_SCENARIO_RUNTIME_CONFIG_DEFAULTS[key]:
        return None
    return normalized


def _sanitize_ai_scenario_config(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _AI_SCENARIO_RUNTIME_CONFIG_KEYS:
        if key in {"stt_provider", "stt_model"}:
            continue
        normalized = _normalize_ai_runtime_config_value(key, config.get(key))
        if normalized is None:
            continue
        out[key] = normalized

    raw_stt_provider = config.get("stt_provider")
    raw_stt_model = config.get("stt_model")
    if raw_stt_provider is not None or raw_stt_model is not None:
        try:
            parsed_stt = parse_stt_config(
                raw_stt_provider if isinstance(raw_stt_provider, str) else "",
                raw_stt_model if isinstance(raw_stt_model, str) else "",
            )
        except ValueError:
            return out
        if parsed_stt.provider != _AI_SCENARIO_RUNTIME_CONFIG_DEFAULTS["stt_provider"]:
            out["stt_provider"] = parsed_stt.provider
        if parsed_stt.model != _AI_SCENARIO_RUNTIME_CONFIG_DEFAULTS["stt_model"]:
            out["stt_model"] = parsed_stt.model
    return out


def sanitize_ai_scenario_config(config: dict[str, Any]) -> dict[str, Any]:
    return _sanitize_ai_scenario_config(config)


async def _get_ai_scenario_row_by_public_id(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
) -> AIScenarioRow | None:
    return await scenarios_repo.get_ai_scenario_row_by_ai_scenario_id_for_tenant(
        db,
        ai_scenario_id,
        tenant_id,
    )


def _stored_ai_scenario_from_row(
    *,
    row: AIScenarioRow,
    scenario_row_name: str | None,
    record_count: int,
) -> StoredAIScenario:
    config = dict(row.config or {})
    name = _normalize_ai_text(row.name) or (scenario_row_name or row.ai_scenario_id)
    return StoredAIScenario(
        ai_scenario_id=_normalize_ai_text(row.ai_scenario_id) or row.scenario_id,
        scenario_id=row.scenario_id,
        name=name,
        namespace=_normalize_namespace(row.namespace),
        tenant_id=row.tenant_id,
        persona_id=row.persona_id,
        scenario_brief=_normalize_ai_text(row.scenario_brief)
        or _normalize_ai_text(config.get("scenario_brief")),
        scenario_facts=_normalize_ai_facts(row.scenario_facts)
        or _normalize_ai_facts(config.get("scenario_facts")),
        evaluation_objective=_normalize_ai_text(row.evaluation_objective)
        or _normalize_ai_text(config.get("evaluation_objective")),
        opening_strategy=_normalize_opening_strategy(
            row.opening_strategy or config.get("opening_strategy")
        ),
        is_active=bool(row.is_active),
        scoring_profile=row.scoring_profile,
        dataset_source=row.dataset_source,
        config=_sanitize_ai_scenario_config(config),
        record_count=record_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_ai_scenarios(
    db: AsyncSession,
    tenant_id: str,
) -> list[StoredAIScenarioSummary]:
    ai_rows = await scenarios_repo.list_ai_scenario_rows_for_tenant(db, tenant_id)
    if not ai_rows:
        return []

    scenario_ids = [row.scenario_id for row in ai_rows]
    scenario_rows = await scenarios_repo.list_scenario_rows_by_ids_for_tenant(
        db,
        tenant_id,
        scenario_ids,
    )
    names_by_scenario_id = {row.scenario_id: row.name for row in scenario_rows}
    record_counts = await scenarios_repo.list_ai_scenario_record_counts_for_tenant(db, tenant_id)

    out: list[StoredAIScenarioSummary] = []
    for row in ai_rows:
        config = dict(row.config or {})
        name = _normalize_ai_text(row.name) or names_by_scenario_id.get(row.scenario_id, row.scenario_id)
        out.append(
            StoredAIScenarioSummary(
                scenario_id=row.scenario_id,
                ai_scenario_id=_normalize_ai_text(row.ai_scenario_id) or row.scenario_id,
                name=name,
                namespace=_normalize_namespace(row.namespace),
                tenant_id=row.tenant_id,
                persona_id=row.persona_id,
                scenario_brief=_normalize_ai_text(row.scenario_brief)
                or _normalize_ai_text(config.get("scenario_brief")),
                scenario_facts=_normalize_ai_facts(row.scenario_facts)
                or _normalize_ai_facts(config.get("scenario_facts")),
                evaluation_objective=_normalize_ai_text(row.evaluation_objective)
                or _normalize_ai_text(config.get("evaluation_objective")),
                opening_strategy=_normalize_opening_strategy(
                    row.opening_strategy or config.get("opening_strategy")
                ),
                is_active=bool(row.is_active),
                scoring_profile=row.scoring_profile,
                dataset_source=row.dataset_source,
                record_count=record_counts.get(row.scenario_id, 0),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return out


def _as_stored_ai_scenario_record(row: AIScenarioRecordRow) -> StoredAIScenarioRecord:
    return StoredAIScenarioRecord(
        record_id=row.record_id,
        scenario_id=row.scenario_id,
        tenant_id=row.tenant_id,
        order_index=row.order_index,
        input_text=row.input_text,
        expected_output=row.expected_output,
        metadata_json=dict(row.metadata_json or {}),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_ai_scenario(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
) -> StoredAIScenario | None:
    row = await _get_ai_scenario_row_by_public_id(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=tenant_id,
    )
    if row is None:
        return None
    scenario_row = await scenarios_repo.get_scenario_row_for_tenant(db, row.scenario_id, tenant_id)
    counts = await scenarios_repo.list_ai_scenario_record_counts_for_tenant(db, tenant_id)
    return _stored_ai_scenario_from_row(
        row=row,
        scenario_row_name=scenario_row.name if scenario_row is not None else None,
        record_count=counts.get(row.scenario_id, 0),
    )


async def get_ai_scenario_by_scenario_id(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
) -> StoredAIScenario | None:
    row = await scenarios_repo.get_ai_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    scenario_row = await scenarios_repo.get_scenario_row_for_tenant(db, row.scenario_id, tenant_id)
    counts = await scenarios_repo.list_ai_scenario_record_counts_for_tenant(db, tenant_id)
    return _stored_ai_scenario_from_row(
        row=row,
        scenario_row_name=scenario_row.name if scenario_row is not None else None,
        record_count=counts.get(row.scenario_id, 0),
    )


async def create_or_replace_ai_scenario(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
    namespace: str | None,
    persona_id: str,
    name: str | None,
    scenario_brief: str | None,
    scenario_facts: dict[str, Any],
    evaluation_objective: str | None,
    opening_strategy: str | None,
    is_active: bool,
    scoring_profile: str | None,
    dataset_source: str | None,
    config: dict[str, Any],
) -> StoredAIScenario:
    scenario_row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if scenario_row is None:
        raise LookupError("Scenario not found")
    persona_row = await scenarios_repo.get_ai_persona_row_for_tenant(db, persona_id, tenant_id)
    if persona_row is None:
        raise LookupError("AI persona not found")

    config_payload = dict(config or {})
    normalized_ai_scenario_id = _normalize_ai_text(config_payload.get("ai_scenario_id")) or scenario_id
    normalized_name = _normalize_ai_text(name) or _normalize_ai_text(config_payload.get("name"))
    normalized_namespace = _normalize_namespace(namespace)
    normalized_brief = _normalize_ai_text(scenario_brief) or _normalize_ai_text(
        config_payload.get("scenario_brief")
    )
    normalized_facts = scenario_facts or _normalize_ai_facts(config_payload.get("scenario_facts"))
    normalized_objective = _normalize_ai_text(evaluation_objective) or _normalize_ai_text(
        config_payload.get("evaluation_objective")
    )
    normalized_opening_strategy = _normalize_opening_strategy(
        opening_strategy or config_payload.get("opening_strategy")
    )
    sanitized_config = _sanitize_ai_scenario_config(config_payload)

    row = await scenarios_repo.get_ai_scenario_row_for_tenant(db, scenario_id, tenant_id)
    existing_by_public_id = await scenarios_repo.get_ai_scenario_row_by_ai_scenario_id_for_tenant(
        db,
        normalized_ai_scenario_id,
        tenant_id,
    )
    if existing_by_public_id is not None and (
        row is None or existing_by_public_id.scenario_id != row.scenario_id
    ):
        raise ValueError("AI scenario ID already exists")
    if row is None:
        row = AIScenarioRow(
            scenario_id=scenario_id,
            ai_scenario_id=normalized_ai_scenario_id,
            tenant_id=tenant_id,
            name=normalized_name or scenario_row.name or scenario_id,
            namespace=normalized_namespace,
            persona_id=persona_id,
            scenario_brief=normalized_brief,
            scenario_facts=normalized_facts,
            evaluation_objective=normalized_objective,
            opening_strategy=normalized_opening_strategy,
            is_active=is_active,
            scoring_profile=scoring_profile,
            dataset_source=dataset_source,
            config=sanitized_config,
        )
        await scenarios_repo.add_ai_scenario_row(db, row)
    else:
        row.ai_scenario_id = normalized_ai_scenario_id or _normalize_ai_text(row.ai_scenario_id) or row.scenario_id
        row.name = normalized_name or row.name or scenario_row.name or scenario_id
        row.namespace = normalized_namespace
        row.persona_id = persona_id
        row.scenario_brief = normalized_brief
        row.scenario_facts = normalized_facts
        row.evaluation_objective = normalized_objective
        row.opening_strategy = normalized_opening_strategy
        row.is_active = is_active
        row.scoring_profile = scoring_profile
        row.dataset_source = dataset_source
        row.config = sanitized_config

    scenario_row.scenario_kind = ScenarioKind.AI.value
    await db.flush()
    counts = await scenarios_repo.list_ai_scenario_record_counts_for_tenant(db, tenant_id)
    return StoredAIScenario(
        scenario_id=row.scenario_id,
        ai_scenario_id=_normalize_ai_text(row.ai_scenario_id) or row.scenario_id,
        name=_normalize_ai_text(row.name) or scenario_row.name or row.scenario_id,
        namespace=_normalize_namespace(row.namespace),
        tenant_id=row.tenant_id,
        persona_id=row.persona_id,
        scenario_brief=_normalize_ai_text(row.scenario_brief),
        scenario_facts=_normalize_ai_facts(row.scenario_facts),
        evaluation_objective=_normalize_ai_text(row.evaluation_objective),
        opening_strategy=_normalize_opening_strategy(row.opening_strategy),
        is_active=bool(row.is_active),
        scoring_profile=row.scoring_profile,
        dataset_source=row.dataset_source,
        config=_sanitize_ai_scenario_config(dict(row.config or {})),
        record_count=counts.get(row.scenario_id, 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def delete_ai_scenario(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
) -> bool:
    row = await _get_ai_scenario_row_by_public_id(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=tenant_id,
    )
    if row is None:
        return False
    await scenarios_repo.delete_ai_scenario_record_rows_for_scenario_for_tenant(
        db,
        scenario_id=row.scenario_id,
        tenant_id=tenant_id,
    )
    return await scenarios_repo.delete_ai_scenario_row_for_tenant(db, row.scenario_id, tenant_id)


async def list_ai_scenario_records(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
) -> list[StoredAIScenarioRecord]:
    row = await _get_ai_scenario_row_by_public_id(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=tenant_id,
    )
    if row is None:
        return []
    rows = await scenarios_repo.list_ai_scenario_record_rows_for_scenario_for_tenant(
        db,
        scenario_id=row.scenario_id,
        tenant_id=tenant_id,
    )
    return [_as_stored_ai_scenario_record(row) for row in rows]


async def get_preferred_ai_scenario_record_for_dispatch(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
) -> StoredAIScenarioRecord | None:
    row = await scenarios_repo.get_preferred_ai_scenario_record_row_for_scenario_for_tenant(
        db,
        scenario_id=scenario_id,
        tenant_id=tenant_id,
    )
    if row is None:
        return None
    return _as_stored_ai_scenario_record(row)


async def create_or_replace_ai_scenario_record(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
    record_id: str | None,
    order_index: int | None,
    input_text: str,
    expected_output: str,
    metadata_json: dict[str, Any],
    is_active: bool,
) -> StoredAIScenarioRecord:
    ai_scenario = await _get_ai_scenario_row_by_public_id(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=tenant_id,
    )
    if ai_scenario is None:
        raise LookupError("AI scenario not found")
    scenario_id = ai_scenario.scenario_id

    existing_rows = await scenarios_repo.list_ai_scenario_record_rows_for_scenario_for_tenant(
        db,
        scenario_id=scenario_id,
        tenant_id=tenant_id,
    )
    target_order_index = int(order_index or 0)
    if target_order_index <= 0:
        max_existing = max((row.order_index for row in existing_rows), default=0)
        target_order_index = max_existing + 1

    row = None
    if record_id:
        row = await scenarios_repo.get_ai_scenario_record_row_for_tenant(db, record_id, tenant_id)
        if row is None or row.scenario_id != scenario_id:
            raise LookupError("AI scenario record not found")

    for existing in existing_rows:
        if row is not None and existing.record_id == row.record_id:
            continue
        if existing.order_index == target_order_index:
            raise ValueError("AI scenario record order_index already exists")

    if row is None:
        row = AIScenarioRecordRow(
            record_id=f"airec_{uuid4().hex[:12]}",
            scenario_id=scenario_id,
            tenant_id=tenant_id,
            order_index=target_order_index,
            input_text=input_text,
            expected_output=expected_output,
            metadata_json=dict(metadata_json or {}),
            is_active=is_active,
        )
        await scenarios_repo.add_ai_scenario_record_row(db, row)
    else:
        row.order_index = target_order_index
        row.input_text = input_text
        row.expected_output = expected_output
        row.metadata_json = dict(metadata_json or {})
        row.is_active = is_active

    await db.flush()
    return _as_stored_ai_scenario_record(row)


async def delete_ai_scenario_record(
    db: AsyncSession,
    *,
    ai_scenario_id: str,
    tenant_id: str,
    record_id: str,
) -> bool:
    ai_scenario = await _get_ai_scenario_row_by_public_id(
        db,
        ai_scenario_id=ai_scenario_id,
        tenant_id=tenant_id,
    )
    if ai_scenario is None:
        return False
    row = await scenarios_repo.get_ai_scenario_record_row_for_tenant(db, record_id, tenant_id)
    if row is None or row.scenario_id != ai_scenario.scenario_id:
        return False
    await db.delete(row)
    return True


async def queue_scenario_cache_rebuild(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> ScenarioCacheRebuildRequest | None:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return None
    scenarios_repo.update_scenario_cache_state(
        row,
        cache_status=CacheStatus.WARMING.value,
    )
    raw = yaml.safe_load(row.yaml_content)
    scenario = ScenarioDefinition.model_validate(raw)
    return ScenarioCacheRebuildRequest(
        scenario_id=row.scenario_id,
        tenant_id=row.tenant_id,
        version_hash=row.version_hash,
        scenario_payload=scenario.model_dump(mode="json"),
    )


async def sync_scenario_cache_status(
    db: AsyncSession,
    *,
    scenario_id: str,
    tenant_id: str,
    scenario_version_hash: str,
    cache_status: str,
) -> ScenarioCacheSyncResult:
    row = await scenarios_repo.get_scenario_row_for_tenant(db, scenario_id, tenant_id)
    if row is None:
        return ScenarioCacheSyncResult(
            found=False,
            applied=False,
            reason="not_found",
            cache_status=CacheStatus.COLD.value,
        )
    if row.version_hash != scenario_version_hash:
        return ScenarioCacheSyncResult(
            found=True,
            applied=False,
            reason="version_mismatch",
            cache_status=row.cache_status,
        )
    scenarios_repo.update_scenario_cache_state(
        row,
        cache_status=cache_status,
    )
    return ScenarioCacheSyncResult(
        found=True,
        applied=True,
        reason="applied",
        cache_status=cache_status,
    )


async def has_schedules_for_scenario(
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
) -> bool:
    return (await scenarios_repo.count_schedules_for_scenario(db, tenant_id, scenario_id)) > 0


__all__ = [
    "ScenarioCacheRebuildRequest",
    "ScenarioCacheSyncResult",
    "StoredAIPersona",
    "StoredAIScenario",
    "StoredAIScenarioRecord",
    "StoredAIScenarioSummary",
    "StoredScenario",
    "ai_persona_in_use",
    "create_or_replace_ai_persona",
    "create_or_replace_ai_scenario",
    "create_or_replace_ai_scenario_record",
    "delete_ai_persona",
    "delete_ai_scenario",
    "delete_ai_scenario_record",
    "delete_scenario",
    "get_ai_persona",
    "get_preferred_ai_scenario_record_for_dispatch",
    "get_ai_scenario",
    "get_ai_scenario_by_scenario_id",
    "get_scenario",
    "get_scenario_cache_status",
    "reconcile_scenario_cache_status",
    "sanitize_ai_scenario_config",
    "get_scenario_kind",
    "get_scenario_yaml",
    "has_schedules_for_scenario",
    "list_ai_personas",
    "list_ai_scenario_records",
    "list_ai_scenarios",
    "list_scenarios",
    "queue_scenario_cache_rebuild",
    "store_scenario",
    "sync_scenario_cache_status",
]
