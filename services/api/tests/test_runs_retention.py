"""Tests for run retention sweep."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from botcheck_api.config import settings
from botcheck_api.main import app

from factories import (
    make_conversation_turn,
    make_run_complete_payload,
    make_run_create_payload,
    make_run_patch_payload,
    make_run_retention_sweep_payload,
)
from runs_test_helpers import SAMPLE_CONVERSATION, _livekit_mock, _set_run_created_at

class TestRetentionSweep:
    async def test_retention_sweep_requires_service_auth(self, client):
        resp = await client.post(
            "/runs/retention/sweep",
            json=make_run_retention_sweep_payload(),
        )
        assert resp.status_code == 401

    async def test_retention_sweep_rejects_non_judge_service(
        self,
        client,
        harness_auth_headers,
    ):
        resp = await client.post(
            "/runs/retention/sweep",
            json=make_run_retention_sweep_payload(),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 403

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_retention_sweep_purges_due_ephemeral_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                retention_profile="ephemeral",
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        # Persist transcript via complete path.
        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(
                conversation=[
                    make_conversation_turn(
                        turn_id="t1",
                        turn_number=1,
                        speaker="harness",
                        text="my number is 415-555-1234",
                        audio_start_ms=0,
                        audio_end_ms=500,
                    )
                ]
            ),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200

        # Move run to COMPLETE and set a report key so sweeper can delete/purge.
        patch_resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                report_s3_key="acme/reports/2026/02/27/run_test.json",
                findings=[{"dimension": "routing", "quoted_text": "x"}],
            ),
            headers=judge_auth_headers,
        )
        assert patch_resp.status_code == 200

        # Make the run older than ephemeral cutoff.
        await _set_run_created_at(
            run_id,
            datetime.now(UTC) - timedelta(days=2),
        )

        delete_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.runs.runs_lifecycle.delete_report_artifact", delete_mock)

        sweep_resp = await client.post(
            "/runs/retention/sweep",
            json=make_run_retention_sweep_payload(limit=100),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["mutated"] >= 1
        assert payload["artifacts_deleted"] >= 1
        assert payload["artifacts_failed"] == 0

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        data = run_detail.json()
        assert data["conversation"] == []
        assert data["findings"] == []
        assert data["report_s3_key"] is None
        assert any(e["type"] == "retention_sweep_applied" for e in data["events"])
        delete_mock.assert_awaited()

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_retention_sweep_dry_run_does_not_mutate(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                retention_profile="ephemeral",
            ),
            headers=user_auth_headers,
        )
        run_id = run_resp.json()["run_id"]

        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                report_s3_key="acme/reports/2026/02/27/run_test.json",
            ),
            headers=judge_auth_headers,
        )
        await _set_run_created_at(run_id, datetime.now(UTC) - timedelta(days=2))

        delete_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.runs.runs_lifecycle.delete_report_artifact", delete_mock)

        sweep_resp = await client.post(
            "/runs/retention/sweep",
            json=make_run_retention_sweep_payload(dry_run=True, limit=100),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        assert sweep_resp.json()["dry_run"] is True
        assert sweep_resp.json()["mutated"] >= 1
        delete_mock.assert_not_awaited()

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["conversation"] != []
        assert run_detail.json()["report_s3_key"] is not None

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_retention_sweep_never_deletes_tts_cache_prefixed_keys(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_resp = await client.post(
            "/runs/",
            json=make_run_create_payload(
                uploaded_scenario["id"],
                retention_profile="ephemeral",
            ),
            headers=user_auth_headers,
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["run_id"]

        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        cache_like_key = f"{settings.tenant_id}/tts-cache/t1/hash.wav"
        await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                report_s3_key=cache_like_key,
            ),
            headers=judge_auth_headers,
        )
        await _set_run_created_at(run_id, datetime.now(UTC) - timedelta(days=2))

        delete_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.runs.runs_lifecycle.delete_report_artifact", delete_mock)

        sweep_resp = await client.post(
            "/runs/retention/sweep",
            json=make_run_retention_sweep_payload(limit=100),
            headers=judge_auth_headers,
        )
        assert sweep_resp.status_code == 200
        payload = sweep_resp.json()
        assert payload["mutated"] >= 1
        assert payload["artifacts_deleted"] == 0
        delete_mock.assert_not_awaited()

        run_detail = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["report_s3_key"] == cache_like_key


# ---------------------------------------------------------------------------
# Cross-tenant isolation  (item 12)
# ---------------------------------------------------------------------------
