"""Tests for PATCH /runs/{id}."""

from unittest.mock import AsyncMock, patch

from botcheck_api.config import settings

from factories import make_run_complete_payload, make_run_patch_payload
from runs_test_helpers import SAMPLE_CONVERSATION, _create_run, _livekit_mock

class TestRunPatchValidation:
    async def test_patch_rejects_unknown_score_dimension(self, client, judge_auth_headers):
        """RunPatch.scores validator must reject keys not in ScoringDimension enum."""
        resp = await client.patch(
            "/runs/run_any",
            json=make_run_patch_payload(scores={"made_up_dimension": 0.9}),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 422
        assert "made_up_dimension" in resp.text

    async def test_patch_rejects_negative_cost_pence(self, client, judge_auth_headers):
        resp = await client.patch(
            "/runs/run_any",
            json=make_run_patch_payload(cost_pence=-1),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 422

    async def test_patch_accepts_all_valid_score_dimensions(
        self,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        """All ScoringDimension enum values should be accepted as score keys."""
        from unittest.mock import patch as mock_patch

        with mock_patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI") as mock_lk_class:
            mock_lk_class.return_value = _livekit_mock()
            run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                scores={
                    "routing": 1.0,
                    "policy": 1.0,
                    "jailbreak": 1.0,
                    "disclosure": 1.0,
                    "pii_handling": 1.0,
                    "reliability": 1.0,
                    "role_integrity": 1.0,
                },
            ),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 200


class TestPatchRun:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_patch_updates_fields(
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
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                failed_dimensions=[],
                summary="All good.",
                cost_pence=245,
                scores={"routing": 0.96, "jailbreak": 1.0},
                findings=[
                    {
                        "dimension": "routing",
                        "turn_id": "t2",
                        "turn_number": 2,
                        "speaker": "bot",
                        "quoted_text": "I can transfer you to billing.",
                        "finding": "Correct transfer intent.",
                        "severity": "info",
                        "positive": True,
                    }
                ],
                report_s3_key="reports/2026/02/23/run_abc.json",
            ),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify the gate endpoint now returns the patched data
        gate_resp = await client.get(f"/runs/{run_id}/gate", headers=user_auth_headers)
        assert gate_resp.status_code == 200
        assert gate_resp.json()["gate_result"] == "passed"

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["cost_pence"] == 245
        assert run_data["scores"]["routing"]["metric_type"] == "score"
        assert run_data["scores"]["routing"]["score"] == 0.96
        assert run_data["findings"][0]["turn_id"] == "t2"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_patch_accepts_structured_flag_metric(
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
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="passed",
                overall_status="pass",
                scores={
                    "jailbreak": {
                        "metric_type": "flag",
                        "passed": True,
                        "status": "pass",
                        "threshold": 1.0,
                        "gate": True,
                        "reasoning": "Bot refused all jailbreak probes.",
                    }
                },
            ),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        score = run_resp.json()["scores"]["jailbreak"]
        assert score["metric_type"] == "flag"
        assert score["passed"] is True
        assert score["score"] == 1.0

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_patch_gate_result_from_pending_is_rejected(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(gate_result="passed", summary="premature"),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 409

    async def test_patch_unknown_run_returns_404(self, client, judge_auth_headers):
        resp = await client.patch(
            "/runs/run_unknown",
            json=make_run_patch_payload(gate_result="passed"),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 404

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_same_state_patch_does_not_emit_duplicate_transition_event(
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
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        first = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                state="error",
                gate_result="blocked",
                summary="fail closed",
            ),
            headers=judge_auth_headers,
        )
        assert first.status_code == 200

        second = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                state="error",
                gate_result="blocked",
                summary="retry",
            ),
            headers=judge_auth_headers,
        )
        assert second.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        events = run_resp.json()["events"]
        transition_events = [e for e in events if e["type"] == "judge_state_patch"]
        assert len(transition_events) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_patch_does_not_double_release_sip_slot(
        self,
        mock_lk_class,
        client,
        sip_uploaded_scenario,
        user_auth_headers,
        judge_auth_headers,
        monkeypatch,
    ):
        """patch_run must not release the SIP slot a second time after complete_run already did.

        The normal flow is: complete_run releases the slot and sets sip_slot_held=False.
        patch_run's guard (`run.sip_slot_held`) must prevent a double-release when the
        judge writes results back to a run whose slot was already freed.
        """
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

        # complete_run releases the slot (release_mock called once, sip_slot_held→False)
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers={"Authorization": f"Bearer {settings.harness_secret}"},
        )
        release_mock.assert_awaited_once()
        release_mock.reset_mock()

        # Judge patches the result — slot is already cleared, must not release again
        resp = await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="blocked",
                summary="jailbreak failure",
            ),
            headers=judge_auth_headers,
        )
        assert resp.status_code == 200
        release_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# PUT/GET /runs/{run_id}/recording
# ---------------------------------------------------------------------------
