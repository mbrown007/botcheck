"""Tests for run heartbeat callback endpoint."""

from datetime import UTC, datetime
from unittest.mock import patch

from factories import (
    make_run_fail_payload,
    make_run_heartbeat_payload,
    make_run_turn_payload,
)
from runs_test_helpers import (
    _create_run,
    _get_run_heartbeat_snapshot,
    _livekit_mock,
)


class TestRunHeartbeat:
    async def test_heartbeat_requires_harness_service_token(
        self,
        client,
        judge_auth_headers,
    ):
        payload = make_run_heartbeat_payload(
            sent_at=datetime.now(UTC).isoformat(),
            seq=1,
        )
        unauth = await client.post("/runs/run_missing/heartbeat", json=payload)
        assert unauth.status_code == 401

        forbidden = await client.post(
            "/runs/run_missing/heartbeat",
            json=payload,
            headers=judge_auth_headers,
        )
        assert forbidden.status_code == 403

    async def test_heartbeat_unknown_run_returns_404(self, client, harness_auth_headers):
        resp = await client.post(
            "/runs/run_missing/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=1,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_heartbeat_updates_running_snapshot(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        turn_resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        sent_at = datetime.now(UTC).isoformat()
        heartbeat_resp = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=sent_at,
                seq=1,
                turn_number=1,
                listener_state="awaiting_bot",
            ),
            headers=harness_auth_headers,
        )
        assert heartbeat_resp.status_code == 200
        data = heartbeat_resp.json()
        assert data["status"] == "updated"
        assert data["state"] == "running"
        assert data["last_heartbeat_seq"] == 1
        assert data["last_heartbeat_at"] is not None

        hb_at, hb_seq, hb_state = await _get_run_heartbeat_snapshot(run_id)
        assert hb_state == "running"
        assert hb_seq == 1
        assert hb_at is not None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_heartbeat_duplicate_or_stale_seq_does_not_regress(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )

        first = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=5,
            ),
            headers=harness_auth_headers,
        )
        assert first.status_code == 200
        assert first.json()["status"] == "updated"
        hb_at, hb_seq, _ = await _get_run_heartbeat_snapshot(run_id)
        assert hb_seq == 5
        assert hb_at is not None

        dup = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=5,
            ),
            headers=harness_auth_headers,
        )
        assert dup.status_code == 200
        assert dup.json()["status"] == "duplicate_or_stale"

        stale = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=4,
            ),
            headers=harness_auth_headers,
        )
        assert stale.status_code == 200
        assert stale.json()["status"] == "duplicate_or_stale"

        hb_at_after, hb_seq_after, _ = await _get_run_heartbeat_snapshot(run_id)
        assert hb_seq_after == 5
        assert hb_at_after == hb_at

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_heartbeat_ignored_for_terminal_run_state(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )
        await client.post(
            f"/runs/{run_id}/fail",
            json=make_run_fail_payload(reason="done"),
            headers=harness_auth_headers,
        )

        resp = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=3,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored_terminal"
        assert data["state"] == "failed"
        assert data["last_heartbeat_at"] is None
        assert data["last_heartbeat_seq"] is None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_heartbeat_transitions_pending_run_to_running(
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
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at=datetime.now(UTC).isoformat(),
                seq=1,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "updated"
        assert payload["state"] == "running"
        assert payload["last_heartbeat_seq"] == 1
        assert payload["last_heartbeat_at"] is not None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_heartbeat_requires_utc_sent_at(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_number=1, speaker="harness", text="hello"),
            headers=harness_auth_headers,
        )

        naive = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at="2026-03-04T12:00:00",
                seq=1,
            ),
            headers=harness_auth_headers,
        )
        assert naive.status_code == 422

        non_utc = await client.post(
            f"/runs/{run_id}/heartbeat",
            json=make_run_heartbeat_payload(
                sent_at="2026-03-04T12:00:00+01:00",
                seq=1,
            ),
            headers=harness_auth_headers,
        )
        assert non_utc.status_code == 422
