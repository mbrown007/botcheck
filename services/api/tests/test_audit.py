"""Tests for immutable audit log endpoints and write paths."""

from unittest.mock import AsyncMock, MagicMock, patch

from jose import jwt

from botcheck_api.config import settings

from factories import (
    make_conversation_turn,
    make_run_complete_payload,
    make_run_create_payload,
    make_run_fail_payload,
    make_run_patch_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)

SAMPLE_CONVERSATION = [
    make_conversation_turn(
        turn_id="t1",
        turn_number=1,
        speaker="harness",
        text="Hello.",
        audio_start_ms=0,
        audio_end_ms=800,
    ),
]


def _other_tenant_headers() -> dict[str, str]:
    token = jwt.encode(
        {"sub": "other-user", "tenant_id": "other-tenant", "role": "admin", "iss": settings.auth_issuer},
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _livekit_mock():
    m = MagicMock()
    m.room.create_room = AsyncMock(return_value=MagicMock())
    m.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    m.sip.create_sip_participant = AsyncMock(return_value=MagicMock())
    m.aclose = AsyncMock()
    return m


class TestAuditAPI:
    async def test_list_audit_requires_auth(self, client):
        resp = await client.get("/audit/")
        assert resp.status_code == 401

    async def test_scenario_create_writes_audit_event(
        self,
        client,
        scenario_yaml,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        scenario_id = create_resp.json()["id"]

        audit_resp = await client.get("/audit/?action=scenario.upsert", headers=user_auth_headers)
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "scenario.upsert"
        assert event["resource_type"] == "scenario"
        assert event["resource_id"] == scenario_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_run_create_writes_audit_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        audit_resp = await client.get("/audit/?action=run.create", headers=user_auth_headers)
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "run.create"
        assert event["resource_type"] == "run"
        assert event["resource_id"] == run_id

    async def test_list_audit_cross_tenant_forbidden(self, client):
        resp = await client.get("/audit/", headers=_other_tenant_headers())
        assert resp.status_code == 403

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_run_complete_callback_writes_audit_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = (
            await client.post(
                "/runs/",
                json=make_run_create_payload(uploaded_scenario["id"]),
                headers=user_auth_headers,
            )
        ).json()["run_id"]

        resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        audit_resp = await client.get(
            "/audit/?action=run.complete_callback", headers=user_auth_headers
        )
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "run.complete_callback"
        assert event["resource_type"] == "run"
        assert event["resource_id"] == run_id
        assert event["actor_type"] == "service"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_run_fail_callback_writes_audit_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = (
            await client.post(
                "/runs/",
                json=make_run_create_payload(uploaded_scenario["id"]),
                headers=user_auth_headers,
            )
        ).json()["run_id"]

        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="Agent crashed"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        audit_resp = await client.get(
            "/audit/?action=run.fail_callback", headers=user_auth_headers
        )
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "run.fail_callback"
        assert event["resource_type"] == "run"
        assert event["resource_id"] == run_id
        assert event["actor_type"] == "service"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_run_judge_patch_writes_audit_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = (
            await client.post(
                "/runs/",
                json=make_run_create_payload(uploaded_scenario["id"]),
                headers=user_auth_headers,
            )
        ).json()["run_id"]
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        patch_resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(gate_result="passed", summary="All good."),
            headers=judge_auth_headers,
        )
        assert patch_resp.status_code == 200

        audit_resp = await client.get(
            "/audit/?action=run.judge_patch", headers=user_auth_headers
        )
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "run.judge_patch"
        assert event["resource_type"] == "run"
        assert event["resource_id"] == run_id
        assert event["actor_id"] == "judge"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_list_audit_filter_by_resource_type(
        self,
        mock_lk_class,
        client,
        scenario_yaml,
        uploaded_scenario,
        user_auth_headers,
    ):
        """resource_type filter returns only matching events."""
        mock_lk_class.return_value = _livekit_mock()
        # uploaded_scenario fixture already created a scenario.upsert event.
        # Upload a second scenario to have two scenario events.
        yaml2 = make_scenario_yaml(
            scenario_id="test-jailbreak-2",
            name="Jailbreak Test 2",
        )
        await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(yaml2),
            headers=user_auth_headers,
        )

        scenario_events = await client.get(
            "/audit/?resource_type=scenario", headers=user_auth_headers
        )
        assert scenario_events.status_code == 200
        data = scenario_events.json()
        assert all(e["resource_type"] == "scenario" for e in data)

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_list_audit_filter_by_actor_id(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """actor_id filter returns only events from that actor."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = (
            await client.post(
                "/runs/",
                json=make_run_create_payload(uploaded_scenario["id"]),
                headers=user_auth_headers,
            )
        ).json()["run_id"]
        await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="timeout"),
            headers=harness_auth_headers,
        )

        harness_events = await client.get(
            "/audit/?actor_id=harness", headers=user_auth_headers
        )
        assert harness_events.status_code == 200
        data = harness_events.json()
        assert len(data) >= 1
        assert all(e["actor_id"] == "harness" for e in data)
