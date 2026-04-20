"""Tests for run recording upload/read routes."""

from unittest.mock import AsyncMock, patch

from factories import make_run_create_payload
from runs_test_helpers import _create_run, _livekit_mock

class TestRunRecordings:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_recording_upload_requires_harness_service_token(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.put(
            f"/runs/{run_id}/recording",
            content=b"RIFF....WAVE",
            headers=judge_auth_headers,
        )
        assert resp.status_code == 403

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_recording_upload_and_download_round_trip(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        upload_mock = AsyncMock(return_value=None)
        download_mock = AsyncMock(return_value=(b"RIFF....WAVE", "audio/wav"))
        monkeypatch.setattr("botcheck_api.runs.runs_artifacts.upload_artifact_bytes", upload_mock)
        monkeypatch.setattr("botcheck_api.runs.runs_artifacts.download_artifact_bytes", download_mock)

        upload_resp = await client.put(
            f"/runs/{run_id}/recording?format=wav&duration_ms=1234",
            content=b"RIFF....WAVE",
            headers={**harness_auth_headers, "Content-Type": "audio/wav"},
        )
        assert upload_resp.status_code == 200
        payload = upload_resp.json()
        assert payload["ok"] is True
        assert "/recordings/" in payload["recording_s3_key"]
        upload_mock.assert_awaited()

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["recording_s3_key"] == payload["recording_s3_key"]

        dl_resp = await client.get(f"/runs/{run_id}/recording", headers=user_auth_headers)
        assert dl_resp.status_code == 200
        assert dl_resp.content == b"RIFF....WAVE"
        assert dl_resp.headers["content-type"].startswith("audio/wav")
        download_mock.assert_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_recording_upload_skips_no_audio_retention_profile(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"], retention_profile="no_audio"
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        upload_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.runs.runs_artifacts.upload_artifact_bytes", upload_mock)

        upload_resp = await client.put(
            f"/runs/{run_id}/recording",
            content=b"RIFF....WAVE",
            headers={**harness_auth_headers, "Content-Type": "audio/wav"},
        )
        assert upload_resp.status_code == 200
        payload = upload_resp.json()
        assert payload["recording_s3_key"] is None
        assert payload["skipped_reason"] == "retention_profile_no_audio"
        upload_mock.assert_not_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_recording_download_requires_user_auth(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        upload_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.runs.runs_artifacts.upload_artifact_bytes", upload_mock)
        upload_resp = await client.put(
            f"/runs/{run_id}/recording",
            content=b"RIFF....WAVE",
            headers={**harness_auth_headers, "Content-Type": "audio/wav"},
        )
        assert upload_resp.status_code == 200

        dl_resp = await client.get(f"/runs/{run_id}/recording")
        assert dl_resp.status_code == 401

    async def test_recording_download_missing_run_returns_error_code(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.get("/runs/run_missing/recording", headers=user_auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"


# ---------------------------------------------------------------------------
# POST /runs/retention/sweep
# ---------------------------------------------------------------------------
