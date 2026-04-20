"""Tests for run reaper sweep reconciliation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from botcheck_api.config import settings

from factories import (
    make_run_create_payload,
    make_run_reaper_sweep_payload,
    make_run_turn_payload,
)
from runs_test_helpers import _livekit_mock, _set_run_created_at, _set_run_runtime_snapshot


class TestRunReaperSweep:
    async def test_reaper_requires_judge_service_token(self, client, harness_auth_headers):
        unauth = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(),
        )
        assert unauth.status_code == 401

        forbidden = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(),
            headers=harness_auth_headers,
        )
        assert forbidden.status_code == 403

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_closes_stale_pending_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "run_pending_stale_s", 60.0)

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        await _set_run_created_at(
            run_id,
            datetime.now(UTC) - timedelta(seconds=300),
        )

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "timeout_orphan"
        assert data["error_code"] == "harness_timeout"
        assert any(event["type"] == "run_reaped_pending_timeout" for event in data["events"])

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_keeps_recent_pending_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "run_pending_stale_s", 60.0)

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        await _set_run_created_at(
            run_id,
            datetime.now(UTC) - timedelta(seconds=20),
        )

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "pending"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_closes_overdue_run_when_room_missing(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        # Move to RUNNING.
        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
        )

        list_rooms_resp = MagicMock()
        list_rooms_resp.rooms = []
        mock.room.list_rooms = AsyncMock(return_value=list_rooms_resp)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["room_missing"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "timeout_orphan"
        assert data["error_code"] == "harness_timeout"
        assert any(event["type"] == "run_reaped_orphan" for event in data["events"])
        mock.room.delete_room.assert_not_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_is_idempotent_on_already_closed_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
        )

        list_rooms_resp = MagicMock()
        list_rooms_resp.rooms = []
        mock.room.list_rooms = AsyncMock(return_value=list_rooms_resp)

        first = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert first.status_code == 200
        assert first.json()["closed"] == 1

        second = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert second.status_code == 200
        assert second.json()["closed"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        reaper_events = [event for event in data["events"] if event["type"] == "run_reaped_orphan"]
        assert len(reaper_events) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_closes_overdue_run_when_room_active(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]
        room_name = run_resp.json()["livekit_room"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
        )

        room = MagicMock()
        room.name = room_name
        list_rooms_resp = MagicMock()
        list_rooms_resp.rooms = [room]
        mock.room.list_rooms = AsyncMock(return_value=list_rooms_resp)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["room_active"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "max_duration_exceeded"
        assert data["error_code"] == "reaper_force_closed"
        assert any(event["type"] == "run_reaped_max_duration" for event in data["events"])
        mock.room.delete_room.assert_awaited_once()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_closes_overdue_run_when_room_lookup_errors(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
        )

        mock.room.list_rooms = AsyncMock(side_effect=Exception("livekit timeout"))

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["livekit_errors"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "max_duration_exceeded"
        assert data["error_code"] == "reaper_force_closed"
        assert any(event["type"] == "run_reaped_max_duration" for event in data["events"])
        mock.room.delete_room.assert_not_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_skips_not_overdue_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=5),
            max_duration_s_at_start=120.0,
        )

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 0
        assert payload["overdue"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["state"] == "running"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_stale_heartbeat_not_overdue_does_not_force_close(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "run_heartbeat_enabled", True)
        monkeypatch.setattr(settings, "run_heartbeat_stale_s", 120.0)

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=20),
            max_duration_s_at_start=120.0,
            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=400),
            last_heartbeat_seq=9,
        )
        list_rooms_resp = MagicMock()
        room = MagicMock()
        room.name = f"botcheck-{run_id}"
        list_rooms_resp.rooms = [room]
        mock.room.list_rooms = AsyncMock(return_value=list_rooms_resp)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["overdue"] == 0
        assert payload["closed"] == 0
        assert payload["heartbeat_stale"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "running"
        assert not any(event["type"].startswith("run_reaped_") for event in data["events"])

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_stale_heartbeat_with_missing_room_force_closes_not_overdue(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "run_heartbeat_enabled", True)
        monkeypatch.setattr(settings, "run_heartbeat_stale_s", 120.0)

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=20),
            max_duration_s_at_start=120.0,
            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=400),
            last_heartbeat_seq=11,
        )
        # _livekit_mock default room.list_rooms => [] (missing room)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["overdue"] == 0
        assert payload["closed"] == 1
        assert payload["room_missing"] >= 1
        assert payload["heartbeat_stale"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "timeout_orphan"
        assert data["error_code"] == "harness_timeout"
        assert any(event["type"] == "run_reaped_orphan_stale" for event in data["events"])

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_dry_run_does_not_mutate(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
        )

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10, dry_run=True),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["dry_run"] is True
        assert payload["overdue"] >= 1
        assert payload["closed"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["state"] == "running"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_releases_sip_slot_on_forced_close(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
            transport="sip",
            sip_slot_held=True,
        )

        release_mock = AsyncMock(return_value=True)
        monkeypatch.setattr("botcheck_api.runs.runs_lifecycle.release_sip_slot", release_mock)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["sip_slots_released"] == 1
        release_mock.assert_awaited_once()

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert any(
            event["type"] == "sip_slot_released" and event.get("detail", {}).get("reason") == "run_reaper"
            for event in data["events"]
        )

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_closes_overdue_run_without_room_as_max_duration(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
            livekit_room="",
        )

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["room_missing"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["state"] == "error"
        assert data["end_reason"] == "max_duration_exceeded"
        assert data["error_code"] == "reaper_force_closed"
        assert any(event["type"] == "run_reaped_max_duration" for event in data["events"])

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_reaper_overdue_with_stale_heartbeat_includes_heartbeat_context(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock = _livekit_mock()
        mock_lk_class.return_value = mock
        monkeypatch.setattr(settings, "run_heartbeat_enabled", True)
        monkeypatch.setattr(settings, "run_heartbeat_stale_s", 120.0)

        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        await _set_run_runtime_snapshot(
            run_id,
            run_started_at=datetime.now(UTC) - timedelta(seconds=400),
            max_duration_s_at_start=120.0,
            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=350),
            last_heartbeat_seq=14,
        )

        list_rooms_resp = MagicMock()
        list_rooms_resp.rooms = []
        mock.room.list_rooms = AsyncMock(return_value=list_rooms_resp)

        sweep_resp = await client.post(
            "/runs/reaper/sweep",
            json=make_run_reaper_sweep_payload(limit=100, grace_s=10),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["closed"] == 1
        assert payload["heartbeat_stale"] >= 1

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        events = [event for event in run_detail.json()["events"] if event["type"] == "run_reaped_orphan"]
        assert len(events) == 1
        detail = events[0].get("detail", {})
        assert detail.get("heartbeat_stale") is True
        assert isinstance(detail.get("heartbeat_age_s"), (int, float))
