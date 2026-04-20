"""Metrics and report metadata tests for assemble_report()."""

from botcheck_scenarios import ConversationTurn, DeterministicChecks, GateResult, RunStatus, ScenarioType

from report_test_helpers import call_assemble, make_scenario, passing_llm_scores, ts


class TestReportMetrics:

    def test_reliability_timing_threshold_can_block_gate(self):
        scenario = make_scenario(type=ScenarioType.RELIABILITY)
        llm_scores = {
            "scores": {
                "reliability": {
                    "score": 1.0,
                    "reasoning": "LLM saw no reliability issue.",
                    "findings": [],
                },
                "routing": {
                    "score": 1.0,
                    "reasoning": "routing ok",
                    "findings": [],
                },
            }
        }
        conversation = [
            ConversationTurn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            ConversationTurn(
                turn_id="t2",
                turn_number=2,
                speaker="bot",
                text="hi",
                audio_start_ms=3000,
                audio_end_ms=3600,
            ),
        ]
        deterministic = DeterministicChecks(
            interruptions_count=0,
            long_pause_count=1,
            p95_response_gap_ms=2500,
            interruption_recovery_pct=100.0,
            turn_taking_efficiency_pct=50.0,
        )
        report = call_assemble(
            scenario=scenario,
            llm_scores=llm_scores,
            conversation=conversation,
            deterministic=deterministic,
        )
        assert report.scores["reliability"].status == RunStatus.FAIL
        assert report.gate_result == GateResult.BLOCKED

    def test_reliability_timing_merges_with_existing_llm_reliability_score(self):
        """
        When both the LLM and deterministic timing assess 'reliability', the merge
        path in _apply_reliability_timing_overrides should lower the score to the
        minimum and upgrade the status to FAIL.
        """
        scenario = make_scenario(type=ScenarioType.RELIABILITY)
        llm_scores = {
            "scores": {
                "reliability": {
                    "score": 1.0,
                    "reasoning": "LLM saw no issue.",
                    "findings": [],
                },
                "routing": {
                    "score": 1.0,
                    "reasoning": "ok",
                    "findings": [],
                },
            }
        }
        # p95 gap of 2500 ms > gate of 1200 ms → deterministic status=FAIL
        # but the score should degrade proportionally instead of hard-zeroing.
        deterministic = DeterministicChecks(
            interruptions_count=0,
            long_pause_count=0,
            p95_response_gap_ms=2500,
            interruption_recovery_pct=100.0,
            turn_taking_efficiency_pct=100.0,
        )
        conversation = [
            ConversationTurn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            ConversationTurn(
                turn_id="t2",
                turn_number=2,
                speaker="bot",
                text="hi",
                audio_start_ms=3000,
                audio_end_ms=3600,
            ),
        ]
        report = call_assemble(
            scenario=scenario,
            llm_scores=llm_scores,
            conversation=conversation,
            deterministic=deterministic,
        )
        reliability = report.scores["reliability"]
        assert 0.0 < reliability.score < 1.0
        assert reliability.status == RunStatus.FAIL
        # Both reasonings should appear in the merged reasoning
        assert "LLM saw no issue" in reliability.reasoning
        assert "p95_gap_ms=2500" in reliability.reasoning
        assert report.gate_result == GateResult.BLOCKED

    def test_reliability_multiple_timing_failures_reduce_score_without_zeroing(self):
        scenario = make_scenario(type=ScenarioType.RELIABILITY)
        llm_scores = {
            "scores": {
                "reliability": {
                    "score": 1.0,
                    "reasoning": "LLM saw no reliability issue.",
                    "findings": [],
                },
            }
        }
        conversation = [
            ConversationTurn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            ConversationTurn(
                turn_id="t2",
                turn_number=2,
                speaker="bot",
                text="hi",
                audio_start_ms=6700,
                audio_end_ms=7200,
            ),
            ConversationTurn(
                turn_id="t3",
                turn_number=3,
                speaker="harness",
                text="next",
                audio_start_ms=7600,
                audio_end_ms=8000,
            ),
        ]
        deterministic = DeterministicChecks(
            interruptions_count=0,
            long_pause_count=1,
            p95_response_gap_ms=6154,
            interruption_recovery_pct=100.0,
            turn_taking_efficiency_pct=40.0,
        )

        report = call_assemble(
            scenario=scenario,
            llm_scores=llm_scores,
            conversation=conversation,
            deterministic=deterministic,
        )

        reliability = report.scores["reliability"]
        assert 0.0 < reliability.score < 0.8
        assert reliability.status == RunStatus.FAIL
        assert "p95_gap_ms=6154" in reliability.reasoning
        assert "turn_taking_efficiency_pct=40.00" in reliability.reasoning

    def test_reliability_exact_handoff_does_not_zero_score(self):
        scenario = make_scenario(type=ScenarioType.RELIABILITY)
        llm_scores = {
            "scores": {
                "reliability": {
                    "score": 1.0,
                    "reasoning": "LLM saw no reliability issue.",
                    "findings": [],
                },
            }
        }
        conversation = [
            ConversationTurn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=1000,
            ),
            ConversationTurn(
                turn_id="t2",
                turn_number=2,
                speaker="bot",
                text="hi",
                audio_start_ms=1000,
                audio_end_ms=1600,
            ),
            ConversationTurn(
                turn_id="t3",
                turn_number=3,
                speaker="harness",
                text="thanks",
                audio_start_ms=1630,
                audio_end_ms=2100,
            ),
        ]
        deterministic = DeterministicChecks(
            interruptions_count=0,
            long_pause_count=0,
            p95_response_gap_ms=30,
            interruption_recovery_pct=100.0,
            turn_taking_efficiency_pct=100.0,
        )

        report = call_assemble(
            scenario=scenario,
            llm_scores=llm_scores,
            conversation=conversation,
            deterministic=deterministic,
        )

        reliability = report.scores["reliability"]
        assert reliability.score == 1.0
        assert reliability.status == RunStatus.PASS
        assert "timing_within_thresholds" in reliability.reasoning

    def test_identity_fields(self):
        report = call_assemble()
        assert report.run_id == "run_test01"
        assert report.scenario_id == "test-scenario"
        assert report.scenario_version_hash == "abc123"
        assert report.tenant_id == "acme"
        assert report.judge_model == "claude-opus-4-6"
        assert report.judge_version == "0.1"

    def test_duration_ms_computed(self):
        report = call_assemble(started_at=ts(0), completed_at=ts(30))
        assert report.duration_ms == 30_000

    def test_bot_endpoint_from_scenario(self):
        report = call_assemble()
        assert report.bot_endpoint == "sip:bot@test.example.com"
