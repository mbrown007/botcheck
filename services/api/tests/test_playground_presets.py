from __future__ import annotations

from datetime import UTC, datetime

from jose import jwt

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import (
    AIPersonaRow,
    AIScenarioRow,
    BotDestinationRow,
    DestinationProtocol,
    RunRow,
    RunState,
    TenantRow,
)


def _role_auth_headers(role: str, *, tenant_id: str | None = None) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": f"{role}-playground-presets-user",
            "tenant_id": tenant_id or settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "amr": ["pwd", "dev_token"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_http_destination(
    *,
    destination_id: str = "dest_http_preset",
    tenant_id: str | None = None,
    is_active: bool = True,
) -> str:
    async with database.AsyncSessionLocal() as session:
        session.add(
            BotDestinationRow(
                destination_id=destination_id,
                tenant_id=tenant_id or settings.tenant_id,
                name="Preset HTTP Destination",
                protocol=DestinationProtocol.HTTP.value,
                endpoint="https://bot.example.test/respond",
                headers={"Authorization": "Bearer test"},
                direct_http_config={
                    "message_field": "message",
                    "response_field": "response",
                    "timeout_s": 15,
                },
                is_active=is_active,
            )
        )
        await session.commit()
    return destination_id


async def _seed_non_http_destination(
    *,
    destination_id: str = "dest_mock_preset",
    protocol: DestinationProtocol = DestinationProtocol.MOCK,
) -> str:
    async with database.AsyncSessionLocal() as session:
        session.add(
            BotDestinationRow(
                destination_id=destination_id,
                tenant_id=settings.tenant_id,
                name="Preset Non-HTTP Destination",
                protocol=protocol.value,
                endpoint="mock://bot",
                headers={},
                is_active=True,
            )
        )
        await session.commit()
    return destination_id


async def _seed_tenant(tenant_id: str) -> None:
    async with database.AsyncSessionLocal() as session:
        session.add(
            TenantRow(
                tenant_id=tenant_id,
                slug=tenant_id,
                display_name=tenant_id,
                feature_overrides={},
                quota_config={},
            )
        )
        await session.commit()


async def _seed_ai_scenario(
    *,
    backing_scenario_id: str,
    ai_scenario_id: str,
    is_active: bool = True,
) -> None:
    async with database.AsyncSessionLocal() as session:
        session.add(
            AIPersonaRow(
                persona_id="persona_playground_preset",
                tenant_id=settings.tenant_id,
                name="Preset Persona",
                system_prompt="Act as a customer.",
                is_active=True,
            )
        )
        session.add(
            AIScenarioRow(
                scenario_id=backing_scenario_id,
                ai_scenario_id=ai_scenario_id,
                tenant_id=settings.tenant_id,
                name="Preset AI Scenario",
                persona_id="persona_playground_preset",
                scenario_brief="Test AI preset target.",
                scenario_facts={},
                evaluation_objective="Stay on task.",
                opening_strategy="wait_for_bot_greeting",
                is_active=is_active,
                config={},
            )
        )
        await session.commit()


async def _store_run_row_direct(*, scenario_id: str) -> str:
    """Insert a RunRow directly. Always uses settings.tenant_id (default tenant)."""
    run_id = f"run_preset_{int(datetime.now(UTC).timestamp() * 1000000)}"
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as session:
        session.add(
            RunRow(
                run_id=run_id,
                scenario_id=scenario_id,
                tenant_id=settings.tenant_id,
                state=RunState.PENDING.value,
                run_type="playground",
                playground_mode="mock",
                transport="mock",
                livekit_room=f"lk_{run_id}",
                trigger_source="manual",
            )
        )
        await session.commit()
    return run_id


async def test_create_list_get_update_delete_playground_preset(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Support smoke preset",
            "description": "Tenant-shared support smoke setup",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a calm support chatbot.",
            "tool_stubs": {"lookup_account": {"status": "active"}},
        },
        headers=_role_auth_headers("operator"),
    )

    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Support smoke preset"
    assert created["scenario_id"] == uploaded_scenario["id"]
    assert created["playground_mode"] == "mock"
    assert created["system_prompt"] == "You are a calm support chatbot."
    assert created["tool_stubs"] == {"lookup_account": {"status": "active"}}
    preset_id = created["preset_id"]

    list_resp = await client.get(
        "/runs/playground/presets",
        headers=_role_auth_headers("viewer"),
    )
    assert list_resp.status_code == 200
    assert list_resp.json() == [
        {
            "preset_id": preset_id,
            "name": "Support smoke preset",
            "description": "Tenant-shared support smoke setup",
            "scenario_id": uploaded_scenario["id"],
            "ai_scenario_id": None,
            "playground_mode": "mock",
            "transport_profile_id": None,
            "has_tool_stubs": True,
            "created_by": "operator-playground-presets-user",
            "updated_by": "operator-playground-presets-user",
            "created_at": created["created_at"],
            "updated_at": created["updated_at"],
        }
    ]

    detail_resp = await client.get(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("viewer"),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["tool_stubs"] == {"lookup_account": {"status": "active"}}

    update_resp = await client.patch(
        f"/runs/playground/presets/{preset_id}",
        json={
            "name": "Support regression preset",
            "description": "Updated description",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a precise support chatbot.",
            "tool_stubs": {"lookup_account": {"status": "delinquent"}},
        },
        headers=_role_auth_headers("operator"),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Support regression preset"
    assert update_resp.json()["updated_by"] == "operator-playground-presets-user"

    delete_resp = await client.delete(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("operator"),
    )
    assert delete_resp.status_code == 204

    missing_resp = await client.get(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("viewer"),
    )
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error_code"] == "preset_not_found"


async def test_create_direct_http_playground_preset(client, uploaded_scenario):
    destination_id = await _seed_http_destination()

    resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "HTTP smoke preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "direct_http",
            "transport_profile_id": destination_id,
        },
        headers=_role_auth_headers("operator"),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["playground_mode"] == "direct_http"
    assert body["transport_profile_id"] == destination_id
    assert body["system_prompt"] is None
    assert body["tool_stubs"] is None


async def test_duplicate_playground_preset_name_rejected(client, uploaded_scenario):
    payload = {
        "name": "Duplicate preset",
        "scenario_id": uploaded_scenario["id"],
        "playground_mode": "mock",
        "system_prompt": "You are a support bot.",
    }

    first = await client.post(
        "/runs/playground/presets",
        json=payload,
        headers=_role_auth_headers("operator"),
    )
    assert first.status_code == 201

    second = await client.post(
        "/runs/playground/presets",
        json=payload,
        headers=_role_auth_headers("operator"),
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "preset_name_conflict"


async def test_create_ai_scenario_preset_uses_public_ai_scenario_id(client, uploaded_scenario):
    await _seed_ai_scenario(
        backing_scenario_id=uploaded_scenario["id"],
        ai_scenario_id="ai_public_preset_target",
    )

    resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "AI preset",
            "ai_scenario_id": "ai_public_preset_target",
            "playground_mode": "mock",
            "system_prompt": "You are a calm support bot.",
        },
        headers=_role_auth_headers("operator"),
    )

    assert resp.status_code == 201
    assert resp.json()["ai_scenario_id"] == "ai_public_preset_target"


