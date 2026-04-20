"""Tests for run failure endpoint and semantics."""

from unittest.mock import AsyncMock, patch

from botcheck_scenarios import ErrorCode

from botcheck_api.config import settings

from factories import make_run_complete_payload, make_run_fail_payload
from runs_test_helpers import SAMPLE_CONVERSATION, _create_run, _livekit_mock

class TestFailRun:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_run_sets_state(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """fail endpoint transitions run to failed and stores reason."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="Agent crashed on turn 2"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "failed"

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.json()["state"] == "failed"
        assert run_resp.json()["summary"] == "Agent crashed on turn 2"
        assert run_resp.json()["end_reason"] == "service_not_available"
        assert run_resp.json()["end_source"] == "harness"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_run_records_loop_guard_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(
                reason="Turn 't1' exceeded max_visits=1",
                end_reason="per_turn_loop_limit",
                loop_guard={
                    "guard": "per_turn_loop_limit",
                    "turn_id": "t1",
                    "visit": 2,
                    "max_visits": 1,
                    "effective_cap": 50,
                },
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["end_reason"] == "per_turn_loop_limit"

        loop_events = [
            event
            for event in data["events"]
            if event.get("type") == "loop_guard_triggered"
        ]
        assert len(loop_events) == 1
        detail = loop_events[0]["detail"]
        assert detail["guard"] == "per_turn_loop_limit"
        assert detail["turn_id"] == "t1"
        assert detail["visit"] == 2
        assert detail["max_visits"] == 1
        assert detail["effective_cap"] == 50

    async def test_fail_unknown_run_returns_404(self, client, harness_auth_headers):
        resp = await client.post(
            "/runs/run_unknown/fail",
            json=make_run_fail_payload(reason="oops"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_unknown_error_code_defaults_to_internal(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(
                reason="Version skew",
                error_code="future_error_code",
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["error_code"] == "internal"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_accepts_all_canonical_error_codes(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        for code in ErrorCode:
            run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
            resp = await client.post(
                f"/runs/{run_id}/fail",
                json=make_run_fail_payload(
                    reason=f"error={code.value}",
                    error_code=code.value,
                ),
                headers=harness_auth_headers,
            )
            assert resp.status_code == 200
            run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
            assert run_resp.status_code == 200
            assert run_resp.json()["error_code"] == code.value

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_run_releases_sip_slot(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        """fail_run must release the SIP slot when the run holds one."""
        mock_lk_class.return_value = _livekit_mock()
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
        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="Agent crashed"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        release_mock.assert_awaited_once()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_is_idempotent_when_already_failed(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """Second /fail on an already-failed run must return 200 without erroring."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="first"),
            headers=harness_auth_headers,
        )
        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="retry"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "failed"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_does_not_override_judging_state(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """If /complete already succeeded (state=judging), a late /fail must not override it.

        This covers the greedy-ACK scenario: complete 200 was lost in transit,
        harness retries with /fail, but the run is already being judged.
        """
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        # Simulate greedy-ACK fallback: /fail arrives after /complete already worked
        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="late retry"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "judging"

        # Run must still be in judging — not reverted to failed
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.json()["state"] == "judging"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_operator_stop_sets_error_and_releases_slot(
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
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.try_acquire_sip_slot",
            AsyncMock(return_value=True),
        )
        release_mock = AsyncMock()
        delete_room_mock = AsyncMock()
        monkeypatch.setattr("botcheck_api.runs.runs_events.release_sip_slot", release_mock)
        monkeypatch.setattr("botcheck_api.runs.runs_events.delete_livekit_room", delete_room_mock)

        run_id = await _create_run(client, sip_uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/stop",
            json={"reason": "Operator stop for stuck pending"},
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["applied"] is True
        assert payload["state"] == "error"
        release_mock.assert_awaited_once()
        delete_room_mock.assert_awaited_once()

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        run_payload = run_resp.json()
        assert run_payload["state"] == "error"
        assert run_payload["error_code"] == "operator_aborted"
        assert run_payload["end_reason"] == "explicit_termination_request"
        assert run_payload["end_source"] == "operator"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_operator_mark_failed_sets_failed_state(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.post(
            f"/runs/{run_id}/mark-failed",
            json={"reason": "Operator marked this run failed"},
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["applied"] is True
        assert payload["state"] == "failed"

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        run_payload = run_resp.json()
        assert run_payload["state"] == "failed"
        assert run_payload["error_code"] == "operator_aborted"
        assert run_payload["summary"] == "Operator marked this run failed"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_fail_run_deletes_livekit_room(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """fail_run must delete the LiveKit room so the PSTN SIP call is terminated."""
        lk = _livekit_mock()
        mock_lk_class.return_value = lk

        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="Agent crashed"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        # The delete_room call must have been issued once (for the run's room).
        lk.room.delete_room.assert_awaited_once()

        # The event must be recorded on the run.
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        room_events = [
            e for e in run_resp.json()["events"] if e.get("type") == "run_room_deleted_on_fail"
        ]
        assert len(room_events) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_operator_actions_reject_terminal_complete_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        judge_patch = await client.patch(
            f"/runs/{run_id}",
            json={"state": "complete", "gate_result": "passed"},
            headers=judge_auth_headers,
        )
        assert judge_patch.status_code == 200

        stop_resp = await client.post(f"/runs/{run_id}/stop", headers=user_auth_headers)
        assert stop_resp.status_code == 409
        mark_resp = await client.post(f"/runs/{run_id}/mark-failed", headers=user_auth_headers)
        assert mark_resp.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /runs/{run_id}
# ---------------------------------------------------------------------------
