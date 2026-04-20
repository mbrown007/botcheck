"""Tests for GET /runs/ endpoints."""

from unittest.mock import patch

from factories import make_run_turn_payload
from runs_test_helpers import _create_run, _livekit_mock

class TestGetRun:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_get_existing_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id
        assert resp.json()["state"] == "pending"
        assert resp.json()["tts_cache_status_at_start"] == uploaded_scenario["cache_status"]

    async def test_get_nonexistent_run_returns_404(self, client, user_auth_headers):
        resp = await client.get("/runs/run_doesnotexist", headers=user_auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"


class TestListRuns:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_list_runs_omits_events_payload(
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
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=200,
            ),
            headers=harness_auth_headers,
        )

        list_resp = await client.get("/runs/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        list_item = next(item for item in list_resp.json() if item["run_id"] == run_id)
        assert list_item["events"] == []
        assert list_item["tts_cache_status_at_start"] == uploaded_scenario["cache_status"]

        detail_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert detail_resp.status_code == 200
        assert len(detail_resp.json()["events"]) >= 2


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/turns
# ---------------------------------------------------------------------------
