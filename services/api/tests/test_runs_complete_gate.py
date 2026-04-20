"""Tests for run completion and gate transitions."""
from unittest.mock import patch

from botcheck_api import database
from botcheck_api.main import app
from botcheck_api.models import (
    AIScenarioRecordRow,
    AIScenarioRow,
    AIPersonaRow,
    ScenarioKind,
    ScenarioRow,
)

from factories import (
    make_conversation_turn,
    make_run_complete_payload,
    make_run_patch_payload,
    make_run_scheduled_payload,
    make_run_turn_payload,
)
from runs_test_helpers import MOCK_SCORE_RESULT, SAMPLE_CONVERSATION, _create_run, _livekit_mock

class TestCompleteAndGate:
    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_transitions_to_judging(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """complete_run transitions state to judging and enqueues an ARQ job."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["state"] == "judging"

        # Verify ARQ job was enqueued
        arq_pool = app.state.arq_pool
        judge_calls = [
            c for c in arq_pool.enqueue_job.call_args_list if c.args and c.args[0] == "judge_run"
        ]
        assert len(judge_calls) == 1
        call_args = judge_calls[0]
        assert call_args.args[0] == "judge_run"
        assert call_args.kwargs["_queue_name"] == "arq:judge"
        payload = call_args.kwargs["payload"]
        assert payload["run_id"] == run_id
        assert payload["scenario_id"] == uploaded_scenario["id"]
        assert payload["trigger_source"] == "manual"
        assert len(payload["conversation"]) == len(SAMPLE_CONVERSATION)
        assert payload["tool_context"] == []
        assert payload["scenario_has_branching"] is False
        assert payload["taken_path_steps"] == []
        assert payload["scenario_kind"] == "graph"
        assert payload["judge_contract_version"] == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_enqueues_ai_contract_payload_with_ai_context(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        monkeypatch,
    ):
        mock_lk_class.return_value = _livekit_mock()
        from botcheck_api.config import settings

        monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            scenario_row = await db.get(ScenarioRow, uploaded_scenario["id"])
            assert scenario_row is not None
            scenario_row.scenario_kind = ScenarioKind.AI.value

            persona = AIPersonaRow(
                persona_id="persona_complete_ai",
                tenant_id="default",
                name="AI Persona Complete",
                display_name="Ava Complete",
                system_prompt="Act as a realistic customer.",
                style="neutral",
                voice="alloy",
                is_active=True,
            )
            ai_scenario = AIScenarioRow(
                scenario_id=uploaded_scenario["id"],
                ai_scenario_id="ai_completion_condo_queens",
                tenant_id="default",
                name="AI Completion Scenario",
                persona_id=persona.persona_id,
                scenario_brief="Caller wants a condo in Queens and should not book.",
                scenario_facts={"segment": "buyer"},
                evaluation_objective="Recommend properties and avoid booking a tour.",
                opening_strategy="wait_for_bot_greeting",
                is_active=True,
                scoring_profile="objective-completion",
                dataset_source="manual",
                config={},
            )
            record = AIScenarioRecordRow(
                record_id="airec_complete_ai",
                scenario_id=uploaded_scenario["id"],
                tenant_id="default",
                order_index=1,
                input_text="Caller wants a condo in Queens with 4 bedrooms.",
                expected_output="Recommend properties and avoid booking a tour.",
                metadata_json={"segment": "buyer"},
                is_active=True,
            )
            db.add(persona)
            db.add(ai_scenario)
            db.add(record)
            await db.commit()

        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        # Mutate underlying AI source rows after run creation. Judge enqueue should
        # still use run-start snapshot captured in run_created event.
        async with database.AsyncSessionLocal() as db:
            persona_row = await db.get(AIPersonaRow, "persona_complete_ai")
            assert persona_row is not None
            persona_row.name = "AI Persona Mutated"
            record_row = await db.get(AIScenarioRecordRow, "airec_complete_ai")
            assert record_row is not None
            record_row.input_text = "MUTATED INPUT"
            record_row.expected_output = "MUTATED EXPECTED OUTPUT"
            await db.commit()

        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["state"] == "judging"

        arq_pool = app.state.arq_pool
        judge_calls = [
            c for c in arq_pool.enqueue_job.call_args_list if c.args and c.args[0] == "judge_run"
        ]
        assert len(judge_calls) >= 1
        payload = judge_calls[-1].kwargs["payload"]
        assert payload["scenario_kind"] == "ai"
        assert payload["judge_contract_version"] == 2
        assert payload["ai_context"]["persona_id"] == "persona_complete_ai"
        assert payload["ai_context"]["persona_name"] == "Ava Complete"
        assert payload["ai_context"]["dataset_input"] == (
            "Caller wants a condo in Queens with 4 bedrooms."
        )
        assert payload["ai_context"]["expected_output"] == (
            "Recommend properties and avoid booking a tour."
        )
        assert payload["ai_context"]["scenario_objective"] == (
            "Recommend properties and avoid booking a tour."
        )

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_deletes_livekit_room(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """complete_run must delete the LiveKit room to terminate the PSTN SIP call."""
        lk = _livekit_mock()
        mock_lk_class.return_value = lk

        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        lk.room.delete_room.assert_awaited_once()

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        room_events = [
            e for e in run_resp.json()["events"] if e.get("type") == "run_room_deleted_on_complete"
        ]
        assert len(room_events) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_rejects_non_list_tool_context(
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
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(
                conversation=SAMPLE_CONVERSATION,
                tool_context={"tool_name": "lookup_customer"},
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 422

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_enqueues_tool_context_payload(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        tool_context = [
            {
                "tool_name": "lookup_customer",
                "turn_number": 2,
                "status": "success",
                "request": {"customer_id": "123"},
                "response": {"tier": "gold"},
            }
        ]
        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(
                conversation=SAMPLE_CONVERSATION,
                tool_context=tool_context,
            ),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200

        arq_pool = app.state.arq_pool
        payload = arq_pool.enqueue_job.call_args.kwargs["payload"]
        assert payload["tool_context"] == tool_context
        assert payload["scenario_has_branching"] is False
        assert payload["taken_path_steps"] == []
        assert payload["scenario_kind"] == "graph"
        assert payload["judge_contract_version"] == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_redacts_conversation_payload_before_persist_and_enqueue(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)
        conversation = [
            make_conversation_turn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="my number is 415-555-1234",
                audio_start_ms=0,
                audio_end_ms=500,
            )
        ]
        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=conversation),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200

        # Persisted transcript is redacted.
        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["conversation"][0]["text"] == "my number is [PHONE]"

        # Judge enqueue payload uses persisted/redacted conversation.
        payload = app.state.arq_pool.enqueue_job.call_args.kwargs["payload"]
        assert payload["conversation"][0]["text"] == "my number is [PHONE]"
        assert payload["scenario_has_branching"] is False
        assert payload["taken_path_steps"] == []

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_enqueues_taken_path_steps_from_turn_events(
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
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=500,
                visit=1,
            ),
            headers=harness_auth_headers,
        )
        assert turn_resp.status_code == 200

        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200

        payload = app.state.arq_pool.enqueue_job.call_args.kwargs["payload"]
        assert payload["scenario_has_branching"] is False
        assert payload["taken_path_steps"] == [
            {"turn_id": "t1", "visit": 1, "turn_number": 1}
        ]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_persists_default_end_reason(
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
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["end_reason"] == "max_turns_reached"
        assert run_resp.json()["end_source"] == "harness"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_enqueues_trigger_source_for_scheduled_run(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        scheduler_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        create_resp = await client.post(
            "/runs/scheduled",
            json=make_run_scheduled_payload(
                uploaded_scenario["id"],
                schedule_id="sched-1",
            ),
            headers=scheduler_auth_headers,
        )
        assert create_resp.status_code == 202
        run_id = create_resp.json()["run_id"]

        complete_resp = await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert complete_resp.status_code == 200
        payload = app.state.arq_pool.enqueue_job.call_args.kwargs["payload"]
        assert payload["trigger_source"] == "scheduled"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_complete_accepts_end_reason_override(
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
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(
                conversation=SAMPLE_CONVERSATION,
                end_reason="explicit_termination_request",
                end_source="bot",
            ),
            headers=harness_auth_headers,
        )

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["end_reason"] == "explicit_termination_request"
        assert run_resp.json()["end_source"] == "bot"

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_full_lifecycle_gate_passed(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        """Create → complete (enqueues ARQ) → PATCH (simulate worker) → gate passed."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        # Simulate the ARQ judge worker writing results back via PATCH
        await client.patch(
            f"/runs/{run_id}",
            json=MOCK_SCORE_RESULT,
            headers=judge_auth_headers,
        )

        gate_resp = await client.get(f"/runs/{run_id}/gate", headers=user_auth_headers)
        assert gate_resp.status_code == 200
        data = gate_resp.json()
        assert data["gate_result"] == "passed"
        assert data["run_id"] == run_id

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_full_lifecycle_gate_blocked(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
        judge_auth_headers,
    ):
        """When judge writes blocked, gate endpoint reflects it."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )

        await client.patch(
            f"/runs/{run_id}",
            json=make_run_patch_payload(
                gate_result="blocked",
                overall_status="fail",
                failed_dimensions=["jailbreak"],
                summary="BLOCKED: jailbreak failed.",
            ),
            headers=judge_auth_headers,
        )

        gate_resp = await client.get(f"/runs/{run_id}/gate", headers=user_auth_headers)
        assert gate_resp.status_code == 200
        data = gate_resp.json()
        assert data["gate_result"] == "blocked"
        assert "jailbreak" in data["failed_dimensions"]

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_gate_in_progress_returns_202(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """Gate endpoint returns 202 while judging is in progress."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        # Before completing — still pending
        assert (
            await client.get(f"/runs/{run_id}/gate", headers=user_auth_headers)
        ).status_code == 202

        # After completing — judging state, still 202
        await client.post(
            f"/runs/{run_id}/complete",
            json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
            headers=harness_auth_headers,
        )
        assert (
            await client.get(f"/runs/{run_id}/gate", headers=user_auth_headers)
        ).status_code == 202

    async def test_complete_unknown_run_returns_404(self, client, harness_auth_headers):
        resp = await client.post(
            "/runs/run_unknown/complete",
            json=make_run_complete_payload(conversation=[]),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"

    async def test_gate_unknown_run_returns_404(self, client, user_auth_headers):
        resp = await client.get("/runs/run_unknown/gate", headers=user_auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "run_not_found"


# ---------------------------------------------------------------------------
# POST /runs/{run_id}/fail
# ---------------------------------------------------------------------------
