import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.main import app
from botcheck_api.models import TenantRow


async def test_features_endpoint_returns_cache_flag(client):
    resp = await client.get("/features")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tts_cache_enabled"] is settings.tts_cache_enabled
    assert data["packs_enabled"] is settings.feature_packs_enabled
    assert data["destinations_enabled"] is settings.feature_destinations_enabled
    assert data["ai_scenarios_enabled"] is settings.feature_ai_scenarios_enabled
    assert data["speech_capabilities"]["stt"] == [
        {
            "id": "deepgram",
            "label": "Deepgram",
            "enabled": bool(settings.feature_stt_provider_deepgram_enabled),
            "voice_mode": "freeform_id",
            "supports_preview": False,
            "supports_cache_warm": False,
            "supports_live_synthesis": False,
            "supports_live_stream": True,
        },
        {
            "id": "azure",
            "label": "Azure Speech",
            "enabled": bool(settings.feature_stt_provider_azure_enabled),
            "voice_mode": "freeform_id",
            "supports_preview": False,
            "supports_cache_warm": False,
            "supports_live_synthesis": False,
            "supports_live_stream": True,
        }
    ]
    assert data["speech_capabilities"]["tts"] == [
        {
            "id": "openai",
            "label": "OpenAI",
            "enabled": bool(settings.feature_tts_provider_openai_enabled),
            "voice_mode": "static_select",
            "supports_preview": True,
            "supports_cache_warm": True,
            "supports_live_synthesis": True,
            "supports_live_stream": True,
        },
        {
            "id": "elevenlabs",
            "label": "ElevenLabs",
            "enabled": bool(settings.feature_tts_provider_elevenlabs_enabled),
            "voice_mode": "freeform_id",
            "supports_preview": True,
            "supports_cache_warm": True,
            "supports_live_synthesis": True,
            "supports_live_stream": True,
        },
    ]
    assert data["provider_degraded"] is False
    assert data["harness_degraded"] is True
    assert data["harness_state"] == "unknown"
    assert isinstance(data["provider_circuits"], list)
    assert len(data["provider_circuits"]) == 9
    assert {row["state"] for row in data["provider_circuits"]} == {"unknown"}


async def test_features_endpoint_reflects_runtime_toggle(client, monkeypatch):
    monkeypatch.setattr(settings, "tts_cache_enabled", False)
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    monkeypatch.setattr(settings, "feature_tts_provider_openai_enabled", False)
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)
    monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
    resp = await client.get("/features")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tts_cache_enabled"] is False
    assert payload["packs_enabled"] is True
    assert payload["destinations_enabled"] is True
    assert payload["ai_scenarios_enabled"] is True
    assert payload["speech_capabilities"]["stt"] == [
        {
            "id": "deepgram",
            "label": "Deepgram",
            "enabled": False,
            "voice_mode": "freeform_id",
            "supports_preview": False,
            "supports_cache_warm": False,
            "supports_live_synthesis": False,
            "supports_live_stream": True,
        },
        {
            "id": "azure",
            "label": "Azure Speech",
            "enabled": True,
            "voice_mode": "freeform_id",
            "supports_preview": False,
            "supports_cache_warm": False,
            "supports_live_synthesis": False,
            "supports_live_stream": True,
        }
    ]
    assert payload["speech_capabilities"]["tts"] == [
        {
            "id": "openai",
            "label": "OpenAI",
            "enabled": False,
            "voice_mode": "static_select",
            "supports_preview": True,
            "supports_cache_warm": True,
            "supports_live_synthesis": True,
            "supports_live_stream": True,
        },
        {
            "id": "elevenlabs",
            "label": "ElevenLabs",
            "enabled": True,
            "voice_mode": "freeform_id",
            "supports_preview": True,
            "supports_cache_warm": True,
            "supports_live_synthesis": True,
            "supports_live_stream": True,
        },
    ]
    assert payload["provider_degraded"] is False
    assert payload["harness_degraded"] is True
    assert payload["harness_state"] == "unknown"


