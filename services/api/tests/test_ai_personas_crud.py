from __future__ import annotations

from botcheck_api import database, store_repo
from botcheck_api.config import settings
from botcheck_api.models import AIScenarioRow, ScenarioKind


def _persona_payload(
    *,
    name: str = "Customer Persona",
    display_name: str | None = None,
    avatar_url: str | None = None,
    backstory_summary: str | None = None,
    system_prompt: str = "Act as a realistic customer caller.",
    style: str | None = "neutral",
    voice: str | None = "alloy",
    is_active: bool = True,
) -> dict:
    return {
        "name": name,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "backstory_summary": backstory_summary,
        "system_prompt": system_prompt,
        "style": style,
        "voice": voice,
        "is_active": is_active,
    }


async def test_ai_persona_crud_requires_feature_flag(client, user_auth_headers):
    create_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 503
    assert "AI scenarios are disabled" in create_resp.json()["detail"]
    assert create_resp.json()["error_code"] == "ai_scenarios_disabled"


async def test_create_list_get_update_delete_ai_persona(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(
            name="persona_internal_one",
            display_name="Persona One",
            avatar_url="/personas/avatars/female_avatar_1.png",
            backstory_summary="Polite parent calling about a disrupted booking.",
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    persona_id = created["persona_id"]
    assert created["name"] == "persona_internal_one"
    assert created["display_name"] == "Persona One"
    assert created["avatar_url"] == "/personas/avatars/female_avatar_1.png"
    assert created["backstory_summary"] == "Polite parent calling about a disrupted booking."
    assert created["system_prompt"] == "Act as a realistic customer caller."

    list_resp = await client.get("/scenarios/personas", headers=user_auth_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["persona_id"] == persona_id
    assert listed[0]["name"] == "persona_internal_one"
    assert listed[0]["display_name"] == "Persona One"

    get_resp = await client.get(f"/scenarios/personas/{persona_id}", headers=user_auth_headers)
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["persona_id"] == persona_id
    assert fetched["name"] == "persona_internal_one"
    assert fetched["display_name"] == "Persona One"

    update_resp = await client.put(
        f"/scenarios/personas/{persona_id}",
        json=_persona_payload(
            name="persona_internal_one",
            display_name="Persona One Updated",
            avatar_url="/personas/avatars/male_avatar_1.png",
            backstory_summary="Frequent flyer trying to recover a delayed itinerary.",
            style="assertive",
        ),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "persona_internal_one"
    assert updated["display_name"] == "Persona One Updated"
    assert updated["avatar_url"] == "/personas/avatars/male_avatar_1.png"
    assert updated["backstory_summary"] == "Frequent flyer trying to recover a delayed itinerary."
    assert updated["style"] == "assertive"

    fallback_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="persona_fallback_only"),
        headers=user_auth_headers,
    )
    assert fallback_resp.status_code == 201
    assert fallback_resp.json()["display_name"] == "persona_fallback_only"

    delete_resp = await client.delete(
        f"/scenarios/personas/{persona_id}",
        headers=user_auth_headers,
    )
    assert delete_resp.status_code == 204

    get_deleted = await client.get(f"/scenarios/personas/{persona_id}", headers=user_auth_headers)
    assert get_deleted.status_code == 404
    assert get_deleted.json()["error_code"] == "ai_persona_not_found"


async def test_create_ai_persona_rejects_duplicate_name(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    first = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Duplicate Persona"),
        headers=user_auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="Duplicate Persona"),
        headers=user_auth_headers,
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


async def test_delete_ai_persona_rejects_when_in_use(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    create_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(name="In Use Persona"),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    persona_id = create_resp.json()["persona_id"]

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
        ai_scenario = AIScenarioRow(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_persona_in_use",
            tenant_id=settings.tenant_id,
            name="Persona In Use Scenario",
            persona_id=persona_id,
            scenario_brief="Caller needs support from an airline.",
            scenario_facts={"booking_ref": "ABC123"},
            evaluation_objective="Confirm support journey works end to end.",
            opening_strategy="wait_for_bot_greeting",
            is_active=True,
            scoring_profile="default",
            dataset_source="manual",
            config={},
        )
        await store_repo.add_ai_scenario_row(session, ai_scenario)
        await session.commit()

    delete_resp = await client.delete(
        f"/scenarios/personas/{persona_id}",
        headers=user_auth_headers,
    )
    assert delete_resp.status_code == 409
    assert "in use" in delete_resp.json()["detail"]
