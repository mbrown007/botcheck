from __future__ import annotations

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import TenantProviderAssignmentRow
from botcheck_api.providers.service import ensure_provider_registry_seeded
from botcheck_api.scenarios import store_service as scenarios_store_service


def _persona_payload(name: str = "Persona A") -> dict:
    return {
        "name": name,
        "system_prompt": "Act as a realistic customer caller.",
        "style": "neutral",
        "voice": "alloy",
        "is_active": True,
    }


def _ai_scenario_payload(
    *,
    scenario_id: str,
    persona_id: str,
    ai_scenario_id: str | None = None,
    name: str = "Delayed Flight Support",
    namespace: str | None = None,
    scenario_brief: str = "Caller wants confirmation and support for a delayed flight.",
    evaluation_objective: str = "Confirm the delay and explain next steps clearly.",
    scoring_profile: str = "call-success",
    dataset_source: str = "manual",
    config: dict | None = None,
) -> dict:
    return {
        "ai_scenario_id": ai_scenario_id,
        "scenario_id": scenario_id,
        "persona_id": persona_id,
        "name": name,
        "namespace": namespace,
        "scenario_brief": scenario_brief,
        "scenario_facts": {"booking_ref": "ABC123", "airline": "Ryanair"},
        "evaluation_objective": evaluation_objective,
        "opening_strategy": "wait_for_bot_greeting",
        "is_active": True,
        "scoring_profile": scoring_profile,
        "dataset_source": dataset_source,
        "config": config
        or {
            "language": "en-GB",
            "stt_endpointing_ms": 600,
            "transcript_merge_window_s": 2.5,
            "turn_timeout_s": 30,
            "max_duration_s": 450,
            "max_total_turns": 9,
            "tts_voice": "openai:alloy",
            "stt_provider": "deepgram",
            "stt_model": "nova-2-phonecall",
        },
    }


def _record_payload(
    *,
    order_index: int | None = None,
    input_text: str = "I need a 2-bedroom apartment.",
    expected_output: str = "Recommend listings and ask follow-up questions.",
    is_active: bool = True,
) -> dict:
    payload = {
        "input_text": input_text,
        "expected_output": expected_output,
        "metadata": {"segment": "buyer"},
        "is_active": is_active,
    }
    if order_index is not None:
        payload["order_index"] = order_index
    return payload


async def _set_provider_assignment_enabled(*, tenant_id: str, provider_id: str, enabled: bool) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        await ensure_provider_registry_seeded(session, tenant_ids=[tenant_id])
        row = (
            await session.execute(
                select(TenantProviderAssignmentRow).where(
                    TenantProviderAssignmentRow.tenant_id == tenant_id,
                    TenantProviderAssignmentRow.provider_id == provider_id,
                )
            )
        ).scalar_one()
        row.enabled = enabled
        await session.commit()


async def test_ai_scenario_endpoints_require_feature_flag(
    client,
    uploaded_scenario,
    user_auth_headers,
):
    resp = await client.get("/scenarios/ai-scenarios", headers=user_auth_headers)
    assert resp.status_code == 503
    assert "AI scenarios are disabled" in resp.json()["detail"]
    assert resp.json()["error_code"] == "ai_scenarios_disabled"

    resp_create = await client.post(
        "/scenarios/ai-scenarios",
        json={"scenario_id": uploaded_scenario["id"], "persona_id": "persona_missing"},
        headers=user_auth_headers,
    )
    assert resp_create.status_code == 503


