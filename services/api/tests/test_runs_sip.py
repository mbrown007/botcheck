"""Tests for SIP-specific run creation behavior."""

from unittest.mock import AsyncMock, patch

from botcheck_api.capacity import build_sip_slot_key
from botcheck_api.config import settings
from botcheck_api.runs.service import DEFAULT_SIP_CAPACITY_SCOPE

from factories import (
    make_run_complete_payload,
    make_run_create_payload,
    make_run_scheduled_payload,
    make_scenario_upload_payload,
    make_sip_scenario_yaml,
)
from runs_test_helpers import SAMPLE_CONVERSATION, _create_run, _livekit_mock


class TestCreateRunSip:

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_from_schedule_throttles_when_sip_slots_exhausted(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.acquire_with_backoff",
            AsyncMock(return_value=False),
        )

        resp = await client.post(
            "/runs/scheduled",
            json=make_run_scheduled_payload(
                sip_uploaded_scenario["id"], schedule_id="sched-1"
            ),
            headers=scheduler_auth_headers,
        )
        assert resp.status_code == 429
        assert "throttled" in resp.json()["detail"].lower()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_schedule_burst_10_with_5_slots_is_deterministic(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        scheduler_auth_headers,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])
        monkeypatch.setattr(settings, "max_concurrent_outbound_calls", 5)
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.acquire_with_backoff",
            AsyncMock(side_effect=[True, True, True, True, True, False, False, False, False, False]),
        )

        statuses: list[int] = []
        for i in range(10):
            resp = await client.post(
                "/runs/scheduled",
                json=make_run_scheduled_payload(
                    sip_uploaded_scenario["id"], schedule_id=f"sched-{i}"
                ),
                headers=scheduler_auth_headers,
            )
            statuses.append(resp.status_code)

        assert statuses.count(202) == 5
        assert statuses.count(429) == 5

        runs_resp = await client.get("/runs/", headers=user_auth_headers)
        assert runs_resp.status_code == 200
        scheduled = [r for r in runs_resp.json() if r["trigger_source"] == "scheduled"]
        assert len(scheduled) == 5

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_dispatches_sip_when_enabled(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "enable_mock_bot", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(sip_uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        mock.sip.create_sip_participant.assert_awaited_once()
        req = mock.sip.create_sip_participant.call_args.args[0]
        assert req.sip_trunk_id == "trunk-test"
        assert req.sip_call_to == "bot"
        # Harness dispatch only; mock bot must not be dispatched when SIP is active.
        assert mock.agent_dispatch.create_dispatch.await_count == 1
        run_id = resp.json()["run_id"]
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        run_payload = run_resp.json()
        assert run_payload["capacity_scope_at_start"] == "tenant-default"
        assert run_payload["capacity_limit_at_start"] == settings.max_concurrent_outbound_calls
        assert run_payload["destination_id_at_start"] is None
        run_created = next(
            e for e in run_payload["events"] if e["type"] == "run_created"
        )
        assert run_created["detail"]["sip_trunk_id"] == "trunk-test"
        assert run_created["detail"]["sip_capacity_scope"] == "tenant-default"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_uses_destination_capacity_scope_when_selected(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Carrier A",
                "protocol": "sip",
                "endpoint": "sip:bot@test.example.com",
                "trunk_id": "trunk-a",
                "is_active": True,
                "provisioned_channels": 5,
                "reserved_channels": 0,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        try_acquire = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": sip_uploaded_scenario["id"],
                "destination_id": destination_id,
            },
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        expected_key = build_sip_slot_key(tenant_id=settings.tenant_id, capacity_scope="carrier-a")
        try_acquire.assert_awaited_once()
        kwargs = try_acquire.await_args.kwargs
        assert kwargs["max_slots"] == 5
        assert kwargs["slot_ttl_s"] == settings.sip_dispatch_slot_ttl_s
        assert kwargs["slot_key"] == expected_key

        run_id = resp.json()["run_id"]
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        payload = run_resp.json()
        assert payload["destination_id_at_start"] == destination_id
        assert payload["transport_profile_id_at_start"] == destination_id
        assert payload["dial_target_at_start"] == "sip:bot@test.example.com"
        assert payload["capacity_scope_at_start"] == "carrier-a"
        assert payload["capacity_limit_at_start"] == 5

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_transport_profile_id_and_dial_target(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Carrier Alias",
                "protocol": "sip",
                "endpoint": "sip:default@test.example.com",
                "trunk_id": "trunk-a",
                "is_active": True,
                "provisioned_channels": 5,
                "reserved_channels": 0,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        try_acquire = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": sip_uploaded_scenario["id"],
                "transport_profile_id": destination_id,
                "dial_target": "sip:override@test.example.com",
            },
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        run_id = resp.json()["run_id"]
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        payload = run_resp.json()
        assert payload["destination_id_at_start"] == destination_id
        assert payload["transport_profile_id_at_start"] == destination_id
        assert payload["dial_target_at_start"] == "sip:override@test.example.com"
        req = mock_lk_class.return_value.sip.create_sip_participant.call_args.args[0]
        assert req.sip_call_to == "override"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_bare_phone_number_with_transport_profile(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["sipgate.co.uk"])

        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Carrier A",
                "protocol": "sip",
                "endpoint": "sip:default@sipgate.co.uk",
                "trunk_id": "trunk-a",
                "is_active": True,
                "provisioned_channels": 1,
                "reserved_channels": 0,
                "capacity_scope": "sipgate.co.uk",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        try_acquire = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": sip_uploaded_scenario["id"],
                "transport_profile_id": destination_id,
                "dial_target": "+447785766172",
            },
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        run_id = resp.json()["run_id"]
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        payload = run_resp.json()
        assert payload["transport_profile_id_at_start"] == destination_id
        assert payload["dial_target_at_start"] == "+447785766172"
        req = mock_lk_class.return_value.sip.create_sip_participant.call_args.args[0]
        assert req.sip_call_to == "+447785766172"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_uses_scenario_endpoint_when_transport_profile_has_no_default_target(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Transport Only",
                "protocol": "sip",
                "trunk_id": "trunk-a",
                "is_active": True,
                "provisioned_channels": 5,
                "reserved_channels": 0,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        try_acquire = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": sip_uploaded_scenario["id"],
                "transport_profile_id": destination_id,
                "dial_target": "+447700900001",
            },
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        req = mock_lk_class.return_value.sip.create_sip_participant.call_args.args[0]
        assert req.sip_call_to == "+447700900001"

    async def test_create_run_rejects_mismatched_transport_profile_aliases(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": uploaded_scenario["id"],
                "destination_id": "dest_a",
                "transport_profile_id": "dest_b",
            },
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "destination_id does not match transport_profile_id" in resp.json()["detail"]

    async def test_create_run_with_transport_profile_when_destinations_disabled_returns_error_code(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_destinations_enabled", False)

        resp = await client.post(
            "/runs/",
            json={
                "scenario_id": uploaded_scenario["id"],
                "transport_profile_id": "dest_primary",
            },
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "destinations_disabled"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_ignores_legacy_scenario_destination_when_request_omits_destination(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="sip-destination-bound",
            overrides={"destination_id": "dest_legacy_ignored"},
        )
        scenario_create = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert scenario_create.status_code == 201
        uploaded = scenario_create.json()

        try_acquire = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

        resp = await client.post(
            "/runs/",
            json={"scenario_id": uploaded["id"]},
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        expected_key = build_sip_slot_key(
            tenant_id=settings.tenant_id,
            capacity_scope=DEFAULT_SIP_CAPACITY_SCOPE,
        )
        try_acquire.assert_awaited_once()
        kwargs = try_acquire.await_args.kwargs
        assert kwargs["max_slots"] == settings.max_concurrent_outbound_calls
        assert kwargs["slot_key"] == expected_key

        run_id = resp.json()["run_id"]
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        payload = run_resp.json()
        assert payload["destination_id_at_start"] is None
        assert payload["capacity_scope_at_start"] == DEFAULT_SIP_CAPACITY_SCOPE
        assert payload["capacity_limit_at_start"] == settings.max_concurrent_outbound_calls

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_sip_without_allowlist(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", [])

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(sip_uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 500
        assert "allowlist" in resp.json()["detail"]
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_fails_fast_when_sip_dispatch_fails(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock.sip.create_sip_participant = AsyncMock(side_effect=RuntimeError("sip failure"))
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "enable_mock_bot", False)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(sip_uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 502
        assert "SIP dispatch failed" in resp.json()["detail"]

        list_resp = await client.get("/runs/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_allows_sip_subdomain_of_allowlisted_domain(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """A SIP endpoint on sub.example.com is allowed when example.com is in the allowlist."""
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "enable_mock_bot", False)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        # Allowlist contains the parent domain; endpoint is on a subdomain.
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["sipgate.co.uk"])

        endpoint = "sip:07785766172@connect.sipgate.co.uk"
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                sip_uploaded_scenario["id"],
                bot_endpoint=endpoint,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        req = mock.sip.create_sip_participant.call_args.args[0]
        assert req.sip_call_to == "07785766172"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_sip_domain_not_in_allowlist(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """A SIP endpoint whose host is not in (or a subdomain of) the allowlist is rejected."""
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["sipgate.co.uk"])

        endpoint = "sip:user@attacker.com"
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                sip_uploaded_scenario["id"],
                bot_endpoint=endpoint,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_sips_endpoint_with_transport_param(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "enable_mock_bot", False)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["sipgate.co.uk"])

        endpoint = "sips:07785766172@sipgate.co.uk;transport=tls"
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                sip_uploaded_scenario["id"],
                bot_endpoint=endpoint,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        req = mock.sip.create_sip_participant.call_args.args[0]
        assert req.sip_call_to == "07785766172"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_sip_scenario_when_outbound_sip_disabled(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """A scenario with protocol=sip must never silently fall back to the mock bot.
        When ENABLE_OUTBOUND_SIP is false the API must return 422 immediately,
        before any LiveKit room or run record is created."""
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", False)
        monkeypatch.setattr(settings, "enable_mock_bot", True)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(sip_uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "sip" in detail.lower()
        assert "ENABLE_OUTBOUND_SIP" in detail
        # No LiveKit room should have been created
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_mock_bot_does_not_fire_for_sip_scenario(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """Even if enable_mock_bot is True, a sip scenario with outbound SIP enabled
        must dispatch SIP only — the mock bot must not be dispatched alongside it."""
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "enable_mock_bot", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(sip_uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        mock.sip.create_sip_participant.assert_awaited_once()
        # Only the harness is dispatched as an agent — mock bot must not be dispatched
        assert mock.agent_dispatch.create_dispatch.await_count == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_releases_sip_slot(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.try_acquire_sip_slot",
            AsyncMock(return_value=True),
        )
        release_mock = AsyncMock()
        monkeypatch.setattr("botcheck_api.runs.runs_events.release_sip_slot", release_mock)

        run_id = await _create_run(client, sip_uploaded_scenario["id"], user_auth_headers)
        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        release_mock.assert_awaited_once()
