from __future__ import annotations

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.packs.service_models import DiscoveredSIPTrunk
from botcheck_api.packs.service_sip_trunks import sync_sip_trunks

from factories import make_pack_upsert_payload, make_schedule_create_payload
from runs_test_helpers import _other_tenant_headers


def _sip_payload(**overrides):
    payload = {
        "name": "Staging SIP Trunk",
        "protocol": "sip",
        "endpoint": "sip:bot@carrier.example.com",
        "caller_id": "+15551230000",
        "trunk_id": "trunk-a",
        "trunk_pool_id": None,
        "headers": {"X-Region": "us-east-1"},
        "is_active": True,
        "provisioned_channels": 10,
        "reserved_channels": 2,
        "capacity_scope": "carrier-a",
    }
    payload.update(overrides)
    return payload


def _http_payload(**overrides):
    payload = {
        "name": "Direct HTTP Bot",
        "protocol": "http",
        "endpoint": "https://bot.internal/chat",
        "headers": {"Authorization": "Bearer test-token"},
        "direct_http_config": {
            "method": "POST",
            "request_content_type": "json",
            "request_text_field": "message",
            "request_history_field": "history",
            "request_session_id_field": "session_id",
            "request_body_defaults": {
                "dashboard_context": {
                    "uid": "ops-overview",
                    "time_range": {"from": "now-6h", "to": "now"},
                }
            },
            "response_text_field": "reply",
            "timeout_s": 20,
        },
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _webrtc_payload(**overrides):
    payload = {
        "name": "Bot Builder Preview",
        "protocol": "webrtc",
        "headers": {"Authorization": "Bearer preview-token"},
        "webrtc_config": {
            "api_base_url": "https://bot-builder.internal",
            "agent_id": "monitoring-assistant",
            "version_id": "ver_2026_04_03",
            "auth_headers": {"Authorization": "Bearer builder-token"},
            "join_timeout_s": 25,
        },
        "is_active": True,
    }
    payload.update(overrides)
    return payload


async def test_destinations_routes_return_503_when_feature_disabled(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", False)

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 503
    assert list_resp.json()["error_code"] == "destinations_disabled"

    create_resp = await client.post(
        "/destinations/",
        json=_sip_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 503
    assert create_resp.json()["error_code"] == "destinations_disabled"

    trunks_resp = await client.get("/destinations/trunks", headers=user_auth_headers)
    assert trunks_resp.status_code == 503
    assert trunks_resp.json()["error_code"] == "destinations_disabled"


async def test_list_sip_trunks_returns_synced_rows(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        await sync_sip_trunks(
            session,
            discovered=[
                DiscoveredSIPTrunk(
                    trunk_id="trunk-sync-a",
                    name="Sipgate Primary",
                    provider_name="sipgate.co.uk",
                    address="sipgate.co.uk",
                    transport="SIP_TRANSPORT_AUTO",
                    numbers=["+447700900001"],
                    metadata_json={"source": "test"},
                )
            ],
        )
        await session.commit()

    resp = await client.get("/destinations/trunks", headers=user_auth_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["trunk_id"] == "trunk-sync-a"
    assert payload[0]["name"] == "Sipgate Primary"
    assert payload[0]["provider_name"] == "sipgate.co.uk"
    assert payload[0]["address"] == "sipgate.co.uk"
    assert payload[0]["numbers"] == ["+447700900001"]
    assert payload[0]["is_active"] is True


async def test_sync_sip_trunks_marks_missing_rows_inactive(db_setup):
    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        await sync_sip_trunks(
            session,
            discovered=[
                DiscoveredSIPTrunk(
                    trunk_id="trunk-sync-a",
                    name="Sipgate Primary",
                    provider_name="sipgate.co.uk",
                    address="sipgate.co.uk",
                    transport="SIP_TRANSPORT_AUTO",
                    numbers=["+447700900001"],
                    metadata_json={},
                ),
                DiscoveredSIPTrunk(
                    trunk_id="trunk-sync-b",
                    name="Carrier B",
                    provider_name="carrier-b.example",
                    address="carrier-b.example",
                    transport="SIP_TRANSPORT_TLS",
                    numbers=[],
                    metadata_json={},
                ),
            ],
        )
        await session.commit()

    async with factory() as session:
        rows = await sync_sip_trunks(
            session,
            discovered=[
                DiscoveredSIPTrunk(
                    trunk_id="trunk-sync-a",
                    name="Sipgate Primary",
                    provider_name="sipgate.co.uk",
                    address="sipgate.co.uk",
                    transport="SIP_TRANSPORT_AUTO",
                    numbers=["+447700900001"],
                    metadata_json={"refresh": True},
                )
            ],
        )
        await session.commit()

    by_id = {row.trunk_id: row for row in rows}
    assert by_id["trunk-sync-a"].is_active is True
    assert by_id["trunk-sync-b"].is_active is False


async def test_destinations_crud_lifecycle_with_effective_channels(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_sip_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["destination_id"].startswith("dest_")
    assert created["transport_profile_id"] == created["destination_id"]
    assert created["default_dial_target"] == "sip:bot@carrier.example.com"
    assert created["effective_channels"] == 8
    assert created["active_schedule_count"] == 0
    assert created["active_pack_run_count"] == 0
    assert created["in_use"] is False
    destination_id = created["destination_id"]

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert [row["destination_id"] for row in listed] == [destination_id]
    assert listed[0]["transport_profile_id"] == destination_id
    assert listed[0]["default_dial_target"] == "sip:bot@carrier.example.com"
    assert listed[0]["effective_channels"] == 8
    assert listed[0]["trunk_id"] == "trunk-a"
    assert listed[0]["trunk_pool_id"] is None
    assert listed[0]["provisioned_channels"] == 10
    assert listed[0]["reserved_channels"] == 2
    assert listed[0]["active_schedule_count"] == 0
    assert listed[0]["active_pack_run_count"] == 0
    assert listed[0]["in_use"] is False

    detail_resp = await client.get(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["name"] == "Staging SIP Trunk"
    assert detail_resp.json()["transport_profile_id"] == destination_id
    assert detail_resp.json()["default_dial_target"] == "sip:bot@carrier.example.com"
    assert detail_resp.json()["trunk_pool_id"] is None
    assert detail_resp.json()["active_schedule_count"] == 0
    assert detail_resp.json()["active_pack_run_count"] == 0
    assert detail_resp.json()["in_use"] is False

    update_resp = await client.put(
        f"/destinations/{destination_id}",
        json=_sip_payload(botcheck_max_channels=6),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["botcheck_max_channels"] == 6
    assert updated["effective_channels"] == 6

    delete_resp = await client.delete(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert missing_resp.status_code == 404


async def test_destinations_sip_profile_round_trips_trunk_pool_id(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_sip_payload(name="Pooled SIP Trunk", trunk_id=None, trunk_pool_id="pool_outbound_uk"),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["trunk_id"] is None
    assert created["trunk_pool_id"] == "pool_outbound_uk"

    detail_resp = await client.get(f"/destinations/{created['destination_id']}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["trunk_pool_id"] == "pool_outbound_uk"


async def test_destinations_reject_capacity_fields_for_non_sip_protocol(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Mock Bot",
            "protocol": "mock",
            "endpoint": "mock://echo",
            "provisioned_channels": 5,
            "capacity_scope": "carrier-a",
        },
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    assert "only valid for sip" in resp.json()["detail"].lower()


async def test_destinations_http_profile_round_trips_direct_http_config(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_http_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["protocol"] == "http"
    assert created["endpoint"] == "https://bot.internal/chat"
    assert created["default_dial_target"] == "https://bot.internal/chat"
    assert created["direct_http_config"]["request_text_field"] == "message"
    assert created["direct_http_config"]["request_body_defaults"]["dashboard_context"]["uid"] == "ops-overview"
    assert created["direct_http_config"]["response_text_field"] == "reply"
    destination_id = created["destination_id"]

    detail_resp = await client.get(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["direct_http_config"]["timeout_s"] == 20
    assert detail["direct_http_config"]["request_body_defaults"]["dashboard_context"]["time_range"]["to"] == "now"


async def test_destinations_http_mode_defaults_to_generic_json(
    client,
    user_auth_headers,
    monkeypatch,
):
    """Existing profiles without http_mode round-trip as generic_json."""
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    payload = _http_payload()
    del payload["direct_http_config"]["method"]  # omit http_mode — should default
    create_resp = await client.post("/destinations/", json=payload, headers=user_auth_headers)
    assert create_resp.status_code == 201
    assert create_resp.json()["direct_http_config"]["http_mode"] == "generic_json"


async def test_destinations_json_sse_chat_mode_round_trips(
    client,
    user_auth_headers,
    monkeypatch,
):
    """json_sse_chat profiles save with history_field omitted and round-trip correctly."""
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    payload = _http_payload(
        name="SSE Chat Bot",
        direct_http_config={
            "http_mode": "json_sse_chat",
            "request_text_field": "message",
            "request_history_field": None,
            "request_session_id_field": "session_id",
            "timeout_s": 30,
            "max_retries": 1,
        },
    )
    create_resp = await client.post("/destinations/", json=payload, headers=user_auth_headers)
    assert create_resp.status_code == 201
    cfg = create_resp.json()["direct_http_config"]
    assert cfg["http_mode"] == "json_sse_chat"
    assert cfg["request_text_field"] == "message"
    assert cfg["request_history_field"] is None

    detail = await client.get(
        f"/destinations/{create_resp.json()['destination_id']}",
        headers=user_auth_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["direct_http_config"]["http_mode"] == "json_sse_chat"


async def test_destinations_http_mode_invalid_value_rejected(
    client,
    user_auth_headers,
    monkeypatch,
):
    """Unknown http_mode values are rejected with 422."""
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    payload = _http_payload(
        direct_http_config={
            "http_mode": "carrier_pigeon",
            "request_text_field": "message",
            "response_text_field": "response",
        }
    )
    resp = await client.post("/destinations/", json=payload, headers=user_auth_headers)
    assert resp.status_code == 422


async def test_destinations_webrtc_profile_round_trips_webrtc_config(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_webrtc_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["protocol"] == "webrtc"
    assert created["webrtc_config"]["provider"] == "livekit"
    assert created["webrtc_config"]["session_mode"] == "bot_builder_preview"
    assert created["webrtc_config"]["agent_id"] == "monitoring-assistant"
    assert created["webrtc_config"]["auth_headers"] == {"Authorization": "Bearer builder-token"}
    destination_id = created["destination_id"]

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    row = next(r for r in list_resp.json() if r["destination_id"] == destination_id)
    assert row["webrtc_config"]["api_base_url"] == "https://bot-builder.internal"
    assert row["webrtc_config"]["version_id"] == "ver_2026_04_03"
    assert row["webrtc_config"]["auth_headers"] == {}

    detail_resp = await client.get(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["webrtc_config"]["join_timeout_s"] == 25
    assert detail_resp.json()["webrtc_config"]["auth_headers"] == {
        "Authorization": "Bearer builder-token"
    }


async def test_destinations_webrtc_profile_defaults_provider_and_session_mode(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    payload = _webrtc_payload(
        webrtc_config={
            "api_base_url": "https://bot-builder.internal",
            "agent_id": "monitoring-assistant",
            "version_id": "ver_defaulted",
        }
    )
    create_resp = await client.post("/destinations/", json=payload, headers=user_auth_headers)
    assert create_resp.status_code == 201
    cfg = create_resp.json()["webrtc_config"]
    assert cfg["provider"] == "livekit"
    assert cfg["session_mode"] == "bot_builder_preview"
    assert cfg["join_timeout_s"] == 20
    assert cfg["auth_headers"] == {}


async def test_list_endpoint_omits_header_values_but_exposes_count(
    client,
    user_auth_headers,
    monkeypatch,
):
    """List endpoint must not expose header values (credential exposure risk).

    header_count is safe to return; the actual key/value pairs are
    detail-only so viewers cannot harvest bearer tokens from the list.
    """
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post("/destinations/", json=_http_payload(), headers=user_auth_headers)
    assert create_resp.status_code == 201
    destination_id = create_resp.json()["destination_id"]

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    row = next(r for r in list_resp.json() if r["destination_id"] == destination_id)
    # header_count present with the correct count
    assert row["header_count"] == 1
    # raw header values must not appear on the list response
    assert "headers" not in row

    # Detail endpoint does expose the full headers dict
    detail_resp = await client.get(f"/destinations/{destination_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["headers"] == {"Authorization": "Bearer test-token"}


async def test_destinations_reject_http_config_for_non_http_protocol(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json=_sip_payload(
            direct_http_config={
                "request_text_field": "message",
                "response_text_field": "response",
            }
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    if isinstance(detail, list):
        assert any("direct_http_config is only valid" in str(item.get("msg", "")) for item in detail)
    else:
        assert "direct_http_config is only valid" in detail


async def test_destinations_reject_webrtc_config_for_non_webrtc_protocol(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json=_http_payload(
            webrtc_config={
                "api_base_url": "https://bot-builder.internal",
                "agent_id": "monitoring-assistant",
                "version_id": "ver_2026_04_03",
            }
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    if isinstance(detail, list):
        assert any("webrtc_config is only valid" in str(item.get("msg", "")) for item in detail)
    else:
        assert "webrtc_config is only valid" in detail


async def test_destinations_reject_webrtc_profile_without_webrtc_config(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={"name": "Broken WebRTC", "protocol": "webrtc", "is_active": True},
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    if isinstance(detail, list):
        assert any("webrtc_config is required" in str(item.get("msg", "")) for item in detail)
    else:
        assert "webrtc_config is required" in detail


async def test_destinations_reject_webrtc_profile_with_non_object_config(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Broken WebRTC",
            "protocol": "webrtc",
            "webrtc_config": "not-an-object",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    # Pydantic rejects a non-dict value at request-parse time; the service-layer
    # isinstance guard is only reached by internal (non-HTTP) callers.
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("webrtc_config" in str(item.get("loc", "")) for item in detail)


async def test_update_destination_non_existent_returns_404(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.put(
        "/destinations/dest_missing",
        json=_sip_payload(),
        headers=user_auth_headers,
    )
    assert resp.status_code == 404


async def test_get_destination_other_tenant_isolated(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_sip_payload(name="Tenant A"),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    destination_id = create_resp.json()["destination_id"]

    cross_tenant_resp = await client.get(
        f"/destinations/{destination_id}",
        headers=_other_tenant_headers(),
    )
    assert cross_tenant_resp.status_code in (403, 404)


async def test_create_destination_rejects_duplicate_name_in_tenant(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    first = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Name"),
        headers=user_auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Name"),
        headers=user_auth_headers,
    )
    assert second.status_code == 422
    assert "already exists" in second.json()["detail"].lower()


async def test_create_destination_accepts_default_dial_target_alias(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Profile Alias",
            "protocol": "sip",
            "default_dial_target": "sip:alias@carrier.example.com",
            "trunk_id": "trunk-alias",
            "provisioned_channels": 2,
            "reserved_channels": 0,
            "capacity_scope": "carrier-alias",
        },
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["endpoint"] == "sip:alias@carrier.example.com"
    assert payload["default_dial_target"] == "sip:alias@carrier.example.com"


async def test_create_transport_profile_without_default_dial_target(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Transport Only",
            "protocol": "sip",
            "trunk_id": "trunk-transport-only",
            "provisioned_channels": 2,
            "reserved_channels": 0,
            "capacity_scope": "carrier-transport-only",
        },
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["endpoint"] is None
    assert payload["default_dial_target"] is None


async def test_create_destination_accepts_matching_endpoint_and_default_dial_target(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Profile Alias Match",
            "protocol": "sip",
            "endpoint": "sip:match@carrier.example.com",
            "default_dial_target": "sip:match@carrier.example.com",
            "trunk_id": "trunk-alias",
            "provisioned_channels": 2,
            "reserved_channels": 0,
            "capacity_scope": "carrier-alias",
        },
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["endpoint"] == "sip:match@carrier.example.com"
    assert payload["default_dial_target"] == "sip:match@carrier.example.com"


async def test_create_destination_rejects_mismatched_endpoint_and_default_dial_target(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json={
            "name": "Profile Alias Mismatch",
            "protocol": "sip",
            "endpoint": "sip:one@carrier.example.com",
            "default_dial_target": "sip:two@carrier.example.com",
            "trunk_id": "trunk-alias",
            "provisioned_channels": 2,
            "reserved_channels": 0,
            "capacity_scope": "carrier-alias",
        },
        headers=user_auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("must match" in str(item.get("msg", "")).lower() for item in detail)


async def test_update_destination_accepts_default_dial_target_alias(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    create_resp = await client.post(
        "/destinations/",
        json=_sip_payload(name="Profile Alias Update"),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    destination_id = create_resp.json()["destination_id"]

    update_resp = await client.put(
        f"/destinations/{destination_id}",
        json={
            "name": "Profile Alias Update",
            "protocol": "sip",
            "default_dial_target": "sip:update@carrier.example.com",
            "trunk_id": "trunk-a",
            "provisioned_channels": 10,
            "reserved_channels": 2,
            "capacity_scope": "carrier-a",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["endpoint"] == "sip:update@carrier.example.com"
    assert payload["default_dial_target"] == "sip:update@carrier.example.com"


async def test_create_destination_rejects_shared_trunk_scope_mismatch(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    first = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Trunk A", trunk_id="trunk-shared", capacity_scope="scope-a"),
        headers=user_auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Trunk B", trunk_id="trunk-shared", capacity_scope="scope-b"),
        headers=user_auth_headers,
    )
    assert second.status_code == 422
    assert "same effective capacity scope" in second.json()["detail"].lower()


async def test_create_destination_rejects_shared_trunk_custom_scope_when_peer_uses_default_scope(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    first = await client.post(
        "/destinations/",
        json=_sip_payload(
            name="Shared Trunk Default",
            trunk_id="trunk-shared-default",
            capacity_scope=None,
        ),
        headers=user_auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/destinations/",
        json=_sip_payload(
            name="Shared Trunk Custom",
            trunk_id="trunk-shared-default",
            capacity_scope="scope-custom",
        ),
        headers=user_auth_headers,
    )
    assert second.status_code == 422
    assert "same effective capacity scope" in second.json()["detail"].lower()


async def test_update_destination_rejects_shared_trunk_scope_mismatch(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    first = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Trunk Update A", trunk_id="trunk-update", capacity_scope="scope-a"),
        headers=user_auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/destinations/",
        json=_sip_payload(name="Shared Trunk Update B", trunk_id="trunk-update", capacity_scope="scope-a"),
        headers=user_auth_headers,
    )
    assert second.status_code == 201
    second_id = second.json()["destination_id"]

    update = await client.put(
        f"/destinations/{second_id}",
        json=_sip_payload(
            name="Shared Trunk Update B",
            trunk_id="trunk-update",
            capacity_scope="scope-b",
        ),
        headers=user_auth_headers,
    )
    assert update.status_code == 422
    assert "same effective capacity scope" in update.json()["detail"].lower()


async def test_delete_destination_rejects_when_active_schedule_references_override(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    create_destination = await client.post(
        "/destinations/",
        json=_sip_payload(name="Schedule Protected Destination"),
        headers=user_auth_headers,
    )
    assert create_destination.status_code == 201
    destination_id = create_destination.json()["destination_id"]

    create_schedule = await client.post(
        "/schedules/",
        json=make_schedule_create_payload(
            uploaded_scenario["id"],
            cron_expr="*/15 * * * *",
            config_overrides={"destination_id": destination_id},
        ),
        headers=user_auth_headers,
    )
    assert create_schedule.status_code == 201

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    usage_row = next((row for row in list_resp.json() if row["destination_id"] == destination_id), None)
    assert usage_row is not None
    assert usage_row["active_schedule_count"] == 1
    assert usage_row["active_pack_run_count"] == 0
    assert usage_row["in_use"] is True

    delete_resp = await client.delete(
        f"/destinations/{destination_id}",
        headers=user_auth_headers,
    )
    assert delete_resp.status_code == 409
    assert delete_resp.json()["error_code"] == "destination_in_use"
    detail = delete_resp.json()["detail"]
    assert "active schedules" in detail.lower()
    assert "active_schedule_count=1" in detail


async def test_delete_destination_rejects_when_active_pack_run_references_destination(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    create_destination = await client.post(
        "/destinations/",
        json=_sip_payload(name="Pack Protected Destination"),
        headers=user_auth_headers,
    )
    assert create_destination.status_code == 201
    destination_id = create_destination.json()["destination_id"]

    create_pack = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Destination Delete Guard Pack",
            scenario_ids=[uploaded_scenario["id"]],
        ),
        headers=user_auth_headers,
    )
    assert create_pack.status_code == 201
    pack_id = create_pack.json()["pack_id"]

    run_pack = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": destination_id},
        headers=user_auth_headers,
    )
    assert run_pack.status_code == 202

    list_resp = await client.get("/destinations/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    usage_row = next((row for row in list_resp.json() if row["destination_id"] == destination_id), None)
    assert usage_row is not None
    assert usage_row["active_schedule_count"] == 0
    assert usage_row["active_pack_run_count"] == 1
    assert usage_row["in_use"] is True

    delete_resp = await client.delete(
        f"/destinations/{destination_id}",
        headers=user_auth_headers,
    )
    assert delete_resp.status_code == 409
    assert delete_resp.json()["error_code"] == "destination_in_use"
    detail = delete_resp.json()["detail"]
    assert "active pack runs" in detail.lower()
    assert "active_pack_run_count=1" in detail


async def test_update_destination_rejects_deactivation_when_active_schedule_references_override(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    create_destination = await client.post(
        "/destinations/",
        json=_sip_payload(name="Schedule Active Destination"),
        headers=user_auth_headers,
    )
    assert create_destination.status_code == 201
    destination_id = create_destination.json()["destination_id"]

    create_schedule = await client.post(
        "/schedules/",
        json=make_schedule_create_payload(
            uploaded_scenario["id"],
            cron_expr="*/15 * * * *",
            config_overrides={"destination_id": destination_id},
        ),
        headers=user_auth_headers,
    )
    assert create_schedule.status_code == 201

    deactivate_resp = await client.put(
        f"/destinations/{destination_id}",
        json=_sip_payload(name="Schedule Active Destination", is_active=False),
        headers=user_auth_headers,
    )
    assert deactivate_resp.status_code == 409
    assert deactivate_resp.json()["error_code"] == "destination_in_use"
    detail = deactivate_resp.json()["detail"]
    assert "active schedules" in detail.lower()
    assert "active_schedule_count=1" in detail


async def test_update_destination_rejects_deactivation_when_active_pack_run_references_destination(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    create_destination = await client.post(
        "/destinations/",
        json=_sip_payload(name="Pack Active Destination"),
        headers=user_auth_headers,
    )
    assert create_destination.status_code == 201
    destination_id = create_destination.json()["destination_id"]

    create_pack = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Destination Deactivation Guard Pack",
            scenario_ids=[uploaded_scenario["id"]],
        ),
        headers=user_auth_headers,
    )
    assert create_pack.status_code == 201
    pack_id = create_pack.json()["pack_id"]

    run_pack = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": destination_id},
        headers=user_auth_headers,
    )
    assert run_pack.status_code == 202

    deactivate_resp = await client.put(
        f"/destinations/{destination_id}",
        json=_sip_payload(name="Pack Active Destination", is_active=False),
        headers=user_auth_headers,
    )
    assert deactivate_resp.status_code == 409
    assert deactivate_resp.json()["error_code"] == "destination_in_use"
    detail = deactivate_resp.json()["detail"]
    assert "active pack runs" in detail.lower()
    assert "active_pack_run_count=1" in detail
