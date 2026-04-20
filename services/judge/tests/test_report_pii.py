"""Finding, severity, and quoted-text assertions for assemble_report()."""

from botcheck_scenarios import ConversationTurn, DeterministicChecks, ScenarioType

from report_test_helpers import call_assemble, make_scenario


class TestReportPii:

    def test_no_findings(self):
        report = call_assemble()
        assert report.all_findings == []

    def test_finding_assembled_correctly(self):
        llm_scores = {
            "scores": {
                "jailbreak": {
                    "score": 0.4,
                    "reasoning": "Bot partially complied.",
                    "findings": [
                        {
                            "turn_number": 2,
                            "speaker": "bot",
                            "quoted_text": "Sure, I can help with that.",
                            "finding": "Bot complied with jailbreak attempt.",
                            "severity": "high",
                            "positive": False,
                        }
                    ],
                },
                "disclosure": {
                    "score": 1.0,
                    "reasoning": "No disclosure.",
                    "findings": [],
                },
            }
        }
        report = call_assemble(llm_scores=llm_scores)
        assert len(report.all_findings) == 1
        f = report.all_findings[0]
        assert f.turn_number == 2
        assert f.quoted_text == "Sure, I can help with that."
        assert f.severity.value == "high"
        assert f.positive is False

    def test_llm_finding_resolves_turn_id_and_visit_from_taken_path_steps(self):
        llm_scores = {
            "scores": {
                "jailbreak": {
                    "score": 0.4,
                    "reasoning": "Bot complied.",
                    "findings": [
                        {
                            "turn_number": 2,
                            "speaker": "bot",
                            "quoted_text": "Sure, here's that info.",
                            "finding": "Complied with attack prompt.",
                            "severity": "high",
                            "positive": False,
                        }
                    ],
                },
                "disclosure": {
                    "score": 1.0,
                    "reasoning": "No disclosure.",
                    "findings": [],
                },
            }
        }
        conversation = [
            ConversationTurn(
                turn_id="intro",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=200,
            ),
            ConversationTurn(
                turn_id="branch-bot",
                turn_number=2,
                speaker="bot",
                text="Sure, here's that info.",
                audio_start_ms=300,
                audio_end_ms=600,
            ),
        ]
        report = call_assemble(
            llm_scores=llm_scores,
            conversation=conversation,
            taken_path_steps=[
                {"turn_id": "intro", "visit": 1, "turn_number": 1},
                {"turn_id": "branch-bot", "visit": 2, "turn_number": 2},
            ],
        )
        assert len(report.all_findings) == 1
        finding = report.all_findings[0]
        assert finding.turn_id == "branch-bot"
        assert finding.turn_number == 2
        assert finding.visit == 2

    def test_findings_aggregated_across_dimensions(self):
        llm_scores = {
            "scores": {
                "jailbreak": {
                    "score": 0.5,
                    "reasoning": "Issues found.",
                    "findings": [
                        {
                            "turn_number": 1,
                            "speaker": "bot",
                            "quoted_text": "text1",
                            "finding": "issue1",
                            "severity": "high",
                            "positive": False,
                        }
                    ],
                },
                "disclosure": {
                    "score": 0.5,
                    "reasoning": "Issues found.",
                    "findings": [
                        {
                            "turn_number": 2,
                            "speaker": "bot",
                            "quoted_text": "text2",
                            "finding": "issue2",
                            "severity": "medium",
                            "positive": False,
                        }
                    ],
                },
            }
        }
        report = call_assemble(llm_scores=llm_scores)
        assert len(report.all_findings) == 2

    def test_deterministic_findings_include_path_visit_coordinate(self):
        scenario = make_scenario(type=ScenarioType.RELIABILITY)
        llm_scores = {
            "scores": {
                "reliability": {
                    "score": 1.0,
                    "reasoning": "LLM saw no issue.",
                    "findings": [],
                }
            }
        }
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
            taken_path_steps=[
                {"turn_id": "t1", "visit": 1, "turn_number": 1},
                {"turn_id": "t2", "visit": 3, "turn_number": 2},
            ],
        )
        reliability_findings = report.scores["reliability"].findings
        assert reliability_findings
        assert reliability_findings[0].turn_id == "t2"
        assert reliability_findings[0].visit == 3

    def test_severity_invalid_defaults_to_medium(self):
        llm_scores = {
            "scores": {
                "jailbreak": {
                    "score": 1.0,
                    "reasoning": "ok",
                    "findings": [
                        {
                            "turn_number": 1,
                            "speaker": "bot",
                            "quoted_text": "Hello.",
                            "finding": "Normal greeting.",
                            "severity": "not_a_real_severity",
                            "positive": True,
                        }
                    ],
                }
            }
        }
        report = call_assemble(llm_scores=llm_scores)
        assert len(report.all_findings) == 1
        assert report.all_findings[0].severity.value == "medium"
