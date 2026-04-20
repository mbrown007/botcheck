"""Tests for PATCH /runs/{id}/turn endpoint."""

from unittest.mock import patch

from factories import make_run_turn_payload
from runs_test_helpers import _create_run, _livekit_mock

class TestRecordTurn:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_record_turn_ok(
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
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="Hello.",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["state"] == "running"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_record_turn_redacts_structured_pii(
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
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="my ssn is 123-45-6789 and card 4111 1111 1111 1111",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        text = run_resp.json()["conversation"][0]["text"]
        assert "[SSN]" in text
        assert "[CARD]" in text

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_record_turn_redacts_spoken_digits(
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
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="call me at four one five five five five one two three four",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        text = run_resp.json()["conversation"][0]["text"]
        assert "[PHONE]" in text

    async def test_record_turn_unknown_run_returns_404(self, client, harness_auth_headers):
        resp = await client.post(
            "/runs/run_unknown/turns",
            json=make_run_turn_payload(text="hi"),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_record_turn_requires_service_auth(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_id="t1", speaker="harness", text="x"),
        )
        assert resp.status_code == 401

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_record_turn_rejects_wrong_service_token(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(turn_id="t1", speaker="harness", text="x"),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/complete  +  GET /runs/{run_id}/gate
# ---------------------------------------------------------------------------
