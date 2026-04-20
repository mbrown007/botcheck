"""Tests for POST /runs/ create lifecycle behavior."""

import json
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from botcheck_observability.trace_contract import (
    ATTR_RUN_ID,
    ATTR_SCHEDULE_ID,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_KIND,
    ATTR_TENANT_ID,
    ATTR_TRANSPORT_KIND,
    ATTR_TRANSPORT_PROFILE_ID,
    ATTR_TRIGGER_SOURCE,
    SPAN_LIVEKIT_DISPATCH,
    SPAN_RUN_LIFECYCLE,
    SPAN_SIP_DISPATCH,
)
from botcheck_api import database, store_repo
from botcheck_api.config import settings
from botcheck_api.models import (
    AIPersonaRow,
    AIScenarioRecordRow,
    AIScenarioRow,
    ProviderCredentialRow,
    RunRow,
    SIPTrunkRow,
    ScenarioKind,
    TenantProviderAssignmentRow,
    TenantTrunkPoolRow,
    TrunkPoolMemberRow,
    TrunkPoolRow,
)
from botcheck_api.runs import service as runs_service
from botcheck_api.runs import service_lifecycle as runs_lifecycle_service
from botcheck_api.scenarios.service import ScenarioCacheInspection
from botcheck_api.providers.service import ensure_provider_registry_seeded

