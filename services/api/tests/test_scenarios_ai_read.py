from __future__ import annotations

from botcheck_api import database, store_repo
from botcheck_api.config import settings
from botcheck_api.models import (
    AIPersonaRow,
    AIScenarioRecordRow,
    AIScenarioRow,
    ScenarioKind,
)


async def test_list_ai_personas_disabled_returns_503(client, user_auth_headers):
    resp = await client.get("/scenarios/personas", headers=user_auth_headers)
    assert resp.status_code == 503
    assert "AI scenarios are disabled" in resp.json()["detail"]


async def test_list_ai_scenarios_disabled_returns_503(client, user_auth_headers):
    resp = await client.get("/scenarios/ai-scenarios", headers=user_auth_headers)
    assert resp.status_code == 503
    assert "AI scenarios are disabled" in resp.json()["detail"]


async def test_list_ai_read_models_when_enabled(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        scenario_row = await store_repo.get_scenario_row_for_tenant(
            session,
            uploaded_scenario["id"],
            settings.tenant_id,
        )
        assert scenario_row is not None
        scenario_row.scenario_kind = ScenarioKind.AI.value

        persona = AIPersonaRow(
            persona_id="persona_customer",
            tenant_id=settings.tenant_id,
            name="Customer Persona",
            display_name="Liam White",
            avatar_url="/personas/avatars/male_avatar_2.png",
            backstory_summary="Young buyer calling about townhouse options.",
            system_prompt="You are a realistic customer.",
            style="neutral",
            voice="alloy",
            is_active=True,
        )
        ai_scenario = AIScenarioRow(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_customer_scenarios",
            tenant_id=settings.tenant_id,
            name="AI Scenario Read Model",
            namespace="support/housing",
            persona_id="persona_customer",
            scenario_brief="Caller wants help finding a townhouse with a backyard.",
            scenario_facts={"segment": "buyer"},
            evaluation_objective="Recommend properties and avoid booking unless asked.",
            opening_strategy="wait_for_bot_greeting",
            is_active=True,
            scoring_profile="call-success",
            dataset_source="manual",
            config={
                "language": "en-GB",
                "stt_endpointing_ms": 900,
                "transcript_merge_window_s": 2.0,
                "turn_timeout_s": 25,
                "max_duration_s": 360,
                "max_total_turns": 12,
                "tts_voice": "elevenlabs:voice-123",
                "sample_count": 5,
            },
        )
        record_1 = AIScenarioRecordRow(
            record_id="record_customer_1",
            scenario_id=uploaded_scenario["id"],
            tenant_id=settings.tenant_id,
            order_index=1,
            input_text="Need a townhouse with backyard.",
            expected_output="Recommend properties and ask follow-up.",
            metadata_json={"segment": "buyer"},
            is_active=True,
        )
        record_2 = AIScenarioRecordRow(
            record_id="record_customer_2",
            scenario_id=uploaded_scenario["id"],
            tenant_id=settings.tenant_id,
            order_index=2,
            input_text="Do not book an appointment.",
            expected_output="No booking should be made.",
            metadata_json={"segment": "buyer"},
            is_active=True,
        )
        await store_repo.add_ai_persona_row(session, persona)
        await store_repo.add_ai_scenario_row(session, ai_scenario)
        await store_repo.add_ai_scenario_record_row(session, record_1)
        await store_repo.add_ai_scenario_record_row(session, record_2)
        await session.commit()

    personas_resp = await client.get("/scenarios/personas", headers=user_auth_headers)
    assert personas_resp.status_code == 200
    personas_payload = personas_resp.json()
    assert len(personas_payload) == 1
    assert personas_payload[0]["persona_id"] == "persona_customer"
    assert personas_payload[0]["name"] == "Customer Persona"
    assert personas_payload[0]["display_name"] == "Liam White"
    assert personas_payload[0]["avatar_url"] == "/personas/avatars/male_avatar_2.png"
    assert personas_payload[0]["backstory_summary"] == "Young buyer calling about townhouse options."
    assert personas_payload[0]["is_active"] is True

    scenarios_resp = await client.get("/scenarios/ai-scenarios", headers=user_auth_headers)
    assert scenarios_resp.status_code == 200
    scenarios_payload = scenarios_resp.json()
    assert len(scenarios_payload) == 1
    assert scenarios_payload[0]["ai_scenario_id"] == "ai_customer_scenarios"
    assert scenarios_payload[0]["name"] == "AI Scenario Read Model"
    assert scenarios_payload[0]["namespace"] == "support/housing"
    assert scenarios_payload[0]["persona_id"] == "persona_customer"
    assert scenarios_payload[0]["scenario_brief"] == (
        "Caller wants help finding a townhouse with a backyard."
    )
    assert scenarios_payload[0]["scenario_facts"] == {"segment": "buyer"}
    assert scenarios_payload[0]["evaluation_objective"] == (
        "Recommend properties and avoid booking unless asked."
    )
    assert scenarios_payload[0]["opening_strategy"] == "wait_for_bot_greeting"
    assert scenarios_payload[0]["is_active"] is True
    assert scenarios_payload[0]["record_count"] == 2

    detail_resp = await client.get(
        "/scenarios/ai-scenarios/ai_customer_scenarios",
        headers=user_auth_headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["ai_scenario_id"] == "ai_customer_scenarios"
    assert detail_resp.json()["name"] == "AI Scenario Read Model"
    assert detail_resp.json()["namespace"] == "support/housing"
    assert detail_resp.json()["config"] == {
        "language": "en-GB",
        "stt_endpointing_ms": 900,
        "transcript_merge_window_s": 2.0,
        "turn_timeout_s": 25.0,
        "max_duration_s": 360.0,
        "max_total_turns": 12,
        "tts_voice": "elevenlabs:voice-123",
    }