async def test_features_shows_elevenlabs_when_feature_enabled_even_without_api_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")

    resp = await client.get("/features")

    assert resp.status_code == 200
    payload = resp.json()
    elevenlabs = next(
        provider
        for provider in payload["speech_capabilities"]["tts"]
        if provider["id"] == "elevenlabs"
    )
    assert elevenlabs["enabled"] is True


async def test_features_deepgram_enabled_when_api_key_absent(client, monkeypatch):
    """Regression guard: /features must report deepgram enabled by feature flag alone.

    DEEPGRAM_API_KEY lives in the harness agent environment, not the API. The /features
    endpoint must not use the key's presence to determine availability, otherwise the
    AI scenario speech settings UI would always show Deepgram as unavailable.
    """
    monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", True)
    monkeypatch.setattr(settings, "deepgram_api_key", "")

    resp = await client.get("/features")

    assert resp.status_code == 200
    deepgram = next(
        p for p in resp.json()["speech_capabilities"]["stt"] if p["id"] == "deepgram"
    )
    assert deepgram["enabled"] is True


async def test_features_shows_azure_when_feature_enabled_even_without_api_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
    monkeypatch.setattr(settings, "azure_speech_key", "")
    monkeypatch.setattr(settings, "azure_speech_region", "")
    monkeypatch.setattr(settings, "azure_speech_endpoint", "")

    resp = await client.get("/features")

    assert resp.status_code == 200
    azure = next(
        p for p in resp.json()["speech_capabilities"]["stt"] if p["id"] == "azure"
    )
    assert azure["enabled"] is True


async def test_features_applies_tenant_feature_overrides_for_authenticated_user(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", False)
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        tenant = (
            await session.execute(
                select(TenantRow).where(TenantRow.tenant_id == settings.tenant_id)
            )
        ).scalar_one()
        tenant.feature_overrides = {
            "feature_packs_enabled": True,
            "feature_tts_provider_elevenlabs_enabled": True,
        }
        await session.commit()

    anonymous = await client.get("/features")
    assert anonymous.status_code == 200
    assert anonymous.json()["packs_enabled"] is False
    anonymous_elevenlabs = next(
        provider
        for provider in anonymous.json()["speech_capabilities"]["tts"]
        if provider["id"] == "elevenlabs"
    )
    assert anonymous_elevenlabs["enabled"] is False

    authed = await client.get("/features", headers=user_auth_headers)
    assert authed.status_code == 200
    payload = authed.json()
    assert payload["packs_enabled"] is True
    elevenlabs = next(
        provider for provider in payload["speech_capabilities"]["tts"] if provider["id"] == "elevenlabs"
    )
    assert elevenlabs["enabled"] is True


async def test_provider_circuit_upsert_rejects_source_mismatch(client, harness_auth_headers):
    resp = await client.post(
        "/internal/provider-circuits/state",
        json={
            "source": "judge",
            "provider": "openai",
            "service": "tts",
            "component": "judge_cache_warm",
            "state": "open",
        },
        headers=harness_auth_headers,
    )
    assert resp.status_code == 403


async def test_provider_circuit_upsert_updates_features_projection(
    client,
    harness_auth_headers,
):
    storage: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int | None = None):
        del ex
        storage[key] = value
        return True

    async def _get(key: str):
        return storage.get(key)

    app.state.arq_pool.set.side_effect = _set
    app.state.arq_pool.get.side_effect = _get

    observed_at = datetime.now(UTC).isoformat()
    upsert = await client.post(
        "/internal/provider-circuits/state",
        json={
            "source": "agent",
            "provider": "openai",
            "service": "tts",
            "component": "agent_live_tts",
            "state": "open",
            "observed_at": observed_at,
        },
        headers=harness_auth_headers,
    )
    assert upsert.status_code == 200
    assert upsert.json() == {"stored": True}

    features = await client.get("/features")
    assert features.status_code == 200
    payload = features.json()
    assert payload["provider_degraded"] is True
    assert payload["harness_degraded"] is True
    assert payload["harness_state"] == "unknown"

    by_component = {
        (entry["source"], entry["provider"], entry["component"]): entry
        for entry in payload["provider_circuits"]
    }
    agent_tts = by_component[("agent", "openai", "agent_live_tts")]
    assert agent_tts["provider"] == "openai"
    assert agent_tts["service"] == "tts"
    assert agent_tts["state"] == "open"


