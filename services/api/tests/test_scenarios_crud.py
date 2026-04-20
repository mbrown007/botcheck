"""Tests for /scenarios/ CRUD routes."""

import yaml
from unittest.mock import patch

from botcheck_api import database, store_repo
from botcheck_api.admin.service_providers import (
    delete_platform_provider_credential,
    upsert_platform_provider_credential,
    validate_platform_provider_credential_background,
)
from botcheck_api.config import settings
from botcheck_api.main import app
from botcheck_api.models import ProviderCredentialRow, TenantProviderAssignmentRow
from botcheck_api.providers.service import ensure_provider_registry_seeded
from sqlalchemy import select

from factories import (
    make_scenario_dict,
    make_scenario_upload_payload,
    make_scenario_yaml,
    make_schedule_create_payload,
)


def _time_route_scenario_yaml(*, scenario_id: str = "time-route-crud") -> str:
    return yaml.safe_dump(
        {
            "version": "1.0",
            "id": scenario_id,
            "name": "Time Route CRUD",
            "type": "reliability",
            "bot": {
                "endpoint": "sip:bot@test.example.com",
                "protocol": "sip",
            },
            "turns": [
                {
                    "id": "t0_pickup",
                    "kind": "bot_listen",
                    "next": "t_route",
                },
                {
                    "id": "t_route",
                    "kind": "time_route",
                    "timezone": "UTC",
                    "windows": [
                        {
                            "label": "business_hours",
                            "start": "09:00",
                            "end": "17:00",
                            "next": "t_hours",
                        },
                        {
                            "label": "after_hours",
                            "start": "17:00",
                            "end": "09:00",
                            "next": "t_after",
                        },
                    ],
                    "default": "t_default",
                },
                {
                    "id": "t_hours",
                    "kind": "harness_prompt",
                    "content": {"text": "Business hours greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {
                    "id": "t_after",
                    "kind": "harness_prompt",
                    "content": {"text": "After hours greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {
                    "id": "t_default",
                    "kind": "harness_prompt",
                    "content": {"text": "Default greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {"id": "t_end", "kind": "hangup"},
            ],
        },
        sort_keys=False,
    )


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


async def _delete_platform_provider_credential(*, provider_id: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        existing = (
            await session.execute(
                select(ProviderCredentialRow).where(
                    ProviderCredentialRow.provider_id == provider_id,
                    ProviderCredentialRow.owner_scope == "platform",
                    ProviderCredentialRow.tenant_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await delete_platform_provider_credential(
                session,
                provider_id=provider_id,
                actor_id="test-fixture",
                actor_tenant_id=settings.tenant_id,
            )
            await session.commit()


async def _store_platform_provider_credential(
    *,
    provider_id: str,
    secret_fields: dict[str, str],
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await upsert_platform_provider_credential(
            session,
            provider_id=provider_id,
            secret_fields=secret_fields,
            actor_id="test-fixture",
            actor_tenant_id=settings.tenant_id,
        )
        await session.commit()
        await validate_platform_provider_credential_background(credential_id=row.credential_id)


class TestCreateScenario:
    async def test_valid_scenario_returns_201(self, client, scenario_yaml, user_auth_headers):
        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "test-jailbreak"
        assert data["name"] == "Jailbreak Test"
        assert data["type"] == "adversarial"
        assert data["scenario_kind"] == "graph"
        assert data["namespace"] is None
        assert "version_hash" in data
        assert data["cache_status"] == "warming"
        assert data["cache_updated_at"] is not None

    async def test_valid_scenario_with_namespace_returns_201(
        self, client, user_auth_headers
    ):
        scenario_yaml = make_scenario_yaml(
            scenario_id="namespaced-scenario",
            name="Namespaced Scenario",
            overrides={"namespace": "support/refunds"},
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 201
        assert resp.json()["namespace"] == "support/refunds"

    async def test_invalid_yaml_returns_422(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload("not: valid: scenario: yaml: content"),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_missing_required_field_returns_422(self, client, user_auth_headers):
        incomplete = make_scenario_dict(scenario_id="broken", name="Broken")
        incomplete.pop("bot")
        incomplete_yaml = yaml.safe_dump(incomplete, sort_keys=False)
        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(incomplete_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_duplicate_upload_overwrites(self, client, scenario_yaml, user_auth_headers):
        """Uploading the same scenario ID twice is idempotent."""
        resp1 = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        resp2 = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] == resp2.json()["id"]

    async def test_create_requires_auth(self, client, scenario_yaml):
        resp = await client.post(
            "/scenarios/", json=make_scenario_upload_payload(scenario_yaml)
        )
        assert resp.status_code == 401

    async def test_create_enqueues_warm_cache_job(
        self, client, scenario_yaml, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "warm_tts_cache"
        assert kwargs["_queue_name"] == "arq:cache"
        payload = kwargs["payload"]
        assert payload["scenario_id"] == "test-jailbreak"
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["scenario_payload"]["id"] == "test-jailbreak"

    async def test_create_accepts_time_route_scenario_and_enqueues_cache_warm(
        self, client, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(_time_route_scenario_yaml()),
            headers=user_auth_headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "time-route-crud"
        assert data["cache_status"] == "warming"

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "warm_tts_cache"
        payload = kwargs["payload"]
        assert payload["scenario_id"] == "time-route-crud"
        assert payload["scenario_payload"]["turns"][1]["kind"] == "time_route"
        assert payload["scenario_payload"]["turns"][1]["default"] == "t_default"
        assert payload["scenario_payload"]["turns"][1]["windows"] == [
            {
                "label": "business_hours",
                "start": "09:00",
                "end": "17:00",
                "next": "t_hours",
            },
            {
                "label": "after_hours",
                "start": "17:00",
                "end": "09:00",
                "next": "t_after",
            },
        ]

    async def test_create_skips_cache_enqueue_when_feature_disabled(
        self, client, scenario_yaml, user_auth_headers, monkeypatch
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()
        monkeypatch.setattr(settings, "tts_cache_enabled", False)

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["cache_status"] == "cold"
        assert data["cache_updated_at"] is None
        enqueue_mock.assert_not_awaited()

    async def test_create_ignores_legacy_destination_field_in_yaml(
        self, client, user_auth_headers, monkeypatch
    ):
        # Scenario-level destination binding is deprecated. Legacy YAML payloads
        # that still include destination_id remain accepted but the field is ignored.
        monkeypatch.setattr(settings, "feature_destinations_enabled", False)
        scenario_yaml = make_scenario_yaml(
            scenario_id="destination-legacy",
            overrides={"destination_id": "dest_missing"},
        )
        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        scenario_id = resp.json()["id"]

        get_resp = await client.get(f"/scenarios/{scenario_id}", headers=user_auth_headers)
        assert get_resp.status_code == 200
        assert "destination_id" not in get_resp.json()

    async def test_create_rejects_unsupported_tts_provider_with_error_code(
        self, client, user_auth_headers
    ):
        scenario_yaml = make_scenario_yaml(
            scenario_id="unsupported-provider-create",
            overrides={"config": {"tts_voice": "deepgram:aura-asteria-en"}},
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "tts_provider_unsupported"

    async def test_create_rejects_unconfigured_tts_provider_with_error_code(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", True)
        await _delete_platform_provider_credential(provider_id="elevenlabs:eleven_flash_v2_5")
        scenario_yaml = make_scenario_yaml(
            scenario_id="unconfigured-provider-create",
            overrides={"config": {"tts_voice": "elevenlabs:voice-123"}},
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "tts_provider_unconfigured"

    async def test_create_rejects_tenant_disabled_tts_provider_with_error_code(
        self, client, user_auth_headers
    ):
        await _set_provider_assignment_enabled(
            tenant_id=settings.tenant_id,
            provider_id="openai:gpt-4o-mini-tts",
            enabled=False,
        )
        scenario_yaml = make_scenario_yaml(
            scenario_id="tenant-disabled-provider-create",
            overrides={"config": {"tts_voice": "openai:alloy"}},
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "tts_provider_disabled"

    async def test_create_rejects_unsupported_stt_provider_with_error_code(
        self, client, user_auth_headers
    ):
        scenario_yaml = make_scenario_yaml(
            scenario_id="unsupported-stt-provider-create",
            overrides={
                "config": {
                    "stt_provider": "whisper",
                    "stt_model": "whisper-1",
                }
            },
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "stt_provider_unsupported"

    async def test_create_rejects_disabled_stt_provider_with_error_code(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)
        scenario_yaml = make_scenario_yaml(
            scenario_id="disabled-stt-provider-create",
            overrides={
                "config": {
                    "stt_provider": "deepgram",
                    "stt_model": "nova-2-phonecall",
                }
            },
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "stt_provider_disabled"

    async def test_create_rejects_unconfigured_azure_stt_provider_with_error_code(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
        await _delete_platform_provider_credential(provider_id="azure:azure-speech")
        scenario_yaml = make_scenario_yaml(
            scenario_id="unconfigured-azure-stt-provider-create",
            overrides={
                "config": {
                    "stt_provider": "azure",
                    "stt_model": "azure-default",
                }
            },
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "stt_provider_unconfigured"

    async def test_create_accepts_configured_azure_stt_provider(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
        monkeypatch.setattr(settings, "azure_speech_key", "test-azure-key")
        monkeypatch.setattr(settings, "azure_speech_region", "uksouth")
        monkeypatch.setattr(settings, "azure_speech_endpoint", "")
        await _store_platform_provider_credential(
            provider_id="azure:azure-speech",
            secret_fields={"api_key": "test-azure-key", "region": "uksouth"},
        )
        scenario_yaml = make_scenario_yaml(
            scenario_id="configured-azure-stt-provider-create",
            overrides={
                "config": {
                    "stt_provider": "azure",
                    "stt_model": "azure-default",
                }
            },
        )

        resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == "configured-azure-stt-provider-create"

class TestListScenarios:
    async def test_empty_list(self, client, user_auth_headers):
        resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_upload(self, client, uploaded_scenario, user_auth_headers):
        resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "test-jailbreak"
        assert data[0]["namespace"] is None
        assert data[0]["type"] == "adversarial"
        assert data[0]["scenario_kind"] == "graph"
        assert data[0]["cache_status"] == "warming"

    async def test_list_includes_persisted_namespace(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            row = await store_repo.get_scenario_row_for_tenant(
                db,
                uploaded_scenario["id"],
                settings.tenant_id,
            )
            assert row is not None
            row.namespace = "support/refunds"
            await db.commit()

        resp = await client.get("/scenarios/", headers=user_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["id"] == uploaded_scenario["id"]
        assert data[0]["namespace"] == "support/refunds"

    async def test_list_requires_auth(self, client):
        resp = await client.get("/scenarios/")
        assert resp.status_code == 401

    async def test_list_returns_newest_first(self, client, scenario_yaml, user_auth_headers):
        first = scenario_yaml
        second = make_scenario_yaml(
            scenario_id="test-jailbreak-2",
            name="Jailbreak Test 2",
        )
        r1 = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(first),
            headers=user_auth_headers,
        )
        r2 = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(second),
            headers=user_auth_headers,
        )
        assert r1.status_code == 201
        assert r2.status_code == 201

        listed = await client.get("/scenarios/", headers=user_auth_headers)
        assert listed.status_code == 200
        ids = [row["id"] for row in listed.json()]
        assert ids[:2] == ["test-jailbreak-2", "test-jailbreak"]

class TestGetScenario:
    async def test_get_full_definition(self, client, uploaded_scenario, user_auth_headers):
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}", headers=user_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # Full ScenarioDefinition is returned (not just the summary)
        assert "turns" in data
        assert len(data["turns"]) == 2
        assert data["bot"]["endpoint"] == "sip:bot@test.example.com"

    async def test_get_requires_auth(self, client, uploaded_scenario):
        resp = await client.get(f"/scenarios/{uploaded_scenario['id']}")
        assert resp.status_code == 401

    async def test_get_accepts_harness_service_token(
        self, client, uploaded_scenario, harness_auth_headers
    ):
        """Internal services (harness, judge) must be able to fetch scenario definitions."""
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}", headers=harness_auth_headers
        )
        assert resp.status_code == 200

    async def test_get_not_found_returns_404(self, client, user_auth_headers):
        resp = await client.get("/scenarios/nonexistent-id", headers=user_auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "scenario_not_found"

    async def test_get_can_be_validated_as_scenario_definition(
        self, client, uploaded_scenario, user_auth_headers
    ):
        """The full JSON should round-trip back into a ScenarioDefinition."""
        from botcheck_scenarios import ScenarioDefinition

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}", headers=user_auth_headers
        )
        scenario = ScenarioDefinition.model_validate(resp.json())
        assert scenario.id == "test-jailbreak"

class TestScenarioSource:
    async def test_get_source_returns_yaml(
        self, client, uploaded_scenario, user_auth_headers
    ):
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/source",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == uploaded_scenario["id"]
        assert "yaml_content" in data
        assert "id: test-jailbreak" in data["yaml_content"]

    async def test_get_source_requires_auth(self, client, uploaded_scenario):
        resp = await client.get(f"/scenarios/{uploaded_scenario['id']}/source")
        assert resp.status_code == 401

class TestUpdateScenario:
    async def test_update_replaces_existing_scenario(
        self, client, uploaded_scenario, scenario_yaml, user_auth_headers
    ):
        updated_yaml = make_scenario_yaml(
            scenario_id=uploaded_scenario["id"],
            name="Jailbreak Test Updated",
        )
        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(updated_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Jailbreak Test Updated"
        assert resp.json()["cache_status"] == "warming"

        get_resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}",
            headers=user_auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Jailbreak Test Updated"

    async def test_update_rejects_id_mismatch(
        self, client, uploaded_scenario, scenario_yaml, user_auth_headers
    ):
        mismatched_yaml = make_scenario_yaml(
            scenario_id="another-id",
            name="Jailbreak Test Updated",
        )
        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(mismatched_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "Scenario ID mismatch" in resp.json()["detail"]

    async def test_update_requires_auth(self, client, uploaded_scenario, scenario_yaml):
        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(scenario_yaml),
        )
        assert resp.status_code == 401

    async def test_update_enqueues_warm_cache_job(
        self, client, uploaded_scenario, scenario_yaml, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()
        updated_yaml = make_scenario_yaml(
            scenario_id=uploaded_scenario["id"],
            name="Updated",
        )

        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(updated_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "warm_tts_cache"
        assert kwargs["_queue_name"] == "arq:cache"
        payload = kwargs["payload"]
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["scenario_payload"]["name"] == "Updated"

    async def test_update_accepts_time_route_scenario_and_reenqueues_cache_warm(
        self, client, uploaded_scenario, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()
        updated_yaml = _time_route_scenario_yaml(scenario_id=uploaded_scenario["id"])

        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(updated_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == uploaded_scenario["id"]
        assert data["cache_status"] == "warming"

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "warm_tts_cache"
        payload = kwargs["payload"]
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["scenario_payload"]["turns"][0]["id"] == "t0_pickup"
        assert payload["scenario_payload"]["turns"][0]["kind"] == "bot_listen"
        assert payload["scenario_payload"]["turns"][0]["next"] == "t_route"
        assert payload["scenario_payload"]["turns"][1]["id"] == "t_route"
        assert payload["scenario_payload"]["turns"][1]["kind"] == "time_route"
        assert payload["scenario_payload"]["turns"][1]["default"] == "t_default"
        assert payload["scenario_payload"]["turns"][1]["windows"] == [
            {
                "label": "business_hours",
                "start": "09:00",
                "end": "17:00",
                "next": "t_hours",
            },
            {
                "label": "after_hours",
                "start": "17:00",
                "end": "09:00",
                "next": "t_after",
            },
        ]
        assert payload["scenario_payload"]["turns"][-1]["id"] == "t_end"
        assert payload["scenario_payload"]["turns"][-1]["kind"] == "hangup"

    async def test_update_skips_cache_enqueue_when_feature_disabled(
        self, client, uploaded_scenario, scenario_yaml, user_auth_headers, monkeypatch
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()
        monkeypatch.setattr(settings, "tts_cache_enabled", False)
        updated_yaml = make_scenario_yaml(
            scenario_id=uploaded_scenario["id"],
            name="Updated",
        )

        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(updated_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["cache_status"] == "cold"
        assert resp.json()["cache_updated_at"] is None
        enqueue_mock.assert_not_awaited()

    async def test_update_rejects_disabled_tts_provider_with_error_code(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)
        updated_yaml = make_scenario_yaml(
            scenario_id=uploaded_scenario["id"],
            name="Updated",
            overrides={"config": {"tts_voice": "elevenlabs:voice-123"}},
        )

        resp = await client.put(
            f"/scenarios/{uploaded_scenario['id']}",
            json=make_scenario_upload_payload(updated_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "tts_provider_disabled"

class TestDeleteScenario:
    async def test_delete_existing_scenario(
        self, client, uploaded_scenario, user_auth_headers
    ):
        resp = await client.delete(
            f"/scenarios/{uploaded_scenario['id']}",
            headers=user_auth_headers,
        )
        assert resp.status_code == 204

        list_resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    async def test_delete_not_found_returns_404(self, client, user_auth_headers):
        resp = await client.delete("/scenarios/does-not-exist", headers=user_auth_headers)
        assert resp.status_code == 404

    async def test_delete_requires_auth(self, client, uploaded_scenario):
        resp = await client.delete(f"/scenarios/{uploaded_scenario['id']}")
        assert resp.status_code == 401

    async def test_delete_rejects_when_schedule_references_scenario(
        self, client, uploaded_scenario, user_auth_headers
    ):
        schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"], cron_expr="*/5 * * * *"
            ),
            headers=user_auth_headers,
        )
        assert schedule_resp.status_code == 201

        delete_resp = await client.delete(
            f"/scenarios/{uploaded_scenario['id']}",
            headers=user_auth_headers,
        )
        assert delete_resp.status_code == 409
        assert "referenced by one or more schedules" in delete_resp.json()["detail"]

    async def test_delete_enqueues_purge_cache_job(
        self, client, uploaded_scenario, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()

        resp = await client.delete(
            f"/scenarios/{uploaded_scenario['id']}",
            headers=user_auth_headers,
        )
        assert resp.status_code == 204

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "purge_tts_cache"
        assert kwargs["_queue_name"] == "arq:cache"
        payload = kwargs["payload"]
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["turn_ids"] == ["t1", "t2"]

    async def test_delete_still_enqueues_purge_when_cache_feature_disabled(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()
        monkeypatch.setattr(settings, "tts_cache_enabled", False)

        resp = await client.delete(
            f"/scenarios/{uploaded_scenario['id']}",
            headers=user_auth_headers,
        )
        assert resp.status_code == 204

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "purge_tts_cache"
        assert kwargs["_queue_name"] == "arq:cache"
