"""Tests for /schedules/ routes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from botcheck_api import database
from botcheck_api.capacity import build_sip_slot_key
from botcheck_api.config import settings
from botcheck_api.exceptions import ApiProblem, HARNESS_UNAVAILABLE
from botcheck_api.main import app
from botcheck_api.models import PackRunItemRow, PackRunRow, RunRow, ScenarioKind, ScheduleRow
from sqlalchemy import select

from factories import (
    make_pack_upsert_payload,
    make_run_complete_payload,
    make_run_fail_payload,
    make_run_patch_payload,
    make_schedule_create_payload,
    make_schedule_dispatch_due_payload,
    make_schedule_patch_payload,
    make_schedule_preview_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)
from scenario_test_helpers import _set_scenario_kind


def _parse_iso(value: str) -> datetime:
    candidate = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _livekit_mock():
    m = MagicMock()
    m.room.create_room = AsyncMock(return_value=MagicMock())
    m.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    m.sip.create_sip_participant = AsyncMock(return_value=MagicMock())
    m.aclose = AsyncMock()
    return m


def _persona_payload(name: str = "Schedule Persona") -> dict[str, object]:
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
) -> dict[str, object]:
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


def _http_destination_payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Schedule HTTP Transport",
        "protocol": "http",
        "endpoint": "https://bot.internal/chat",
        "headers": {"Authorization": "Bearer schedule-token"},
        "direct_http_config": {
            "method": "POST",
            "request_content_type": "json",
            "request_text_field": "message",
            "request_history_field": "history",
            "request_session_id_field": "session_id",
            "response_text_field": "response.text",
            "timeout_s": 20,
            "max_retries": 1,
        },
        "is_active": True,
    }
    payload.update(overrides)
    return payload


async def _set_schedule_next_run(schedule_id: str, next_run_at: datetime) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(ScheduleRow, schedule_id)
        assert row is not None
        row.next_run_at = next_run_at
        await db.commit()


class TestSchedules:
    async def test_schedule_preview_requires_auth(self, client):
        resp = await client.post(
            "/schedules/preview",
            json=make_schedule_preview_payload("*/15 * * * *"),
        )
        assert resp.status_code == 401

    async def test_schedule_preview_returns_occurrences(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/preview",
            json=make_schedule_preview_payload("*/15 * * * *", count=3),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cron_expr"] == "*/15 * * * *"
        assert body["timezone"] == settings.instance_timezone
        assert len(body["occurrences"]) == 3
        occurrences = [_parse_iso(v) for v in body["occurrences"]]
        assert occurrences[0] < occurrences[1] < occurrences[2]

    async def test_schedule_preview_uses_explicit_timezone(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/preview",
            json=make_schedule_preview_payload(
                "0 9 * * *",
                timezone="Europe/London",
                count=2,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["timezone"] == "Europe/London"
        assert len(body["occurrences"]) == 2
        occurrences = [_parse_iso(v) for v in body["occurrences"]]
        assert occurrences[0] < occurrences[1]

    async def test_schedule_preview_accepts_count_one_boundary(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/preview",
            json=make_schedule_preview_payload("*/15 * * * *", count=1),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["occurrences"]) == 1

    async def test_schedule_preview_rejects_invalid_cron(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/preview",
            json=make_schedule_preview_payload("not-a-cron"),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_schedule_requires_auth(self, client, uploaded_scenario):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"], cron_expr="*/15 * * * *"
            ),
        )
        assert resp.status_code == 401

    async def test_create_schedule_defaults_timezone_to_instance(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"], cron_expr="*/15 * * * *"
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["timezone"] == settings.instance_timezone
        assert data["next_run_at"] is not None
        assert data["active"] is True

    async def test_create_schedule_persists_retry_on_failure(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                retry_on_failure=True,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["retry_on_failure"] is True
        assert data["consecutive_failures"] == 0
        assert data["last_run_outcome"] is None

    async def test_create_schedule_persists_trimmed_name(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                name="  Morning smoke pack  ",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Morning smoke pack"

    async def test_create_schedule_unknown_scenario_returns_404(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                "missing-scenario",
                cron_expr="*/15 * * * *",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 404

    async def test_create_schedule_accepts_public_ai_scenario_id(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
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
                scenario_id=uploaded_scenario["id"],
                persona_id=persona_id,
                ai_scenario_id="ai_delay_schedule_public",
            ),
            headers=user_auth_headers,
        )
        assert ai_resp.status_code == 201

        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="*/15 * * * *",
                ai_scenario_id="ai_delay_schedule_public",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        payload = resp.json()
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["ai_scenario_id"] == "ai_delay_schedule_public"
        assert payload["config_overrides"] is None

    async def test_create_pack_target_schedule_returns_201(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Nightly Pack Target",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        payload = resp.json()
        assert payload["target_type"] == "pack"
        assert payload["pack_id"] == pack_id
        assert payload["scenario_id"] is None

    async def test_create_schedule_rejects_mismatched_ai_scenario_target(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        second_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(
                make_scenario_yaml(
                    scenario_id="test-second-schedule-scenario",
                    name="Second Schedule Scenario",
                )
            ),
            headers=user_auth_headers,
        )
        assert second_resp.status_code == 201
        second_scenario = second_resp.json()

        persona_resp = await client.post(
            "/scenarios/personas",
            json=_persona_payload(name="Mismatch Persona"),
            headers=user_auth_headers,
        )
        assert persona_resp.status_code == 201
        persona_id = persona_resp.json()["persona_id"]

        ai_resp = await client.post(
            "/scenarios/ai-scenarios",
            json=_ai_scenario_payload(
                scenario_id=uploaded_scenario["id"],
                persona_id=persona_id,
                ai_scenario_id="ai_delay_schedule_mismatch",
            ),
            headers=user_auth_headers,
        )
        assert ai_resp.status_code == 201

        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                second_scenario["id"],
                cron_expr="*/15 * * * *",
                ai_scenario_id="ai_delay_schedule_mismatch",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "scenario_id does not match ai_scenario_id" in resp.json()["detail"]

    async def test_create_schedule_rejects_missing_destination_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                config_overrides={"destination_id": "dest_missing"},
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "destination_id override not found" in resp.json()["detail"]
        assert resp.json()["error_code"] == "destination_not_found"

    async def test_create_pack_schedule_rejects_missing_destination_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Pack Destination Validation",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
                config_overrides={"destination_id": "dest_missing"},
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "destination_id override not found" in resp.json()["detail"]
        assert resp.json()["error_code"] == "destination_not_found"

    async def test_create_pack_target_schedule_requires_pack_id(
        self,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="*/15 * * * *",
                target_type="pack",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "pack_id" in resp.json()["detail"].lower()

    async def test_create_scenario_target_schedule_rejects_pack_id(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                target_type="scenario",
                pack_id="pack_any",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "must not include pack_id" in resp.json()["detail"].lower()

    async def test_create_schedule_active_false_has_no_next_run(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                active=False,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["next_run_at"] is None

    async def test_create_schedule_rejects_unknown_override_key(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                config_overrides={"unexpected": "value"},
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_schedule_rejects_invalid_retention_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                config_overrides={"retention_profile": "forever"},
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_schedule_rejects_invalid_cron(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"], cron_expr="not-a-cron"
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_schedule_rejects_invalid_timezone(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                cron_expr="*/15 * * * *",
                timezone="Mars/Olympus",
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_list_patch_delete_schedule(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "0 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]

        list_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(active=False),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["active"] is False
        assert patch_resp.json()["next_run_at"] is None

        delete_resp = await client.delete(
            f"/schedules/{schedule_id}",
            headers=user_auth_headers,
        )
        assert delete_resp.status_code == 204
        list_resp2 = await client.get("/schedules/", headers=user_auth_headers)
        assert list_resp2.status_code == 200
        assert list_resp2.json() == []

    async def test_patch_schedule_rejects_unknown_scenario(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "0 * * * *"),
            headers=user_auth_headers,
        )
        schedule_id = create_resp.json()["schedule_id"]
        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(scenario_id="missing-scenario"),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 404

    async def test_patch_schedule_updates_retry_on_failure(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "0 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(retry_on_failure=True),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["retry_on_failure"] is True

    async def test_patch_schedule_can_set_and_clear_name(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "0 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]

        rename_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(name="Daily production smoke"),
            headers=user_auth_headers,
        )
        assert rename_resp.status_code == 200
        assert rename_resp.json()["name"] == "Daily production smoke"

        clear_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(name="   "),
            headers=user_auth_headers,
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["name"] is None

    async def test_patch_schedule_can_switch_from_scenario_target_to_pack_target(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Switch Target Pack",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "0 * * * *"),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                target_type="pack",
                scenario_id=None,
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        payload = patch_resp.json()
        assert payload["target_type"] == "pack"
        assert payload["pack_id"] == pack_id
        assert payload["scenario_id"] is None

    async def test_patch_switch_to_pack_preserves_existing_destination_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)

        destination_resp = await client.post(
            "/destinations/",
            json={
                "name": "Switch Target Preserve Destination",
                "protocol": "mock",
                "endpoint": "mock://switch-preserve",
            },
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Switch Target Preserve Overrides Pack",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                "0 * * * *",
                config_overrides={
                    "destination_id": destination_id,
                    "retention_profile": "standard",
                },
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                target_type="pack",
                scenario_id=None,
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        payload = patch_resp.json()
        assert payload["target_type"] == "pack"
        assert payload["pack_id"] == pack_id
        assert payload["scenario_id"] is None
        assert payload["config_overrides"] == {
            "destination_id": destination_id,
            "transport_profile_id": destination_id,
            "retention_profile": "standard",
        }

    async def test_patch_schedule_can_switch_from_pack_target_to_scenario_target(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Switch Back Pack",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="0 * * * *",
                target_type="pack",
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                target_type="scenario",
                scenario_id=uploaded_scenario["id"],
                pack_id=None,
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        payload = patch_resp.json()
        assert payload["target_type"] == "scenario"
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["pack_id"] is None

    async def test_patch_switch_to_scenario_preserves_existing_destination_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)

        destination_resp = await client.post(
            "/destinations/",
            json={
                "name": "Switch Back Preserve Destination",
                "protocol": "mock",
                "endpoint": "mock://switch-back-preserve",
            },
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Switch Back Preserve Overrides Pack",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                cron_expr="0 * * * *",
                target_type="pack",
                pack_id=pack_id,
                config_overrides={
                    "destination_id": destination_id,
                    "retention_profile": "standard",
                },
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                target_type="scenario",
                scenario_id=uploaded_scenario["id"],
                pack_id=None,
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        payload = patch_resp.json()
        assert payload["target_type"] == "scenario"
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["pack_id"] is None
        assert payload["config_overrides"] == {
            "destination_id": destination_id,
            "transport_profile_id": destination_id,
            "retention_profile": "standard",
        }

    async def test_patch_config_overrides_does_not_recompute_next_run(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        next_run_before = create_resp.json()["next_run_at"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                config_overrides={"triggered_by": "scheduler-eu"}
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 200
        assert _parse_iso(patch_resp.json()["next_run_at"]) == _parse_iso(next_run_before)

    async def test_patch_schedule_rejects_missing_destination_override(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]

        patch_resp = await client.patch(
            f"/schedules/{schedule_id}",
            json=make_schedule_patch_payload(
                config_overrides={"destination_id": "dest_missing"},
            ),
            headers=user_auth_headers,
        )
        assert patch_resp.status_code == 422
        assert "destination_id override not found" in patch_resp.json()["detail"]
        assert patch_resp.json()["error_code"] == "destination_not_found"

    async def test_delete_schedule_not_found_returns_404(self, client, user_auth_headers):
        resp = await client.delete("/schedules/sched_missing", headers=user_auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "schedule_not_found"

    async def test_dispatch_due_requires_scheduler_token(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=user_auth_headers,
        )
        assert resp.status_code == 401

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_creates_scheduled_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        body = dispatch_resp.json()
        assert body["checked"] == 1
        assert body["dispatched"] == 1
        assert body["throttled"] == 0
        assert body["failed"] == 0

        runs_resp = await client.get("/runs/", headers=user_auth_headers)
        assert runs_resp.status_code == 200
        scheduled_runs = [r for r in runs_resp.json() if r["trigger_source"] == "scheduled"]
        assert len(scheduled_runs) == 1
        assert scheduled_runs[0]["schedule_id"] == schedule_id

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedule = schedules_resp.json()[0]
        assert schedule["last_status"] == "dispatched"
        assert schedule["last_run_at"] is not None
        assert schedule["next_run_at"] is not None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_failed_scheduled_run_retries_once_and_tracks_failure_streak(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                "*/15 * * * *",
                retry_on_failure=True,
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(schedule_id, datetime.now(UTC) - timedelta(minutes=1))

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200

        runs_resp = await client.get("/runs/", headers=user_auth_headers)
        first_run = next(r for r in runs_resp.json() if r["schedule_id"] == schedule_id)
        fail_resp = await client.post(
            f"/runs/{first_run['run_id']}/fail",
            json=make_run_fail_payload(reason="scheduled failure", error_code="harness_timeout"),
            headers=harness_auth_headers,
        )
        assert fail_resp.status_code == 200

        runs_resp_after = await client.get("/runs/", headers=user_auth_headers)
        scheduled_runs = [r for r in runs_resp_after.json() if r["schedule_id"] == schedule_id]
        assert len(scheduled_runs) == 2
        retry_run = next(r for r in scheduled_runs if r["run_id"] != first_run["run_id"])
        assert retry_run["trigger_source"] == "scheduled"
        assert retry_run["state"] == "pending"

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        schedule = next(row for row in schedules_resp.json() if row["schedule_id"] == schedule_id)
        assert schedule["last_run_outcome"] == "failed"
        assert schedule["consecutive_failures"] == 1
        assert schedule["retry_on_failure"] is True

        second_fail_resp = await client.post(
            f"/runs/{retry_run['run_id']}/fail",
            json=make_run_fail_payload(reason="retry failure", error_code="harness_timeout"),
            headers=harness_auth_headers,
        )
        assert second_fail_resp.status_code == 200

        final_runs_resp = await client.get("/runs/", headers=user_auth_headers)
        final_scheduled_runs = [r for r in final_runs_resp.json() if r["schedule_id"] == schedule_id]
        assert len(final_scheduled_runs) == 2

        final_schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        final_schedule = next(
            row for row in final_schedules_resp.json() if row["schedule_id"] == schedule_id
        )
        assert final_schedule["last_run_outcome"] == "failed"
        assert final_schedule["consecutive_failures"] == 2

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_successful_retry_resets_schedule_failure_streak(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                "*/15 * * * *",
                retry_on_failure=True,
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(schedule_id, datetime.now(UTC) - timedelta(minutes=1))

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200

        runs_resp = await client.get("/runs/", headers=user_auth_headers)
        first_run = next(r for r in runs_resp.json() if r["schedule_id"] == schedule_id)
        fail_resp = await client.post(
            f"/runs/{first_run['run_id']}/fail",
            json=make_run_fail_payload(reason="scheduled failure", error_code="harness_timeout"),
            headers=harness_auth_headers,
        )
        assert fail_resp.status_code == 200

        runs_after_fail = await client.get("/runs/", headers=user_auth_headers)
        retry_run = next(
            r
            for r in runs_after_fail.json()
            if r["schedule_id"] == schedule_id and r["run_id"] != first_run["run_id"]
        )
        complete_resp = await client.post(
            f"/runs/{retry_run['run_id']}/complete",
            json=make_run_complete_payload(
                conversation=[
                    {
                        "turn_id": "t1",
                        "turn_number": 1,
                        "speaker": "harness",
                        "text": "hello",
                    }
                ]
            ),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        patch_resp = await client.patch(
            f"/runs/{retry_run['run_id']}",
            json=make_run_patch_payload(gate_result="passed", summary="ok"),
            headers=judge_auth_headers,
        )
        assert patch_resp.status_code == 200

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        schedule = next(row for row in schedules_resp.json() if row["schedule_id"] == schedule_id)
        assert schedule["last_run_outcome"] == "success"
        assert schedule["consecutive_failures"] == 0

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_creates_scheduled_run_for_ai_scenario_when_enabled(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        body = dispatch_resp.json()
        assert body["checked"] == 1
        assert body["dispatched"] == 1
        assert body["throttled"] == 0
        assert body["failed"] == 0

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedule = schedules_resp.json()[0]
        assert schedule["last_status"] == "dispatched"
        assert schedule["last_run_at"] is not None
        assert schedule["next_run_at"] is not None

        runs_resp = await client.get("/runs/", headers=user_auth_headers)
        assert runs_resp.status_code == 200
        scheduled_runs = [r for r in runs_resp.json() if r["trigger_source"] == "scheduled"]
        assert len(scheduled_runs) == 1
        assert scheduled_runs[0]["scenario_id"] == uploaded_scenario["id"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_creates_scheduled_run_for_public_ai_scenario_id(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

        persona_resp = await client.post(
            "/scenarios/personas",
            json=_persona_payload(name="Dispatch Persona"),
            headers=user_auth_headers,
        )
        assert persona_resp.status_code == 201
        persona_id = persona_resp.json()["persona_id"]

        ai_resp = await client.post(
            "/scenarios/ai-scenarios",
            json=_ai_scenario_payload(
                scenario_id=uploaded_scenario["id"],
                persona_id=persona_id,
                ai_scenario_id="ai_delay_schedule_dispatch",
            ),
            headers=user_auth_headers,
        )
        assert ai_resp.status_code == 201

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                "*/15 * * * *",
                ai_scenario_id="ai_delay_schedule_dispatch",
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        body = dispatch_resp.json()
        assert body["checked"] == 1
        assert body["dispatched"] == 1
        assert body["failed"] == 0

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedule = schedules_resp.json()[0]
        assert schedule["scenario_id"] == uploaded_scenario["id"]
        assert schedule["ai_scenario_id"] == "ai_delay_schedule_dispatch"
        assert schedule["last_status"] == "dispatched"

    async def test_dispatch_due_pack_target_enqueues_pack_dispatch(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Scheduled Pack Dispatch",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                "*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["checked"] == 1
        assert payload["dispatched"] == 1
        assert payload["throttled"] == 0
        assert payload["failed"] == 0

        enqueue = app.state.arq_pool.enqueue_job
        assert enqueue.await_count >= 1
        args, kwargs = enqueue.call_args
        assert args[0] == "dispatch_pack_run"
        assert kwargs["_queue_name"] == "arq:scheduler"
        pack_run_id = kwargs["payload"]["pack_run_id"]
        assert pack_run_id

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            pack_run = await db.get(PackRunRow, pack_run_id)
            assert pack_run is not None
            assert pack_run.trigger_source == "scheduled"
            assert pack_run.schedule_id == schedule_id
            assert pack_run.pack_id == pack_id
            item_rows = (
                await db.execute(
                    select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
                )
            ).scalars().all()
            assert len(item_rows) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_pack_target_child_runs_keep_scheduled_trigger_source(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_packs_enabled", True)

        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Scheduled Pack Child Trigger Source",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                "*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_due_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_due_resp.status_code == 200
        assert dispatch_due_resp.json()["dispatched"] == 1

        enqueue = app.state.arq_pool.enqueue_job
        assert enqueue.await_count >= 1
        _, kwargs = enqueue.call_args
        pack_run_id = kwargs["payload"]["pack_run_id"]
        assert pack_run_id

        internal_dispatch_resp = await client.post(
            f"/packs/internal/{pack_run_id}/dispatch",
            headers=scheduler_auth_headers,
        )
        assert internal_dispatch_resp.status_code == 200
        assert internal_dispatch_resp.json()["applied"] is True

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            runs = (
                await db.execute(
                    select(RunRow)
                    .where(RunRow.pack_run_id == pack_run_id)
                    .order_by(RunRow.created_at.asc())
                )
            ).scalars().all()
            assert len(runs) == 1
            assert runs[0].trigger_source == "scheduled"
            assert runs[0].schedule_id == schedule_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_pack_target_destination_override_propagates_to_children(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)

        destination_resp = await client.post(
            "/destinations/",
            json={
                "name": "Scheduled Pack Destination",
                "protocol": "mock",
                "endpoint": "mock://scheduled-pack",
                "is_active": True,
            },
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Scheduled Pack Destination",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                "*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
                config_overrides={"destination_id": destination_id},
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_due_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_due_resp.status_code == 200
        assert dispatch_due_resp.json()["dispatched"] == 1

        enqueue = app.state.arq_pool.enqueue_job
        assert enqueue.await_count >= 1
        _, kwargs = enqueue.call_args
        pack_run_id = kwargs["payload"]["pack_run_id"]
        assert pack_run_id

        internal_dispatch_resp = await client.post(
            f"/packs/internal/{pack_run_id}/dispatch",
            headers=scheduler_auth_headers,
        )
        assert internal_dispatch_resp.status_code == 200
        assert internal_dispatch_resp.json()["applied"] is True

        pack_runs_resp = await client.get("/pack-runs/", headers=user_auth_headers)
        assert pack_runs_resp.status_code == 200
        listed = {entry["pack_run_id"]: entry for entry in pack_runs_resp.json()}
        assert listed[pack_run_id]["destination_id"] == destination_id
        assert listed[pack_run_id]["transport_profile_id"] == destination_id

        pack_run_detail_resp = await client.get(
            f"/pack-runs/{pack_run_id}",
            headers=user_auth_headers,
        )
        assert pack_run_detail_resp.status_code == 200
        assert pack_run_detail_resp.json()["destination_id"] == destination_id
        assert pack_run_detail_resp.json()["transport_profile_id"] == destination_id

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            pack_run = await db.get(PackRunRow, pack_run_id)
            assert pack_run is not None
            assert pack_run.destination_id == destination_id
            assert pack_run.transport_profile_id == destination_id
            runs = (
                await db.execute(
                    select(RunRow)
                    .where(RunRow.pack_run_id == pack_run_id)
                    .order_by(RunRow.created_at.asc())
                )
            ).scalars().all()
            assert len(runs) == 1
            assert runs[0].destination_id_at_start == destination_id
            assert runs[0].transport_profile_id_at_start == destination_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_with_retention_override_uses_default_endpoint(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
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
            "botcheck_api.runs.service_lifecycle.acquire_with_backoff",
            AsyncMock(return_value=True),
        )

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                sip_uploaded_scenario["id"],
                "*/15 * * * *",
                config_overrides={"retention_profile": "standard"},
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["dispatched"] == 1
        assert payload["failed"] == 0

        mock.sip.create_sip_participant.assert_awaited_once()
        req = mock.sip.create_sip_participant.call_args.args[0]
        # Uses scenario default SIP endpoint target when bot_endpoint override is absent.
        assert req.sip_call_to == "bot"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_with_destination_override_uses_destination_capacity(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
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
        acquire = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.acquire_with_backoff",
            acquire,
        )

        destination_resp = await client.post(
            "/destinations/",
            json={
                "name": "Schedule Carrier",
                "protocol": "sip",
                "endpoint": "sip:bot@test.example.com",
                "is_active": True,
                "provisioned_channels": 7,
                "reserved_channels": 2,
                "capacity_scope": "schedule-carrier",
            },
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                sip_uploaded_scenario["id"],
                "*/15 * * * *",
                config_overrides={"destination_id": destination_id},
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["dispatched"] == 1
        assert payload["failed"] == 0

        expected_key = build_sip_slot_key(
            tenant_id=settings.tenant_id,
            capacity_scope="schedule-carrier",
        )
        acquire.assert_awaited_once()
        kwargs = acquire.await_args.kwargs
        assert kwargs["max_slots"] == 5
        assert kwargs["slot_key"] == expected_key

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            run_row = (
                await db.execute(
                    select(RunRow).where(RunRow.schedule_id == schedule_id)
                )
            ).scalars().one()
            assert run_row.destination_id_at_start == destination_id
            assert run_row.transport_profile_id_at_start == destination_id
            assert run_row.dial_target_at_start == "sip:bot@test.example.com"
            assert run_row.capacity_scope_at_start == "schedule-carrier"
            assert run_row.capacity_limit_at_start == 5

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_with_transport_profile_and_dial_target_uses_new_fields(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
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

        destination_resp = await client.post(
            "/destinations/",
            json={
                "name": "Schedule Transport Profile",
                "protocol": "sip",
                "endpoint": "sip:default@test.example.com",
                "is_active": True,
                "provisioned_channels": 4,
                "reserved_channels": 0,
                "capacity_scope": "schedule-transport",
            },
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                sip_uploaded_scenario["id"],
                "*/15 * * * *",
                config_overrides={
                    "transport_profile_id": destination_id,
                    "dial_target": "sip:override@test.example.com",
                },
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        payload = create_resp.json()
        assert payload["config_overrides"] == {
            "destination_id": destination_id,
            "transport_profile_id": destination_id,
            "bot_endpoint": "sip:override@test.example.com",
            "dial_target": "sip:override@test.example.com",
        }
        schedule_id = payload["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        assert dispatch_resp.json()["dispatched"] == 1

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            run_row = (
                await db.execute(
                    select(RunRow).where(RunRow.schedule_id == schedule_id)
                )
            ).scalars().one()
            assert run_row.destination_id_at_start == destination_id
            assert run_row.transport_profile_id_at_start == destination_id
            assert run_row.dial_target_at_start == "sip:override@test.example.com"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_with_http_destination_override_creates_http_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)

        destination_resp = await client.post(
            "/destinations/",
            json=_http_destination_payload(),
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                "*/15 * * * *",
                config_overrides={"destination_id": destination_id},
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        assert dispatch_resp.json()["dispatched"] == 1

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            run_row = (
                await db.execute(
                    select(RunRow).where(RunRow.schedule_id == schedule_id)
                )
            ).scalars().one()
            assert run_row.transport == "http"
            assert run_row.destination_id_at_start == destination_id
            assert run_row.transport_profile_id_at_start == destination_id
            assert run_row.dial_target_at_start == "https://bot.internal/chat"
            assert run_row.direct_http_headers_at_start == {"Authorization": "Bearer schedule-token"}
            assert run_row.direct_http_config_at_start is not None
            assert run_row.direct_http_config_at_start["request_text_field"] == "message"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_pack_target_http_destination_override_propagates_to_children(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_packs_enabled", True)
        monkeypatch.setattr(settings, "feature_destinations_enabled", True)

        destination_resp = await client.post(
            "/destinations/",
            json=_http_destination_payload(headers={"Authorization": "Bearer schedule-pack-token"}),
            headers=user_auth_headers,
        )
        assert destination_resp.status_code == 201
        destination_id = destination_resp.json()["destination_id"]

        create_pack_resp = await client.post(
            "/packs/",
            json=make_pack_upsert_payload(
                name="Scheduled Pack HTTP Destination",
                scenario_ids=[uploaded_scenario["id"]],
            ),
            headers=user_auth_headers,
        )
        assert create_pack_resp.status_code == 201
        pack_id = create_pack_resp.json()["pack_id"]

        create_schedule_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                None,
                "*/15 * * * *",
                target_type="pack",
                pack_id=pack_id,
                config_overrides={"destination_id": destination_id},
            ),
            headers=user_auth_headers,
        )
        assert create_schedule_resp.status_code == 201
        schedule_id = create_schedule_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_due_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_due_resp.status_code == 200
        assert dispatch_due_resp.json()["dispatched"] == 1

        enqueue = app.state.arq_pool.enqueue_job
        assert enqueue.await_count >= 1
        _, kwargs = enqueue.call_args
        pack_run_id = kwargs["payload"]["pack_run_id"]
        assert pack_run_id

        internal_dispatch_resp = await client.post(
            f"/packs/internal/{pack_run_id}/dispatch",
            headers=scheduler_auth_headers,
        )
        assert internal_dispatch_resp.status_code == 200
        assert internal_dispatch_resp.json()["applied"] is True

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            pack_run = await db.get(PackRunRow, pack_run_id)
            assert pack_run is not None
            assert pack_run.destination_id == destination_id
            assert pack_run.transport_profile_id == destination_id
            runs = (
                await db.execute(
                    select(RunRow)
                    .where(RunRow.pack_run_id == pack_run_id)
                    .order_by(RunRow.created_at.asc())
                )
            ).scalars().all()
            assert len(runs) == 1
            assert runs[0].transport == "http"
            assert runs[0].destination_id_at_start == destination_id
            assert runs[0].transport_profile_id_at_start == destination_id
            assert runs[0].dial_target_at_start == "https://bot.internal/chat"
            assert runs[0].direct_http_headers_at_start == {"Authorization": "Bearer schedule-pack-token"}

    async def test_dispatch_due_marks_throttled_with_run_once_misfire_policy(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(
                uploaded_scenario["id"],
                "*/15 * * * *",
                misfire_policy="run_once",
            ),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        async def _throttle(**kwargs):
            from fastapi import HTTPException

            raise HTTPException(status_code=429, detail="throttled")

        monkeypatch.setattr("botcheck_api.runs.schedules._create_run_internal", _throttle)

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["checked"] == 1
        assert payload["dispatched"] == 0
        assert payload["throttled"] == 1

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        schedule = schedules_resp.json()[0]
        assert schedule["last_status"] == "throttled"
        assert schedule["next_run_at"] is not None

    async def test_dispatch_due_marks_api_problem_503_as_failed(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        async def _harness_unavailable(**kwargs):
            raise ApiProblem(
                status=503,
                error_code=HARNESS_UNAVAILABLE,
                detail="Harness agent unavailable",
            )

        monkeypatch.setattr("botcheck_api.runs.schedules._create_run_internal", _harness_unavailable)

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["checked"] == 1
        assert payload["dispatched"] == 0
        assert payload["throttled"] == 0
        assert payload["failed"] == 1

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedule = schedules_resp.json()[0]
        assert schedule["last_status"] == "error_harness_unavailable"
        assert schedule["last_run_at"] is not None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_dispatch_due_marks_ai_scenario_dispatch_unavailable_as_failed(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", False)
        await _set_scenario_kind(uploaded_scenario["id"], ScenarioKind.AI.value)

        create_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201
        schedule_id = create_resp.json()["schedule_id"]
        await _set_schedule_next_run(
            schedule_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["checked"] == 1
        assert payload["dispatched"] == 0
        assert payload["throttled"] == 0
        assert payload["failed"] == 1

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedule = schedules_resp.json()[0]
        assert schedule["last_status"] == "error_ai_scenario_dispatch_unavailable"
        assert schedule["last_run_at"] is not None

    async def test_dispatch_due_partial_failure_does_not_rollback_other_schedule_updates(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        scheduler_auth_headers,
        monkeypatch,
    ):
        first_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        second_resp = await client.post(
            "/schedules/",
            json=make_schedule_create_payload(uploaded_scenario["id"], "*/15 * * * *"),
            headers=user_auth_headers,
        )
        assert first_resp.status_code == 201
        assert second_resp.status_code == 201
        first_id = first_resp.json()["schedule_id"]
        second_id = second_resp.json()["schedule_id"]

        await _set_schedule_next_run(
            first_id,
            datetime.now(UTC) - timedelta(minutes=2),
        )
        await _set_schedule_next_run(
            second_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        async def _create_run_side_effect(*args, **kwargs):
            from fastapi import HTTPException

            call_count = getattr(_create_run_side_effect, "_calls", 0) + 1
            setattr(_create_run_side_effect, "_calls", call_count)
            if call_count == 1:
                raise HTTPException(status_code=429, detail="throttled")
            return {"ok": True}

        monkeypatch.setattr(
            "botcheck_api.runs.schedules._create_run_internal",
            _create_run_side_effect,
        )

        dispatch_resp = await client.post(
            "/schedules/dispatch-due",
            json=make_schedule_dispatch_due_payload(limit=10),
            headers=scheduler_auth_headers,
        )
        assert dispatch_resp.status_code == 200
        payload = dispatch_resp.json()
        assert payload["checked"] == 2
        assert payload["dispatched"] == 1
        assert payload["throttled"] == 1

        schedules_resp = await client.get("/schedules/", headers=user_auth_headers)
        assert schedules_resp.status_code == 200
        schedules_by_id = {row["schedule_id"]: row for row in schedules_resp.json()}
        assert schedules_by_id[first_id]["last_status"] == "throttled"
        assert schedules_by_id[second_id]["last_status"] == "dispatched"
        assert schedules_by_id[first_id]["last_run_at"] is not None
        assert schedules_by_id[second_id]["last_run_at"] is not None
