"""Unit tests for ASCII path summary generation."""

from botcheck_scenarios import BotConfig, BranchCase, BranchConfig, ScenarioDefinition, ScenarioType, Turn

from botcheck_api.scenarios.service import ascii_path_summary


def _base_kwargs() -> dict:
    return {
        "id": "scenario-demo",
        "name": "Scenario Demo",
        "type": ScenarioType.ADVERSARIAL,
        "bot": BotConfig(endpoint="sip:bot@test.example.com"),
    }


def test_ascii_path_summary_for_linear_scenario_includes_implicit_and_end_edges():
    scenario = ScenarioDefinition(
        **_base_kwargs(),
        turns=[
            Turn(id="t1", speaker="harness", text="hello"),
            Turn(id="t2", speaker="harness", text="follow-up"),
        ],
    )
    summary = ascii_path_summary(scenario)
    assert "Scenario: scenario-demo (adversarial)" in summary
    assert "[01] t1 [harness_prompt] max_visits=1" in summary
    assert "-> t2 (implicit)" in summary
    assert "[02] t2 [harness_prompt] max_visits=1" in summary
    assert "-> END" in summary


def test_ascii_path_summary_for_branching_scenario_includes_all_branch_arms():
    scenario = ScenarioDefinition(
        **_base_kwargs(),
        turns=[
            Turn(
                id="t1",
                speaker="harness",
                text="route me",
                branching=BranchConfig(
                    cases=[
                        BranchCase(condition="billing", next="t2_billing"),
                        BranchCase(condition="technical", next="t2_technical"),
                    ],
                    default="t2_fallback",
                ),
            ),
            Turn(id="t2_billing", speaker="harness", text="billing"),
            Turn(id="t2_technical", speaker="harness", text="technical"),
            Turn(id="t2_fallback", speaker="harness", text="fallback"),
        ],
    )
    summary = ascii_path_summary(scenario)
    assert "? billing -> t2_billing" in summary
    assert "? technical -> t2_technical" in summary
    assert "? default -> t2_fallback" in summary