from factories import (
    make_playground_run_payload,
    make_run_create_payload,
    make_run_scheduled_payload,
    make_scenario_upload_payload,
    make_sip_scenario_yaml,
    make_turn,
)
from runs_test_helpers import _livekit_mock, _set_scenario_cache_status
from scenarios_test_helpers import store_scenario_yaml_direct
from scenario_test_helpers import _set_scenario_kind


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
        row = (
            await session.execute(
                select(ProviderCredentialRow).where(
                    ProviderCredentialRow.owner_scope == "platform",
                    ProviderCredentialRow.tenant_id.is_(None),
                    ProviderCredentialRow.provider_id == provider_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        await session.delete(row)
        await session.commit()


class _FakeSpan(AbstractContextManager[None]):
    def __init__(self, recorder: list[tuple[str, dict[str, str] | None]], name: str, attributes):
        self._recorder = recorder
        self._name = name
        self._attributes = dict(attributes) if attributes is not None else None

    def __enter__(self):
        self._recorder.append((self._name, self._attributes))
        return None

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FakeTracer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def start_as_current_span(self, name: str, *, attributes=None):
        return _FakeSpan(self.calls, name, attributes)


def _http_destination_payload(**overrides):
    payload = {
        "name": "Direct HTTP Profile",
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
            "response_text_field": "response.text",
            "timeout_s": 15,
            "max_retries": 2,
        },
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _webrtc_destination_payload(**overrides):
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


def _webrtc_bootstrap(**overrides):
    payload = {
        "provider": "livekit",
        "session_mode": "bot_builder_preview",
        "api_base_url": "https://bot-builder.internal",
        "agent_id": "monitoring-assistant",
        "version_id": "ver_2026_04_03",
        "session_id": "preview_123",
        "room_name": "preview-monitoring-assistant-preview_123",
        "participant_name": "operator-preview_123",
        "server_url": "wss://livekit.bot-builder.test",
        "participant_token": "jwt-preview-token",
        "join_timeout_s": 25,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


async def _create_webrtc_run(
    *,
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    create_dest = await client.post(
        "/destinations/",
        json=_webrtc_destination_payload(),
        headers=user_auth_headers,
    )
    assert create_dest.status_code == 201
    destination_id = create_dest.json()["destination_id"]

    monkeypatch.setattr(
        runs_lifecycle_service,
        "resolve_bot_builder_preview_bootstrap",
        AsyncMock(return_value=_webrtc_bootstrap()),
    )

    run_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(
            uploaded_scenario["id"],
            transport_profile_id=destination_id,
        ),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    return run_resp.json(), destination_id


async def _create_trunk_pool_fixture(
    *,
    tenant_id: str = "default",
    trunk_pool_id: str = "pool_outbound_uk",
    trunk_id: str = "trunk-uk-1",
    provider_name: str = "sipgate.co.uk",
) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        db.add(
            SIPTrunkRow(
                trunk_id=trunk_id,
                name="UK Primary",
                provider_name=provider_name,
                address="sipgate.co.uk",
                transport="SIP_TRANSPORT_AUTO",
                numbers=["+447700900001"],
                metadata_json={},
                is_active=True,
                last_synced_at=datetime.now(UTC),
            )
        )
        db.add(
            TrunkPoolRow(
                trunk_pool_id=trunk_pool_id,
                provider_name=provider_name,
                name="UK Outbound",
                selection_policy="first_available",
                is_active=True,
            )
        )
        db.add(
            TrunkPoolMemberRow(
                trunk_pool_member_id="member_pool_uk_1",
                trunk_pool_id=trunk_pool_id,
                trunk_id=trunk_id,
                priority=10,
                is_active=True,
            )
        )
        db.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id="tenant_pool_default_uk",
                tenant_id=tenant_id,
                trunk_pool_id=trunk_pool_id,
                tenant_label="UK Testing",
                is_default=True,
                is_active=True,
            )
        )
        await db.commit()

async def _create_ai_scenario_binding(
    *,
    scenario_id: str,
    ai_scenario_id: str,
    config: dict | None = None,
    tenant_id: str = "default",
) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        persona = await store_repo.get_ai_persona_row_for_tenant(
            db,
            "persona_runs_create_ai",
            tenant_id,
        )
        if persona is None:
            persona = AIPersonaRow(
                persona_id="persona_runs_create_ai",
                tenant_id=tenant_id,
                name="Runs Create AI Persona",
                system_prompt="Act as a realistic customer.",
                style="neutral",
                voice="alloy",
                is_active=True,
            )
            await store_repo.add_ai_persona_row(db, persona)

        row = await store_repo.get_ai_scenario_row_for_tenant(db, scenario_id, tenant_id)
        if row is None:
            row = AIScenarioRow(
                scenario_id=scenario_id,
                ai_scenario_id=ai_scenario_id,
                tenant_id=tenant_id,
                name="Runs Create AI Scenario",
                persona_id=persona.persona_id,
                scenario_brief="Caller wants airline delay support.",
                scenario_facts={"booking_ref": "ABC123"},
                evaluation_objective="Confirm the delay and next steps clearly.",
                opening_strategy="wait_for_bot_greeting",
                is_active=True,
                scoring_profile="default",
                dataset_source="manual",
                config=config or {},
            )
            await store_repo.add_ai_scenario_row(db, row)
        else:
            row.ai_scenario_id = ai_scenario_id
            row.config = config or {}
        await db.commit()


class TestCreateRunLifecycle:

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_mock_transport_failure_does_not_persist_pending_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock = _livekit_mock()
        mock.room.create_room.side_effect = RuntimeError("livekit room create failed")
        mock_lk_class.return_value = mock

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 502
        assert resp.json()["detail"] == "LiveKit dispatch failed — run not created"

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(RunRow).where(RunRow.scenario_id == uploaded_scenario["id"])
                )
            ).scalars().all()
            assert rows == []

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_playground_run_mock_persists_contract_fields(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()

        resp = await client.post(
            "/runs/playground",
            json=make_playground_run_payload(
                scenario_id=uploaded_scenario["id"],
                playground_mode="mock",
                system_prompt="You are a calm support bot.",
                tool_stubs={"lookup_account": {"status": "active"}},
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["run_type"] == "playground"
        assert payload["playground_mode"] == "mock"
        assert payload["transport"] == "mock"
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["run_type"] == "playground"
        assert metadata["playground_mode"] == "mock"
        assert metadata["transport"] == "mock"
        assert metadata["bot_protocol"] == "mock"

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            row = await db.get(RunRow, payload["run_id"])
            assert row is not None
            assert row.run_type == "playground"
            assert row.playground_mode == "mock"
            assert row.playground_system_prompt == "You are a calm support bot."
            assert row.playground_tool_stubs == {"lookup_account": {"status": "active"}}

    async def test_create_playground_run_direct_http_requires_transport_profile_id(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/runs/playground",
            json=make_playground_run_payload(
                scenario_id=uploaded_scenario["id"],
                playground_mode="direct_http",
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert "transport_profile_id is required for direct_http playground runs" in resp.text

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_playground_run_direct_http_persists_contract_fields(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/playground",
            json=make_playground_run_payload(
                scenario_id=uploaded_scenario["id"],
                playground_mode="direct_http",
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["run_type"] == "playground"
        assert payload["playground_mode"] == "direct_http"
        assert payload["transport"] == "http"
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["run_type"] == "playground"
        assert metadata["playground_mode"] == "direct_http"
        assert metadata["transport"] == "http"
        assert metadata["bot_protocol"] == "http"
        assert metadata["transport_profile_id"] == destination_id

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            row = await db.get(RunRow, payload["run_id"])
            assert row is not None
            assert row.run_type == "playground"
            assert row.playground_mode == "direct_http"
            assert row.playground_system_prompt is None
            assert row.playground_tool_stubs is None

    async def test_create_playground_run_rejects_sip_scenario(
        self,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/runs/playground",
            json=make_playground_run_payload(
                scenario_id=sip_uploaded_scenario["id"],
                playground_mode="mock",
                system_prompt="You are a playground mock.",
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert "not supported for playground runs" in resp.text

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_includes_trace_context_in_room_metadata(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(
            runs_lifecycle_service,
            "current_w3c_trace_context",
            lambda: {
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                "tracestate": "vendor=test",
            },
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["traceparent"] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        assert metadata["tracestate"] == "vendor=test"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_emits_canonical_run_and_livekit_spans(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        tracer = _FakeTracer()
        monkeypatch.setattr(runs_lifecycle_service, "_tracer", tracer)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert [name for name, _attrs in tracer.calls] == [
            SPAN_RUN_LIFECYCLE,
            SPAN_LIVEKIT_DISPATCH,
        ]
        lifecycle_attrs = tracer.calls[0][1] or {}
        assert lifecycle_attrs[ATTR_RUN_ID] == metadata["run_id"]
        assert lifecycle_attrs[ATTR_SCENARIO_ID] == uploaded_scenario["id"]
        assert lifecycle_attrs[ATTR_SCENARIO_KIND] == metadata["scenario_kind"]
        assert lifecycle_attrs[ATTR_TENANT_ID] == metadata["tenant_id"]
        assert lifecycle_attrs[ATTR_TRIGGER_SOURCE] == "manual"
        assert lifecycle_attrs[ATTR_TRANSPORT_KIND] == metadata["transport"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_valid_scenario_returns_202(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        data = resp.json()
        assert data["scenario_id"] == uploaded_scenario["id"]
        assert data["state"] == "pending"
        assert data["run_id"].startswith("run_")
        assert data["livekit_room"].startswith("botcheck-run_")
        assert data["trigger_source"] == "manual"
        assert data["transport"] in {"none", "mock", "sip"}
        assert data["tts_cache_status_at_start"] == uploaded_scenario["cache_status"]
        assert data["retention_profile"] == "standard"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_http_transport_skips_speech_readiness_and_cache_preflight(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        monkeypatch.setattr(
            runs_lifecycle_service,
            "assert_tenant_tts_voice_available",
            AsyncMock(side_effect=AssertionError("tts readiness should be skipped")),
        )
        monkeypatch.setattr(
            runs_lifecycle_service,
            "assert_tenant_stt_config_available",
            AsyncMock(side_effect=AssertionError("stt readiness should be skipped")),
        )
        monkeypatch.setattr(
            runs_lifecycle_service,
            "inspect_scenario_tts_cache",
            AsyncMock(side_effect=AssertionError("tts cache inspection should be skipped")),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["transport"] == "http"
        assert payload["destination_id_at_start"] == destination_id
        assert payload["transport_profile_id_at_start"] == destination_id
        assert payload["dial_target_at_start"] == "https://bot.internal/chat"
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["transport"] == "http"
        assert metadata["bot_protocol"] == "http"
        assert metadata["transport_profile_id"] == destination_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_webrtc_transport_records_bootstrap_metadata(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_webrtc_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        monkeypatch.setattr(
            runs_lifecycle_service,
            "resolve_bot_builder_preview_bootstrap",
            AsyncMock(
                return_value=SimpleNamespace(
                    provider="livekit",
                    session_mode="bot_builder_preview",
                    api_base_url="https://bot-builder.internal",
                    agent_id="monitoring-assistant",
                    version_id="ver_2026_04_03",
                    session_id="preview_123",
                    room_name="preview-monitoring-assistant-preview_123",
                    participant_name="operator-preview_123",
                    server_url="wss://livekit.bot-builder.test",
                    participant_token="jwt-preview-token",
                    join_timeout_s=25,
                )
            ),
        )
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["transport"] == "webrtc"
        assert payload["destination_id_at_start"] == destination_id
        assert payload["transport_profile_id_at_start"] == destination_id
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["transport"] == "webrtc"
        assert metadata["bot_protocol"] == "webrtc"
        assert metadata["webrtc_session_id"] == "preview_123"
        assert metadata["webrtc_remote_room_name"] == "preview-monitoring-assistant-preview_123"
        assert metadata["webrtc_participant_name"] == "operator-preview_123"
        assert "webrtc_server_url" not in metadata
        assert "webrtc_participant_token" not in metadata
        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            row = await db.get(RunRow, payload["run_id"])
            assert row is not None
            assert row.webrtc_config_at_start == {
                "provider": "livekit",
                "session_mode": "bot_builder_preview",
                "api_base_url": "https://bot-builder.internal",
                "agent_id": "monitoring-assistant",
                "version_id": "ver_2026_04_03",
                "auth_headers": {"Authorization": "Bearer builder-token"},
                "join_timeout_s": 25,
            }

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_can_fetch_webrtc_transport_context_without_room_metadata_token(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        # Both service_lifecycle and runs_lifecycle import `from livekit import api as lk_api`,
        # so they share the same underlying module object. A single patch covers both.
        lk = _livekit_mock()
        mock_lk_class.return_value = lk
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_webrtc_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        monkeypatch.setattr(
            runs_lifecycle_service,
            "resolve_bot_builder_preview_bootstrap",
            AsyncMock(
                return_value=SimpleNamespace(
                    provider="livekit",
                    session_mode="bot_builder_preview",
                    api_base_url="https://bot-builder.internal",
                    agent_id="monitoring-assistant",
                    version_id="ver_2026_04_03",
                    session_id="preview_123",
                    room_name="preview-monitoring-assistant-preview_123",
                    participant_name="operator-preview_123",
                    server_url="wss://livekit.bot-builder.test",
                    participant_token="jwt-preview-token",
                    join_timeout_s=25,
                )
            ),
        )
        monkeypatch.setattr(
            "botcheck_api.runs.runs_lifecycle.service_webrtc.resolve_bot_builder_preview_token",
            AsyncMock(
                return_value=SimpleNamespace(
                    server_url="wss://livekit.bot-builder.test",
                    participant_token="jwt-preview-token",
                )
            ),
        )

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        create_req = lk.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert "webrtc_server_url" not in metadata
        assert "webrtc_participant_token" not in metadata
        runs_list_resp = SimpleNamespace(
            rooms=[
                SimpleNamespace(
                    name=run_resp.json()["livekit_room"],
                    metadata=create_req.metadata,
                )
            ]
        )
        lk.room.list_rooms = AsyncMock(return_value=runs_list_resp)

        transport_resp = await client.get(
            f"/runs/{run_id}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )
        assert transport_resp.status_code == 200
        payload = transport_resp.json()
        assert payload["run_id"] == run_id
        assert payload["transport_profile_id"] == destination_id
        assert payload["webrtc_session_id"] == "preview_123"
        assert payload["webrtc_remote_room_name"] == "preview-monitoring-assistant-preview_123"
        assert payload["webrtc_participant_name"] == "operator-preview_123"
        assert payload["webrtc_server_url"] == "wss://livekit.bot-builder.test"
        assert payload["webrtc_participant_token"] == "jwt-preview-token"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_webrtc_transport_context_returns_404_when_livekit_room_missing(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        # Both service_lifecycle and runs_lifecycle import `from livekit import api as lk_api`,
        # so they share the same underlying module object. A single patch covers both.
        lk = _livekit_mock()
        mock_lk_class.return_value = lk
        run_payload, _destination_id = await _create_webrtc_run(
            client=client,
            uploaded_scenario=uploaded_scenario,
            user_auth_headers=user_auth_headers,
            monkeypatch=monkeypatch,
        )
        token_refresh = AsyncMock()
        monkeypatch.setattr(
            "botcheck_api.runs.runs_lifecycle.service_webrtc.resolve_bot_builder_preview_token",
            token_refresh,
        )
        lk.room.list_rooms = AsyncMock(return_value=SimpleNamespace(rooms=[]))

        transport_resp = await client.get(
            f"/runs/{run_payload['run_id']}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )

        assert transport_resp.status_code == 404
        assert transport_resp.json()["detail"] == "Run has no WebRTC bootstrap metadata"
        token_refresh.assert_not_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_webrtc_transport_context_returns_404_when_session_id_missing(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        lk = _livekit_mock()
        mock_lk_class.return_value = lk
        run_payload, _destination_id = await _create_webrtc_run(
            client=client,
            uploaded_scenario=uploaded_scenario,
            user_auth_headers=user_auth_headers,
            monkeypatch=monkeypatch,
        )
        create_req = lk.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        metadata.pop("webrtc_session_id", None)
        token_refresh = AsyncMock()
        monkeypatch.setattr(
            "botcheck_api.runs.runs_lifecycle.service_webrtc.resolve_bot_builder_preview_token",
            token_refresh,
        )
        lk.room.list_rooms = AsyncMock(
            return_value=SimpleNamespace(
                rooms=[
                    SimpleNamespace(
                        name=run_payload["livekit_room"],
                        metadata=json.dumps(metadata),
                    )
                ]
            )
        )

        transport_resp = await client.get(
            f"/runs/{run_payload['run_id']}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )

        assert transport_resp.status_code == 404
        assert transport_resp.json()["detail"] == "Run has no WebRTC session id"
        token_refresh.assert_not_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_webrtc_transport_context_uses_run_snapshot_after_transport_profile_deleted(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        lk = _livekit_mock()
        mock_lk_class.return_value = lk
        run_payload, destination_id = await _create_webrtc_run(
            client=client,
            uploaded_scenario=uploaded_scenario,
            user_auth_headers=user_auth_headers,
            monkeypatch=monkeypatch,
        )
        create_req = lk.room.create_room.await_args.args[0]
        lk.room.list_rooms = AsyncMock(
            return_value=SimpleNamespace(
                rooms=[
                    SimpleNamespace(
                        name=run_payload["livekit_room"],
                        metadata=create_req.metadata,
                    )
                ]
            )
        )
        token_refresh = AsyncMock(
            return_value=SimpleNamespace(
                server_url="wss://livekit.bot-builder.test",
                participant_token="jwt-preview-token",
            )
        )
        monkeypatch.setattr(
            "botcheck_api.runs.runs_lifecycle.service_webrtc.resolve_bot_builder_preview_token",
            token_refresh,
        )

        delete_resp = await client.delete(
            f"/destinations/{destination_id}",
            headers=user_auth_headers,
        )
        assert delete_resp.status_code == 204

        transport_resp = await client.get(
            f"/runs/{run_payload['run_id']}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )

        assert transport_resp.status_code == 200
        payload = transport_resp.json()
        assert payload["run_id"] == run_payload["run_id"]
        assert payload["transport_profile_id"] == destination_id
        assert payload["webrtc_session_id"] == "preview_123"
        assert payload["webrtc_server_url"] == "wss://livekit.bot-builder.test"
        assert payload["webrtc_participant_token"] == "jwt-preview-token"
        assert token_refresh.await_args.kwargs["webrtc_config"] == {
            "provider": "livekit",
            "session_mode": "bot_builder_preview",
            "api_base_url": "https://bot-builder.internal",
            "agent_id": "monitoring-assistant",
            "version_id": "ver_2026_04_03",
            "auth_headers": {"Authorization": "Bearer builder-token"},
            "join_timeout_s": 25,
        }
        assert token_refresh.await_args.kwargs["session_id"] == "preview_123"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_webrtc_transport_context_prefers_snapshot_over_mutated_destination(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """Snapshot takes priority even when the live destination row still exists.

        Creates a run (snapshot captured with original config), then mutates the
        destination via PUT. The transport-context endpoint must use the snapshotted
        config, not the mutated live row.
        """
        lk = _livekit_mock()
        mock_lk_class.return_value = lk
        run_payload, destination_id = await _create_webrtc_run(
            client=client,
            uploaded_scenario=uploaded_scenario,
            user_auth_headers=user_auth_headers,
            monkeypatch=monkeypatch,
        )
        create_req = lk.room.create_room.await_args.args[0]
        lk.room.list_rooms = AsyncMock(
            return_value=SimpleNamespace(
                rooms=[
                    SimpleNamespace(
                        name=run_payload["livekit_room"],
                        metadata=create_req.metadata,
                    )
                ]
            )
        )

        # Mutate destination webrtc_config after the run was created
        mutated_payload = _webrtc_destination_payload(
            webrtc_config={
                "api_base_url": "https://mutated.example.com",
                "agent_id": "different-agent",
                "version_id": "ver_mutated",
                "auth_headers": {"Authorization": "Bearer mutated-token"},
                "join_timeout_s": 99,
            }
        )
        put_resp = await client.put(
            f"/destinations/{destination_id}",
            json=mutated_payload,
            headers=user_auth_headers,
        )
        assert put_resp.status_code == 200

        token_refresh = AsyncMock(
            return_value=SimpleNamespace(
                server_url="wss://livekit.bot-builder.test",
                participant_token="jwt-preview-token",
            )
        )
        monkeypatch.setattr(
            "botcheck_api.runs.runs_lifecycle.service_webrtc.resolve_bot_builder_preview_token",
            token_refresh,
        )

        transport_resp = await client.get(
            f"/runs/{run_payload['run_id']}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )

        assert transport_resp.status_code == 200
        # Must use the snapshotted config, not the mutated live destination row
        assert token_refresh.await_args.kwargs["webrtc_config"] == {
            "provider": "livekit",
            "session_mode": "bot_builder_preview",
            "api_base_url": "https://bot-builder.internal",
            "agent_id": "monitoring-assistant",
            "version_id": "ver_2026_04_03",
            "auth_headers": {"Authorization": "Bearer builder-token"},
            "join_timeout_s": 25,
        }
        assert token_refresh.await_args.kwargs["session_id"] == "preview_123"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_webrtc_transport_failure_does_not_persist_pending_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock.room.create_room.side_effect = RuntimeError("livekit room create failed")
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_webrtc_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        monkeypatch.setattr(
            runs_lifecycle_service,
            "resolve_bot_builder_preview_bootstrap",
            AsyncMock(
                return_value=SimpleNamespace(
                    provider="livekit",
                    session_mode="bot_builder_preview",
                    api_base_url="https://bot-builder.internal",
                    agent_id="monitoring-assistant",
                    version_id="ver_2026_04_03",
                    session_id="preview_123",
                    room_name="preview-monitoring-assistant-preview_123",
                    participant_name="operator-preview_123",
                    server_url="wss://livekit.bot-builder.test",
                    participant_token="jwt-preview-token",
                    join_timeout_s=25,
                )
            ),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 502
        assert resp.json()["detail"] == "LiveKit dispatch failed — run not created"

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(RunRow).where(RunRow.scenario_id == uploaded_scenario["id"])
                )
            ).scalars().all()
            assert rows == []

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_http_transport_includes_trace_context_and_http_span_attrs(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        tracer = _FakeTracer()
        monkeypatch.setattr(runs_lifecycle_service, "_tracer", tracer)
        monkeypatch.setattr(
            runs_lifecycle_service,
            "current_w3c_trace_context",
            lambda: {
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                "tracestate": "vendor=test",
            },
        )
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["traceparent"] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        assert metadata["tracestate"] == "vendor=test"
        assert metadata["transport_profile_id"] == destination_id
        assert metadata["transport"] == "http"
        assert [name for name, _attrs in tracer.calls] == [
            SPAN_RUN_LIFECYCLE,
            SPAN_LIVEKIT_DISPATCH,
        ]
        lifecycle_attrs = tracer.calls[0][1] or {}
        assert lifecycle_attrs[ATTR_RUN_ID] == metadata["run_id"]
        assert lifecycle_attrs[ATTR_SCENARIO_ID] == uploaded_scenario["id"]
        assert lifecycle_attrs[ATTR_TRIGGER_SOURCE] == "manual"
        assert lifecycle_attrs[ATTR_TRANSPORT_KIND] == "http"
        assert lifecycle_attrs[ATTR_TRANSPORT_PROFILE_ID] == destination_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_can_fetch_run_http_transport_context(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        transport_resp = await client.get(
            f"/runs/{run_id}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )
        assert transport_resp.status_code == 200
        payload = transport_resp.json()
        assert payload["run_id"] == run_id
        assert payload["transport_profile_id"] == destination_id
        assert payload["endpoint"] == "https://bot.internal/chat"
        assert payload["headers"]["Authorization"] == "Bearer test-token"
        assert payload["direct_http_config"]["response_text_field"] == "response.text"
        assert payload["direct_http_config"]["request_body_defaults"]["dashboard_context"]["uid"] == "ops-overview"
        assert payload["direct_http_config"]["max_retries"] == 2
        assert payload["playground_mode"] is None
        assert payload["playground_system_prompt"] is None
        assert payload["playground_tool_stubs"] is None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_can_fetch_playground_mock_context(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()

        run_resp = await client.post(
            "/runs/playground",
            json=make_playground_run_payload(
                scenario_id=uploaded_scenario["id"],
                playground_mode="mock",
                system_prompt="You are a calm support bot.",
                tool_stubs={"lookup_account": {"status": "active"}},
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        transport_resp = await client.get(
            f"/runs/{run_id}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )
        assert transport_resp.status_code == 200
        payload = transport_resp.json()
        assert payload["run_id"] == run_id
        assert payload["playground_mode"] == "mock"
        assert payload["playground_system_prompt"] == "You are a calm support bot."
        assert payload["playground_tool_stubs"] == {"lookup_account": {"status": "active"}}
        assert payload["transport_profile_id"] is None
        assert payload["endpoint"] is None
        assert payload["headers"] == {}
        assert payload["direct_http_config"] == {}

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_harness_fetches_http_transport_context_from_run_snapshot_not_live_destination(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        patch_dest = await client.put(
            f"/destinations/{destination_id}",
            json=_http_destination_payload(
                headers={"Authorization": "Bearer rotated-token"},
                direct_http_config={
                    "method": "POST",
                    "request_content_type": "json",
                    "request_text_field": "prompt",
                    "request_history_field": "conversation",
                    "request_session_id_field": "session_id",
                    "request_body_defaults": {
                        "dashboard_context": {
                            "uid": "rotated-dashboard",
                        }
                    },
                    "response_text_field": "data.answer",
                    "timeout_s": 45,
                    "max_retries": 0,
                },
            ),
            headers=user_auth_headers,
        )
        assert patch_dest.status_code == 200

        transport_resp = await client.get(
            f"/runs/{run_id}/transport-context",
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )
        assert transport_resp.status_code == 200
        payload = transport_resp.json()
        assert payload["run_id"] == run_id
        assert payload["transport_profile_id"] == destination_id
        assert payload["endpoint"] == "https://bot.internal/chat"
        assert payload["headers"]["Authorization"] == "Bearer test-token"
        assert payload["direct_http_config"]["request_text_field"] == "message"
        assert payload["direct_http_config"]["request_body_defaults"]["dashboard_context"]["uid"] == "ops-overview"
        assert payload["direct_http_config"]["response_text_field"] == "response.text"
        assert payload["direct_http_config"]["max_retries"] == 2

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_resolves_sip_trunk_from_pool_backed_destination(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["carrier.example.com"])
        monkeypatch.setattr(
            runs_lifecycle_service,
            "load_sip_credentials",
            AsyncMock(return_value=object()),
        )
        monkeypatch.setattr(
            runs_lifecycle_service,
            "try_acquire_sip_slot",
            AsyncMock(return_value=True),
        )
        await _create_trunk_pool_fixture()
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-sip-pool-backed",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
        )
        await store_scenario_yaml_direct(scenario_yaml)
        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Pool-backed SIP Destination",
                "protocol": "sip",
                "endpoint": "sip:bot@carrier.example.com",
                "caller_id": "+15551230000",
                "trunk_pool_id": "pool_outbound_uk",
                "headers": {},
                "is_active": True,
                "provisioned_channels": 10,
                "reserved_channels": 1,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-sip-pool-backed", transport_profile_id=destination_id),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["trunk_pool_id"] == "pool_outbound_uk"
        # SIP participant was dispatched (resolver reached dispatch layer)
        mock_lk_class.return_value.sip.create_sip_participant.assert_awaited_once()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_sip_emits_canonical_sip_dispatch_span(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        tracer = _FakeTracer()
        monkeypatch.setattr(runs_lifecycle_service, "_tracer", tracer)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["carrier.example.com"])
        monkeypatch.setattr(
            runs_lifecycle_service,
            "load_sip_credentials",
            AsyncMock(return_value=object()),
        )
        monkeypatch.setattr(
            runs_lifecycle_service,
            "try_acquire_sip_slot",
            AsyncMock(return_value=True),
        )
        await _create_trunk_pool_fixture()
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-sip-trace-span",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
        )
        await store_scenario_yaml_direct(scenario_yaml)
        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Trace SIP Destination",
                "protocol": "sip",
                "endpoint": "sip:bot@carrier.example.com",
                "caller_id": "+15551230000",
                "trunk_pool_id": "pool_outbound_uk",
                "headers": {},
                "is_active": True,
                "provisioned_channels": 10,
                "reserved_channels": 1,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-sip-trace-span", transport_profile_id=destination_id),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        assert [name for name, _attrs in tracer.calls] == [
            SPAN_RUN_LIFECYCLE,
            SPAN_LIVEKIT_DISPATCH,
            SPAN_SIP_DISPATCH,
        ]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_supports_ad_hoc_trunk_pool_without_transport_profile(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["carrier.example.com"])
        monkeypatch.setattr(
            runs_lifecycle_service,
            "load_sip_credentials",
            AsyncMock(return_value=object()),
        )
        monkeypatch.setattr(
            runs_lifecycle_service,
            "try_acquire_sip_slot",
            AsyncMock(return_value=True),
        )
        await _create_trunk_pool_fixture()
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-sip-pool-ad-hoc",
            overrides={"bot": {"endpoint": "sip:bot@carrier.example.com"}},
            turns=[make_turn(turn_id="t1", text="Hello there.")],
        )
        await store_scenario_yaml_direct(scenario_yaml)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                "run-sip-pool-ad-hoc",
                dial_target="+441234567890",
                trunk_pool_id="pool_outbound_uk",
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock_lk_class.return_value.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["trunk_pool_id"] == "pool_outbound_uk"
        sip_request = mock_lk_class.return_value.sip.create_sip_participant.await_args.args[0]
        assert sip_request.sip_call_to == "+441234567890"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_sip_destination_with_unassigned_trunk_pool(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        monkeypatch.setattr(settings, "enable_outbound_sip", True)

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            db.add(
                SIPTrunkRow(
                    trunk_id="trunk-uk-unassigned",
                    name="UK Unassigned",
                    provider_name="sipgate.co.uk",
                    address="sipgate.co.uk",
                    transport="SIP_TRANSPORT_AUTO",
                    numbers=["+447700900009"],
                    metadata_json={},
                    is_active=True,
                    last_synced_at=datetime.now(UTC),
                )
            )
            db.add(
                TrunkPoolRow(
                    trunk_pool_id="pool_unassigned",
                    provider_name="sipgate.co.uk",
                    name="Unassigned Pool",
                    selection_policy="first_available",
                    is_active=True,
                )
            )
            db.add(
                TrunkPoolMemberRow(
                    trunk_pool_member_id="member_pool_unassigned_1",
                    trunk_pool_id="pool_unassigned",
                    trunk_id="trunk-uk-unassigned",
                    priority=10,
                    is_active=True,
                )
            )
            await db.commit()

        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-sip-pool-unassigned",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
        )
        await store_scenario_yaml_direct(scenario_yaml)
        create_dest = await client.post(
            "/destinations/",
            json={
                "name": "Unassigned Pool Destination",
                "protocol": "sip",
                "endpoint": "sip:bot@carrier.example.com",
                "caller_id": "+15551230000",
                "trunk_pool_id": "pool_unassigned",
                "headers": {},
                "is_active": True,
                "provisioned_channels": 10,
                "reserved_channels": 1,
                "capacity_scope": "carrier-a",
            },
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                "run-sip-pool-unassigned",
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "trunk_pool_unassigned"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejected_when_harness_health_gate_enabled_and_unknown(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "run_dispatch_require_harness_healthy", True)
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 503
        payload = resp.json()
        assert payload["error_code"] == "harness_unavailable"
        assert "state=unknown" in payload["detail"]
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_snapshots_scenario_cache_status_at_start(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        await _set_scenario_cache_status(uploaded_scenario["id"], "warm")
        monkeypatch.setattr(
            runs_lifecycle_service,
            "inspect_scenario_tts_cache",
            AsyncMock(
                return_value=ScenarioCacheInspection(
                    cache_status="warm",
                    cached_turns=1,
                    failed_turns=0,
                    total_harness_turns=1,
                    manifest_present=True,
                    turn_states=[{"turn_id": "t1", "status": "cached", "key": "default/tts-cache/t1/hit.wav"}],
                )
            ),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        assert resp.json()["tts_cache_status_at_start"] == "warm"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_downgrades_stale_warm_cache_status_when_objects_missing(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        await _set_scenario_cache_status(uploaded_scenario["id"], "warm")
        monkeypatch.setattr(
            runs_lifecycle_service,
            "inspect_scenario_tts_cache",
            AsyncMock(
                return_value=ScenarioCacheInspection(
                    cache_status="cold",
                    cached_turns=0,
                    failed_turns=1,
                    total_harness_turns=1,
                    manifest_present=False,
                    turn_states=[{"turn_id": "t1", "status": "failed", "key": None}],
                )
            ),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        assert resp.json()["tts_cache_status_at_start"] == "cold"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_smoke_scenario_when_tts_cache_not_ready(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        yaml_content = make_sip_scenario_yaml(
            scenario_id="smoke-cache-preflight",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
            overrides={"tags": ["smoke-test", "sip"]},
        )
        upload_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(yaml_content),
            headers=user_auth_headers,
        )
        assert upload_resp.status_code == 201
        await _set_scenario_cache_status("smoke-cache-preflight", "warm")
        monkeypatch.setattr(
            runs_lifecycle_service,
            "inspect_scenario_tts_cache",
            AsyncMock(
                return_value=ScenarioCacheInspection(
                    cache_status="partial",
                    cached_turns=0,
                    failed_turns=1,
                    total_harness_turns=1,
                    manifest_present=False,
                    turn_states=[{"turn_id": "t1", "status": "failed", "key": "default/tts-cache/t1/miss.wav"}],
                )
            ),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("smoke-cache-preflight"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 409
        payload = resp.json()
        assert payload["error_code"] == "tts_cache_unavailable"
        assert "missing turns: t1" in payload["detail"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_retention_profile_override(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                retention_profile="compliance",
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        assert resp.json()["retention_profile"] == "compliance"

    async def test_create_run_rejects_invalid_retention_profile(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                retention_profile="forever",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_unknown_scenario_returns_404(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("does-not-exist"),
            headers=user_auth_headers,
        )
        assert resp.status_code == 404

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_unconfigured_tts_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        await _delete_platform_provider_credential(provider_id="openai:gpt-4o-mini-tts")

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_unconfigured"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_disabled_elevenlabs_before_dispatch(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-disabled-elevenlabs",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
            overrides={"config": {"tts_voice": "elevenlabs:voice-123"}},
        )
        await store_scenario_yaml_direct(scenario_yaml)
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-disabled-elevenlabs"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_disabled"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_tenant_disabled_tts_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        await _set_provider_assignment_enabled(
            tenant_id=settings.tenant_id,
            provider_id="openai:gpt-4o-mini-tts",
            enabled=False,
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_disabled"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_succeeds_when_deepgram_api_key_absent(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        """Regression guard: DEEPGRAM_API_KEY lives in the harness, not the API.

        The API dispatch path must never reject a run solely because deepgram_api_key
        is absent from the API service environment. This test directly guards against
        the error_stt_provider_unconfigured regression introduced in 17.11.e.
        """
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "deepgram_api_key", "")

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_unsupported_stt_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
    ):
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-unsupported-stt",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
            overrides={
                "config": {
                    "stt_provider": "whisper",
                    "stt_model": "whisper-1",
                }
            },
        )
        await store_scenario_yaml_direct(scenario_yaml)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-unsupported-stt"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "stt_provider_unsupported"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_disabled_stt_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-disabled-stt",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
            overrides={
                "config": {
                    "stt_provider": "deepgram",
                    "stt_model": "nova-2-phonecall",
                }
            },
        )
        await store_scenario_yaml_direct(scenario_yaml)
        monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-disabled-stt"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "stt_provider_disabled"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_unconfigured_azure_stt_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        scenario_yaml = make_sip_scenario_yaml(
            scenario_id="run-unconfigured-azure-stt",
            turns=[make_turn(turn_id="t1", text="Hello there.")],
            overrides={
                "config": {
                    "stt_provider": "azure",
                    "stt_model": "azure-default",
                }
            },
        )
        await store_scenario_yaml_direct(scenario_yaml)
        monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
        await _delete_platform_provider_credential(provider_id="azure:azure-speech")

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("run-unconfigured-azure-stt"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "stt_provider_unconfigured"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_allows_ai_scenario_when_feature_enabled(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        payload = resp.json()
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["state"] == "pending"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_public_ai_scenario_id(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_public_id",
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_delay_public_id"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["scenario_id"] == uploaded_scenario["id"]
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["scenario_id"] == uploaded_scenario["id"]
        assert metadata["ai_scenario_id"] == "ai_delay_public_id"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_accepts_public_ai_scenario_id_with_http_transport_profile(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_http_public_id",
            config={"tts_voice": "openai:nova"},
        )
        create_dest = await client.post(
            "/destinations/",
            json=_http_destination_payload(
                headers={"Authorization": "Bearer ai-http-token"},
            ),
            headers=user_auth_headers,
        )
        assert create_dest.status_code == 201
        destination_id = create_dest.json()["destination_id"]

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                "",
                ai_scenario_id="ai_delay_http_public_id",
                transport_profile_id=destination_id,
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        payload = resp.json()
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["transport"] == "http"
        assert payload["destination_id_at_start"] == destination_id
        assert payload["transport_profile_id_at_start"] == destination_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_disabled_ai_tts_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_disabled_tts",
            config={"tts_voice": "elevenlabs:voice-123"},
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_delay_disabled_tts"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_disabled"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_unconfigured_ai_tts_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", True)
        await _delete_platform_provider_credential(provider_id="elevenlabs:eleven_flash_v2_5")
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_unconfigured_tts",
            config={"tts_voice": "elevenlabs:voice-123"},
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_delay_unconfigured_tts"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_unconfigured"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_disabled_ai_stt_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_disabled_stt",
            config={"stt_provider": "deepgram", "stt_model": "nova-2-phonecall"},
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_delay_disabled_stt"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "stt_provider_disabled"
        mock_lk_class.assert_not_called()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_rejects_unsupported_ai_stt_provider_before_dispatch(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_unsupported_stt",
            config={"stt_provider": "whisper", "stt_model": "whisper-1"},
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_delay_unsupported_stt"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "stt_provider_unsupported"
        mock_lk_class.assert_not_called()

    async def test_create_run_rejects_unknown_public_ai_scenario_id(
        self,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload("", ai_scenario_id="ai_missing_public_id"),
            headers=user_auth_headers,
        )

        assert resp.status_code == 404
        assert "AI scenario 'ai_missing_public_id' not found" in resp.json()["detail"]

    async def test_create_run_rejects_mismatched_public_ai_scenario_id(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_public_id",
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                "scenario_wrong_internal",
                ai_scenario_id="ai_delay_public_id",
            ),
            headers=user_auth_headers,
        )

        assert resp.status_code == 422
        assert "Run target mismatch between scenario_id and ai_scenario_id" in resp.json()["detail"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_ai_includes_context_in_room_metadata(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["scenario_kind"] == "ai"
        assert metadata["ai_dataset_input"]
        assert metadata["ai_expected_output"]
        assert metadata["ai_persona_id"] == "persona_unknown"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_ai_persists_snapshot_from_preferred_record(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)
        await _create_ai_scenario_binding(
            scenario_id=uploaded_scenario["id"],
            ai_scenario_id="ai_delay_snapshot_context",
        )

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            persona = await store_repo.get_ai_persona_row_for_tenant(
                db,
                "persona_runs_create_ai",
                "default",
            )
            assert persona is not None
            persona.display_name = "Ava Create"

            ai_scenario = await store_repo.get_ai_scenario_row_for_tenant(
                db,
                uploaded_scenario["id"],
                "default",
            )
            assert ai_scenario is not None
            ai_scenario.evaluation_objective = "Explain the delay policy and next steps."

            db.add(
                AIScenarioRecordRow(
                    record_id="airec_runs_create_inactive",
                    scenario_id=uploaded_scenario["id"],
                    tenant_id="default",
                    order_index=1,
                    input_text="Inactive low-order input",
                    expected_output="Inactive low-order expected output",
                    metadata_json={},
                    is_active=False,
                )
            )
            db.add(
                AIScenarioRecordRow(
                    record_id="airec_runs_create_active",
                    scenario_id=uploaded_scenario["id"],
                    tenant_id="default",
                    order_index=2,
                    input_text="Preferred active input",
                    expected_output="Preferred active expected output",
                    metadata_json={},
                    is_active=True,
                )
            )
            await db.commit()

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )

        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["scenario_kind"] == "ai"
        assert metadata["ai_dataset_input"] == "Preferred active input"
        assert metadata["ai_expected_output"] == "Preferred active expected output"
        assert metadata["ai_persona_id"] == "persona_runs_create_ai"
        assert metadata["ai_persona_name"] == "Ava Create"
        assert metadata["ai_scenario_objective"] == "Explain the delay policy and next steps."

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        events = run_resp.json()["events"]
        run_created_events = [e for e in events if e.get("type") == "run_created"]
        assert run_created_events, (
            f"No run_created event found; got types: {[e.get('type') for e in events]}"
        )
        run_created = run_created_events[0]
        assert "ai_context" in run_created["detail"], (
            f"ai_context missing from run_created detail: {run_created['detail']}"
        )
        ai_context = run_created["detail"]["ai_context"]
        assert ai_context["dataset_input"] == "Preferred active input"
        assert ai_context["expected_output"] == "Preferred active expected output"
        assert ai_context["persona_id"] == "persona_runs_create_ai"
        assert ai_context["persona_name"] == "Ava Create"
        assert ai_context["scenario_objective"] == "Explain the delay policy and next steps."

    async def test_create_run_rejects_ai_scenario_when_feature_disabled(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", False)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert resp.status_code == 503
        payload = resp.json()
        assert "ai scenarios are disabled" in payload["detail"].lower()
        assert payload["error_code"] == "ai_scenario_dispatch_unavailable"


    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_run_id_is_unique_across_calls(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()

        r1 = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        r2 = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert r1.json()["run_id"] != r2.json()["run_id"]

    async def test_create_run_requires_auth(self, client, uploaded_scenario):
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
        )
        assert resp.status_code == 401

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_from_schedule_requires_scheduler_service_token(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        resp = await client.post(
            "/runs/scheduled",
            json=make_run_scheduled_payload(uploaded_scenario["id"], schedule_id="sched-1"),
            headers=user_auth_headers,
        )
        assert resp.status_code == 401

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_from_schedule_sets_attribution_fields(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        scheduler_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        resp = await client.post(
            "/runs/scheduled",
            json=make_run_scheduled_payload(
                uploaded_scenario["id"],
                schedule_id="sched-1",
                triggered_by="scheduler-worker",
            ),
            headers=scheduler_auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["trigger_source"] == "scheduled"
        assert data["schedule_id"] == "sched-1"
        assert data["triggered_by"] == "scheduler-worker"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_create_run_from_schedule_includes_trace_context_and_scheduled_span_attrs(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        tracer = _FakeTracer()
        monkeypatch.setattr(runs_lifecycle_service, "_tracer", tracer)
        monkeypatch.setattr(
            runs_lifecycle_service,
            "current_w3c_trace_context",
            lambda: {
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                "tracestate": "vendor=test",
            },
        )

        resp = await client.post(
            "/runs/scheduled",
            json=make_run_scheduled_payload(
                uploaded_scenario["id"],
                schedule_id="sched-1",
                triggered_by="scheduler-worker",
            ),
            headers=scheduler_auth_headers,
        )

        assert resp.status_code == 202
        create_req = mock.room.create_room.await_args.args[0]
        metadata = json.loads(create_req.metadata)
        assert metadata["traceparent"] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        assert metadata["tracestate"] == "vendor=test"
        assert metadata["schedule_id"] == "sched-1"
        assert [name for name, _attrs in tracer.calls] == [
            SPAN_RUN_LIFECYCLE,
            SPAN_LIVEKIT_DISPATCH,
        ]
        lifecycle_attrs = tracer.calls[0][1] or {}
        assert lifecycle_attrs[ATTR_RUN_ID] == metadata["run_id"]
        assert lifecycle_attrs[ATTR_SCENARIO_ID] == uploaded_scenario["id"]
        assert lifecycle_attrs[ATTR_TRIGGER_SOURCE] == "scheduled"
        assert lifecycle_attrs[ATTR_SCHEDULE_ID] == "sched-1"
        assert lifecycle_attrs[ATTR_TRANSPORT_KIND] == metadata["transport"]
