from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import ScenarioPackRow

from _packs_test_helpers import _upload_scenario
from factories import make_pack_upsert_payload


def _persona_payload(name: str = "Pack Persona") -> dict:
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
    ai_scenario_id: str,
) -> dict:
    return {
        "ai_scenario_id": ai_scenario_id,
        "scenario_id": scenario_id,
        "persona_id": persona_id,
        "name": "Delayed Flight Support",
        "scenario_brief": "Caller wants confirmation and support for a delayed flight.",
        "scenario_facts": {"booking_ref": "ABC123", "airline": "Ryanair"},
        "evaluation_objective": "Confirm the delay and explain next steps clearly.",
        "opening_strategy": "wait_for_bot_greeting",
        "is_active": True,
        "scoring_profile": "call-success",
        "dataset_source": "manual",
        "config": {"sample_count": 3},
    }


async def test_packs_routes_return_503_when_feature_disabled(client, user_auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "feature_packs_enabled", False)

    list_resp = await client.get("/packs/", headers=user_auth_headers)
    assert list_resp.status_code == 503
    assert "disabled" in list_resp.json()["detail"].lower()
    assert list_resp.json()["error_code"] == "scenario_packs_disabled"

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(name="Disabled Pack"),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 503
    assert create_resp.json()["error_code"] == "scenario_packs_disabled"

    runs_resp = await client.get("/pack-runs/", headers=user_auth_headers)
    assert runs_resp.status_code == 503
    assert runs_resp.json()["error_code"] == "scenario_packs_disabled"

async def test_pack_crud_lifecycle(client, user_auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    scenario_a = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-scenario-a",
        name="Pack Scenario A",
    )
    scenario_b = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-scenario-b",
        name="Pack Scenario B",
    )

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Regression Pack",
            tags=["smoke", "nightly"],
            scenario_ids=[scenario_a, scenario_b],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Regression Pack"
    assert created["execution_mode"] == "parallel"
    assert created["scenario_count"] == 2
    assert [item["scenario_id"] for item in created["items"]] == [scenario_a, scenario_b]
    assert [item["order_index"] for item in created["items"]] == [0, 1]

    pack_id = created["pack_id"]

    list_resp = await client.get("/packs/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["pack_id"] == pack_id
    assert listed[0]["scenario_count"] == 2

    detail_resp = await client.get(f"/packs/{pack_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["pack_id"] == pack_id
    assert detail["tags"] == ["smoke", "nightly"]

    update_resp = await client.put(
        f"/packs/{pack_id}",
        json=make_pack_upsert_payload(
            name="Updated Pack",
            description=None,
            tags=["nightly"],
            scenario_ids=[scenario_b],
        ),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Updated Pack"
    assert updated["description"] is None
    assert updated["scenario_count"] == 1
    assert [item["scenario_id"] for item in updated["items"]] == [scenario_b]

    delete_resp = await client.delete(f"/packs/{pack_id}", headers=user_auth_headers)
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/packs/{pack_id}", headers=user_auth_headers)
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error_code"] == "pack_not_found"


async def test_create_pack_accepts_public_ai_scenario_items(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    graph_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-graph-public-id",
        name="Graph Public ID",
    )
    ai_backing_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-ai-backing",
        name="AI Backing",
    )

    persona_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(),
        headers=user_auth_headers,
    )
    assert persona_resp.status_code == 201
    persona_id = persona_resp.json()["persona_id"]

    ai_resp = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=ai_backing_scenario_id,
            persona_id=persona_id,
            ai_scenario_id="ai_pack_public",
        ),
        headers=user_auth_headers,
    )
    assert ai_resp.status_code == 201

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Mixed Public Pack",
            scenario_ids=[],
            items=[
                {"scenario_id": graph_scenario_id},
                {"ai_scenario_id": "ai_pack_public"},
            ],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert [item["scenario_id"] for item in created["items"]] == [
        graph_scenario_id,
        ai_backing_scenario_id,
    ]
    assert created["items"][0]["ai_scenario_id"] is None
    assert created["items"][1]["ai_scenario_id"] == "ai_pack_public"

async def test_delete_pack_rejected_when_active_pack_run_exists(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-delete-active-guard",
        name="Pack Delete Active Guard",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Delete Guard Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202

    delete_resp = await client.delete(f"/packs/{pack_id}", headers=user_auth_headers)
    assert delete_resp.status_code == 409
    assert "active pack runs" in delete_resp.json()["detail"].lower()

async def test_create_pack_rejects_duplicate_scenarios(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-duplicate-scenario",
        name="Duplicate Scenario",
    )

    resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Bad Pack",
            scenario_ids=[scenario_id, scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    assert "duplicate" in resp.json()["detail"].lower()

async def test_create_pack_requires_existing_scenarios(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Missing Scenario Pack",
            scenario_ids=["does-not-exist"],
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 404

async def test_update_pack_non_existent_returns_404(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    resp = await client.put(
        "/packs/pack_missing",
        json=make_pack_upsert_payload(
            name="Missing Pack",
            scenario_ids=[],
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
    assert resp.json()["error_code"] == "pack_not_found"

async def test_get_pack_other_tenant_returns_404(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        session.add(
            ScenarioPackRow(
                pack_id="pack_other_tenant",
                tenant_id="other-tenant",
                name="Other Tenant Pack",
                tags=[],
                execution_mode="parallel",
            )
        )
        await session.commit()

    resp = await client.get("/packs/pack_other_tenant", headers=user_auth_headers)
    assert resp.status_code == 404