async def test_provider_circuit_upsert_projects_agent_live_stt_state(
    client,
    harness_auth_headers,
):
    storage: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int | None = None):
        del ex
        storage[key] = value
        return True

    async def _get(key: str):
        return storage.get(key)

    app.state.arq_pool.set.side_effect = _set
    app.state.arq_pool.get.side_effect = _get

    upsert = await client.post(
        "/internal/provider-circuits/state",
        json={
            "source": "agent",
            "provider": "deepgram",
            "service": "stt",
            "component": "agent_live_stt",
            "state": "closed",
            "observed_at": datetime.now(UTC).isoformat(),
        },
        headers=harness_auth_headers,
    )
    assert upsert.status_code == 200

    features = await client.get("/features")
    assert features.status_code == 200
    payload = features.json()
    by_component = {
        (entry["source"], entry["provider"], entry["component"]): entry
        for entry in payload["provider_circuits"]
    }
    agent_stt = by_component[("agent", "deepgram", "agent_live_stt")]
    assert agent_stt["provider"] == "deepgram"
    assert agent_stt["service"] == "stt"
    assert agent_stt["state"] == "closed"


async def test_provider_circuit_upsert_projects_azure_agent_live_stt_state(
    client,
    harness_auth_headers,
):
    storage: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int | None = None):
        del ex
        storage[key] = value
        return True

    async def _get(key: str):
        return storage.get(key)

    app.state.arq_pool.set.side_effect = _set
    app.state.arq_pool.get.side_effect = _get

    upsert = await client.post(
        "/internal/provider-circuits/state",
        json={
            "source": "agent",
            "provider": "azure",
            "service": "stt",
            "component": "agent_live_stt",
            "state": "open",
            "observed_at": datetime.now(UTC).isoformat(),
        },
        headers=harness_auth_headers,
    )
    assert upsert.status_code == 200

    features = await client.get("/features")
    assert features.status_code == 200
    payload = features.json()
    by_component = {
        (entry["source"], entry["provider"], entry["component"]): entry
        for entry in payload["provider_circuits"]
    }
    agent_stt = by_component[("agent", "azure", "agent_live_stt")]
    assert agent_stt["provider"] == "azure"
    assert agent_stt["service"] == "stt"
    assert agent_stt["state"] == "open"


async def test_features_marks_stale_snapshots_unknown(client):
    stale_payload = json.dumps(
        {
            "source": "agent",
            "provider": "openai",
            "service": "tts",
            "component": "agent_live_tts",
            "state": "open",
            "updated_at": (datetime.now(UTC) - timedelta(seconds=600)).isoformat(),
        }
    )

    async def _get(key: str):
        if "agent:openai:tts:agent_live_tts" in key:
            return stale_payload
        return None

    app.state.arq_pool.get.side_effect = _get
    resp = await client.get("/features")
    assert resp.status_code == 200
    payload = resp.json()
    by_component = {
        (entry["source"], entry["provider"], entry["component"]): entry
        for entry in payload["provider_circuits"]
    }
    assert by_component[("agent", "openai", "agent_live_tts")]["state"] == "unknown"
    assert payload["harness_state"] == "unknown"


async def test_features_reports_harness_closed_when_worker_snapshot_is_fresh(
    client,
    harness_auth_headers,
):
    storage: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int | None = None):
        del ex
        storage[key] = value
        return True

    async def _get(key: str):
        return storage.get(key)

    app.state.arq_pool.set.side_effect = _set
    app.state.arq_pool.get.side_effect = _get

    upsert = await client.post(
        "/internal/provider-circuits/state",
        json={
            "source": "agent",
            "provider": "botcheck",
            "service": "harness",
            "component": "worker",
            "state": "closed",
            "observed_at": datetime.now(UTC).isoformat(),
        },
        headers=harness_auth_headers,
    )
    assert upsert.status_code == 200

    features = await client.get("/features")
    assert features.status_code == 200
    payload = features.json()
    assert payload["harness_degraded"] is False
    assert payload["harness_state"] == "closed"