async def test_ai_scenario_crud_and_record_crud(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Alpha"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_delay_ryanair",
            namespace="support/flights",
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201
    created = create_ai.json()
    assert created["ai_scenario_id"] == "ai_delay_ryanair"
    assert created["persona_id"] == persona_id
    assert created["name"] == "Delayed Flight Support"
    assert created["namespace"] == "support/flights"
    assert created["scenario_brief"] == "Caller wants confirmation and support for a delayed flight."
    assert created["scenario_facts"]["booking_ref"] == "ABC123"
    assert created["evaluation_objective"] == "Confirm the delay and explain next steps clearly."
    assert created["opening_strategy"] == "wait_for_bot_greeting"
    assert created["is_active"] is True
    assert created["record_count"] == 0
    assert created["config"] == {
        "language": "en-GB",
        "stt_endpointing_ms": 600,
        "transcript_merge_window_s": 2.5,
        "turn_timeout_s": 30.0,
        "max_duration_s": 450.0,
        "max_total_turns": 9,
        "tts_voice": "openai:alloy",
        "stt_model": "nova-2-phonecall",
    }

    list_ai = await client.get("/scenarios/ai-scenarios", headers=user_auth_headers)
    assert list_ai.status_code == 200
    listed = list_ai.json()
    assert len(listed) == 1
    assert listed[0]["ai_scenario_id"] == "ai_delay_ryanair"
    assert listed[0]["namespace"] == "support/flights"
    assert listed[0]["scenario_brief"] == created["scenario_brief"]

    get_ai = await client.get(
        "/scenarios/ai-scenarios/ai_delay_ryanair",
        headers=user_auth_headers,
    )
    assert get_ai.status_code == 200
    assert get_ai.json()["persona_id"] == persona_id
    assert get_ai.json()["namespace"] == "support/flights"
    assert get_ai.json()["evaluation_objective"] == created["evaluation_objective"]

    update_ai = await client.put(
        "/scenarios/ai-scenarios/ai_delay_ryanair",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_delay_ryanair",
            name="Delayed Flight Support Updated",
            namespace="support/escalations",
            scenario_brief="Caller is stranded with children and needs certainty.",
            evaluation_objective="Confirm timing and provide child-friendly options.",
            scoring_profile="updated-profile",
            config={
                "language": "fr-FR",
                "turn_timeout_s": 45,
                "max_total_turns": 12,
                "stt_model": "nova-2-phonecall",
            },
        ),
        headers=user_auth_headers,
    )
    assert update_ai.status_code == 200
    assert update_ai.json()["scoring_profile"] == "updated-profile"
    assert update_ai.json()["name"] == "Delayed Flight Support Updated"
    assert update_ai.json()["namespace"] == "support/escalations"
    assert update_ai.json()["scenario_brief"] == "Caller is stranded with children and needs certainty."
    assert (
        update_ai.json()["evaluation_objective"]
        == "Confirm timing and provide child-friendly options."
    )
    assert update_ai.json()["config"] == {
        "language": "fr-FR",
        "stt_model": "nova-2-phonecall",
        "turn_timeout_s": 45.0,
        "max_total_turns": 12,
    }

    record_create_auto = await client.post(
        "/scenarios/ai-scenarios/ai_delay_ryanair/records",
        json=_record_payload(),
        headers=user_auth_headers,
    )
    assert record_create_auto.status_code == 201
    rec_1 = record_create_auto.json()
    assert rec_1["ai_scenario_id"] == "ai_delay_ryanair"
    assert rec_1["order_index"] == 1
    record_id_1 = rec_1["record_id"]

    record_create_explicit = await client.post(
        "/scenarios/ai-scenarios/ai_delay_ryanair/records",
        json=_record_payload(order_index=2, input_text="No booking please."),
        headers=user_auth_headers,
    )
    assert record_create_explicit.status_code == 201
    rec_2 = record_create_explicit.json()
    assert rec_2["ai_scenario_id"] == "ai_delay_ryanair"
    assert rec_2["order_index"] == 2
    record_id_2 = rec_2["record_id"]

    list_records = await client.get(
        "/scenarios/ai-scenarios/ai_delay_ryanair/records",
        headers=user_auth_headers,
    )
    assert list_records.status_code == 200
    records = list_records.json()
    assert [row["record_id"] for row in records] == [record_id_1, record_id_2]

    duplicate_order = await client.put(
        f"/scenarios/ai-scenarios/ai_delay_ryanair/records/{record_id_2}",
        json=_record_payload(order_index=1, input_text="Conflict order"),
        headers=user_auth_headers,
    )
    assert duplicate_order.status_code == 409

    update_record = await client.put(
        f"/scenarios/ai-scenarios/ai_delay_ryanair/records/{record_id_2}",
        json=_record_payload(order_index=3, input_text="Updated ask."),
        headers=user_auth_headers,
    )
    assert update_record.status_code == 200
    assert update_record.json()["order_index"] == 3

    delete_record = await client.delete(
        f"/scenarios/ai-scenarios/ai_delay_ryanair/records/{record_id_1}",
        headers=user_auth_headers,
    )
    assert delete_record.status_code == 204

    delete_ai = await client.delete(
        "/scenarios/ai-scenarios/ai_delay_ryanair",
        headers=user_auth_headers,
    )
    assert delete_ai.status_code == 204

    get_deleted = await client.get(
        "/scenarios/ai-scenarios/ai_delay_ryanair",
        headers=user_auth_headers,
    )
    assert get_deleted.status_code == 404
    assert get_deleted.json()["error_code"] == "ai_scenario_not_found"


async def test_ai_scenario_namespace_blank_normalizes_to_null(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Namespace"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_blank_namespace",
            namespace="  /  ",
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201
    assert create_ai.json()["namespace"] is None


async def test_ai_scenario_config_drops_malformed_tts_voice(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Beta"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_invalid_tts_voice",
            config={
                "tts_voice": "openai:",
                "language": "en-GB",
            },
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201
    assert create_ai.json()["config"] == {"language": "en-GB"}


async def test_create_ai_scenario_rejects_disabled_tts_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Gamma"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_disabled_elevenlabs",
            config={"tts_voice": "elevenlabs:voice-123"},
        ),
        headers=user_auth_headers,
    )

    assert create_ai.status_code == 422
    assert create_ai.json()["error_code"] == "tts_provider_disabled"