async def test_create_preset_rejects_inactive_ai_scenario(client, uploaded_scenario):
    await _seed_ai_scenario(
        backing_scenario_id=uploaded_scenario["id"],
        ai_scenario_id="ai_inactive_preset_target",
        is_active=False,
    )

    resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Inactive AI preset",
            "ai_scenario_id": "ai_inactive_preset_target",
            "playground_mode": "mock",
            "system_prompt": "You are a calm support bot.",
        },
        headers=_role_auth_headers("operator"),
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "ai_scenario_inactive"


async def test_create_direct_http_preset_rejects_non_http_transport_profile(client, uploaded_scenario):
    destination_id = await _seed_non_http_destination()

    resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Wrong transport preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "direct_http",
            "transport_profile_id": destination_id,
        },
        headers=_role_auth_headers("operator"),
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "preset_invalid_transport_profile"


async def test_playground_presets_are_tenant_scoped(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Tenant A preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are tenant A support.",
        },
        headers=_role_auth_headers("operator"),
    )
    assert create_resp.status_code == 201
    preset_id = create_resp.json()["preset_id"]

    other_tenant = "other-tenant"
    await _seed_tenant(other_tenant)

    # enforce_instance_tenant blocks cross-tenant JWTs at the auth layer (403).
    list_resp = await client.get(
        "/runs/playground/presets",
        headers=_role_auth_headers("viewer", tenant_id=other_tenant),
    )
    assert list_resp.status_code == 403

    get_resp = await client.get(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("viewer", tenant_id=other_tenant),
    )
    assert get_resp.status_code == 403


async def test_patch_playground_preset_merges_partial_fields(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Patchable preset",
            "description": "Original description",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a calm support chatbot.",
            "tool_stubs": {"lookup_account": {"status": "active"}},
        },
        headers=_role_auth_headers("operator"),
    )
    preset_id = create_resp.json()["preset_id"]

    patch_resp = await client.patch(
        f"/runs/playground/presets/{preset_id}",
        json={"name": "Patched preset"},
        headers=_role_auth_headers("operator"),
    )

    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["name"] == "Patched preset"
    assert body["description"] == "Original description"
    assert body["system_prompt"] == "You are a calm support chatbot."
    assert body["tool_stubs"] == {"lookup_account": {"status": "active"}}


async def test_patch_playground_preset_rejects_mode_contract_violation(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Mode patch preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a calm support chatbot.",
        },
        headers=_role_auth_headers("operator"),
    )
    preset_id = create_resp.json()["preset_id"]

    patch_resp = await client.patch(
        f"/runs/playground/presets/{preset_id}",
        json={"playground_mode": "direct_http"},
        headers=_role_auth_headers("operator"),
    )

    assert patch_resp.status_code == 422
    assert "transport_profile_id is required for direct_http playground runs" in patch_resp.text


async def test_patch_and_delete_hide_cross_tenant_preset(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Tenant A preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are tenant A support.",
        },
        headers=_role_auth_headers("operator"),
    )
    preset_id = create_resp.json()["preset_id"]

    other_tenant = "other-tenant-patch-delete"
    await _seed_tenant(other_tenant)

    # enforce_instance_tenant blocks cross-tenant JWTs at the auth layer (403).
    patch_resp = await client.patch(
        f"/runs/playground/presets/{preset_id}",
        json={"name": "Tenant B rename"},
        headers=_role_auth_headers("operator", tenant_id=other_tenant),
    )
    assert patch_resp.status_code == 403

    delete_resp = await client.delete(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("operator", tenant_id=other_tenant),
    )
    assert delete_resp.status_code == 403


async def test_delete_playground_preset_does_not_delete_existing_runs(client, uploaded_scenario):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "Reusable preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a calm support bot.",
        },
        headers=_role_auth_headers("operator"),
    )
    assert create_resp.status_code == 201
    preset_id = create_resp.json()["preset_id"]

    run_id = await _store_run_row_direct(scenario_id=uploaded_scenario["id"])

    delete_resp = await client.delete(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers("operator"),
    )
    assert delete_resp.status_code == 204

    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as session:
        run = await session.get(RunRow, run_id)
        assert run is not None
