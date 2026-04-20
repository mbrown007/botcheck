"""Unit tests for scenario validation cycle warnings."""

from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn

from botcheck_api.scenarios.service import cycle_warnings


def _scenario(*, turns: list[Turn]) -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cycle-test",
        name="Scenario Cycle Test",
        type=ScenarioType.ADVERSARIAL,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=turns,
    )


def test_cycle_warnings_empty_for_linear_scenario():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", wait_for_response=False),
            Turn(id="t2", text="two", wait_for_response=False),
        ]
    )
    assert cycle_warnings(scenario) == []


def test_cycle_warnings_guaranteed_loop_for_all_max_visits_one():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", next="t2", max_visits=1, wait_for_response=False),
            Turn(id="t2", text="two", next="t1", max_visits=1, wait_for_response=False),
        ]
    )
    warnings = cycle_warnings(scenario)
    assert len(warnings) == 1
    assert warnings[0].code == "CYCLE_GUARANTEED_LOOP"
    assert warnings[0].turn_ids == ["t1", "t2"]


def test_cycle_warnings_unlimited_visit_when_any_node_has_zero():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="loop", next="t1", max_visits=0, wait_for_response=False),
        ]
    )
    warnings = cycle_warnings(scenario)
    assert len(warnings) == 1
    assert warnings[0].code == "CYCLE_UNLIMITED_VISIT"
    assert warnings[0].turn_ids == ["t1"]


def test_cycle_warnings_no_warning_for_bounded_cycle_with_max_visits_two():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", next="t2", max_visits=2, wait_for_response=False),
            Turn(id="t2", text="two", next="t1", max_visits=2, wait_for_response=False),
        ]
    )
    warnings = cycle_warnings(scenario)
    assert warnings == []


def test_cycle_warnings_mixed_cycle_with_zero_emits_only_unlimited_visit():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", next="t2", max_visits=1, wait_for_response=False),
            Turn(id="t2", text="two", next="t1", max_visits=0, wait_for_response=False),
        ]
    )
    warnings = cycle_warnings(scenario)
    assert len(warnings) == 1
    assert warnings[0].code == "CYCLE_UNLIMITED_VISIT"
    assert warnings[0].turn_ids == ["t1", "t2"]


def test_cycle_warnings_detect_branch_only_cycle():
    scenario = _scenario(
        turns=[
            Turn(
                id="t1",
                text="route",
                wait_for_response=False,
                branching={
                    "cases": [{"condition": "loop route", "next": "t2"}],
                    "default": "t3",
                },
                max_visits=1,
            ),
            Turn(id="t2", text="loop node", next="t1", max_visits=1, wait_for_response=False),
            Turn(id="t3", text="terminal", wait_for_response=False),
        ]
    )
    warnings = cycle_warnings(scenario)
    assert len(warnings) == 1
    assert warnings[0].code == "CYCLE_GUARANTEED_LOOP"
    assert warnings[0].turn_ids == ["t1", "t2"]