async def test_preferred_ai_scenario_record_for_dispatch_prefers_active_record(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Dispatch Active"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_dispatch_active",
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201

    inactive_resp = await client.post(
        "/scenarios/ai-scenarios/ai_dispatch_active/records",
        json=_record_payload(order_index=1, input_text="inactive", is_active=False),
        headers=user_auth_headers,
    )
    assert inactive_resp.status_code == 201

    active_resp = await client.post(
        "/scenarios/ai-scenarios/ai_dispatch_active/records",
        json=_record_payload(order_index=2, input_text="active winner", is_active=True),
        headers=user_auth_headers,
    )
    assert active_resp.status_code == 201

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        selected = await scenarios_store_service.get_preferred_ai_scenario_record_for_dispatch(
            session,
            scenario_id=uploaded_scenario["id"],
            tenant_id=settings.tenant_id,
        )

    assert selected is not None
    assert selected.record_id == active_resp.json()["record_id"]
    assert selected.input_text == "active winner"


async def test_preferred_ai_scenario_record_for_dispatch_falls_back_to_lowest_order(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Dispatch Fallback"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_dispatch_fallback",
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201

    later_resp = await client.post(
        "/scenarios/ai-scenarios/ai_dispatch_fallback/records",
        json=_record_payload(order_index=2, input_text="later inactive", is_active=False),
        headers=user_auth_headers,
    )
    assert later_resp.status_code == 201

    first_resp = await client.post(
        "/scenarios/ai-scenarios/ai_dispatch_fallback/records",
        json=_record_payload(order_index=1, input_text="first inactive", is_active=False),
        headers=user_auth_headers,
    )
    assert first_resp.status_code == 201

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        selected = await scenarios_store_service.get_preferred_ai_scenario_record_for_dispatch(
            session,
            scenario_id=uploaded_scenario["id"],
            tenant_id=settings.tenant_id,
        )

    assert selected is not None
    assert selected.record_id == first_resp.json()["record_id"]
    assert selected.input_text == "first inactive"


async def test_create_ai_scenario_rejects_tenant_disabled_tts_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    await _set_provider_assignment_enabled(
        tenant_id=settings.tenant_id,
        provider_id="openai:gpt-4o-mini-tts",
        enabled=False,
    )

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Tenant Disabled"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_tenant_disabled_openai",
            config={"tts_voice": "openai:alloy"},
        ),
        headers=user_auth_headers,
    )

    assert create_ai.status_code == 422
    assert create_ai.json()["error_code"] == "tts_provider_disabled"


async def test_create_ai_scenario_rejects_unsupported_tts_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Epsilon"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_unsupported_tts_provider",
            config={"tts_voice": "deepgram:aura-asteria-en"},
        ),
        headers=user_auth_headers,
    )

    assert create_ai.status_code == 422
    assert create_ai.json()["error_code"] == "tts_provider_unsupported"


async def test_create_ai_scenario_rejects_disabled_stt_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Eta"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_disabled_deepgram",
            config={"stt_provider": "deepgram", "stt_model": "nova-2-phonecall"},
        ),
        headers=user_auth_headers,
    )

    assert create_ai.status_code == 422
    assert create_ai.json()["error_code"] == "stt_provider_disabled"


async def test_create_ai_scenario_rejects_unsupported_stt_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Theta"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_unsupported_stt_provider",
            config={"stt_provider": "whisper", "stt_model": "whisper-1"},
        ),
        headers=user_auth_headers,
    )

    assert create_ai.status_code == 422
    assert create_ai.json()["error_code"] == "stt_provider_unsupported"


async def test_update_ai_scenario_rejects_unconfigured_tts_provider(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")

    create_persona = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Persona Delta"),
        headers=user_auth_headers,
    )
    assert create_persona.status_code == 201
    persona_id = create_persona.json()["persona_id"]

    create_ai = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_update_unconfigured_elevenlabs",
        ),
        headers=user_auth_headers,
    )
    assert create_ai.status_code == 201

    update_ai = await client.put(
        "/scenarios/ai-scenarios/ai_update_unconfigured_elevenlabs",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id=persona_id,
            ai_scenario_id="ai_update_unconfigured_elevenlabs",
            config={"tts_voice": "elevenlabs:voice-123"},
        ),
        headers=user_auth_headers,
    )

    assert update_ai.status_code == 422
    assert update_ai.json()["error_code"] == "tts_provider_unconfigured"


async def test_create_ai_scenario_rejects_missing_persona(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    resp = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=uploaded_scenario["id"],
            persona_id="persona_missing",
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 404
    assert "AI persona not found" in resp.json()["detail"]
    assert resp.json()["error_code"] == "ai_persona_not_found"
