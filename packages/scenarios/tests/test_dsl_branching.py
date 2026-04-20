"""Branching and graph validation tests for Scenario DSL models."""

import pytest
from dsl_test_helpers import minimal_scenario
from pydantic import ValidationError

from botcheck_scenarios import BranchCase, BranchConfig, BranchMode, ScenarioConfig, Turn


class TestDslBranching:

    def test_branching_scenario_parses_and_preserves_fields(self):
        s = minimal_scenario(
            turns=[
                Turn(
                    id="t1_open",
                    text="Billing or technical support?",
                    branching=BranchConfig(
                        default="t_fallback",
                        cases=[
                            BranchCase(
                                condition="bot offers billing support",
                                next="t_billing",
                            ),
                            BranchCase(
                                condition="bot offers technical support",
                                next="t_tech",
                            ),
                        ],
                    ),
                    max_visits=2,
                ),
                Turn(id="t_billing", text="What is my balance?", next="t_end"),
                Turn(id="t_tech", text="My app cannot connect.", next="t_end"),
                Turn(id="t_fallback", text="Please repeat.", next="t1_open"),
                Turn(id="t_end", text="Thanks, goodbye.", wait_for_response=False),
            ],
            config=ScenarioConfig(max_total_turns=40),
        )
        assert s.config.max_total_turns == 40
        first = s.turns[0]
        assert first.branching is not None
        assert first.branching.mode == BranchMode.CLASSIFIER
        assert first.branching.default == "t_fallback"
        assert [c.next for c in first.branching.cases] == ["t_billing", "t_tech"]
        assert first.max_visits == 2

    def test_turn_rejects_branching_and_next_on_same_turn(self):
        with pytest.raises(ValidationError, match="both branching and next"):
            Turn(
                id="t1",
                text="Hello",
                next="t2",
                branching=BranchConfig(
                    default="t2",
                    cases=[BranchCase(condition="x", next="t2")],
                ),
            )

    def test_branching_conditions_must_be_unique_after_normalization(self):
        with pytest.raises(ValidationError, match="must be unique"):
            BranchConfig(
                default="t2",
                cases=[
                    BranchCase(condition="Billing", next="t2"),
                    BranchCase(condition="  billing  ", next="t3"),
                ],
            )

    def test_branching_rejects_reserved_default_selector_as_condition(self):
        with pytest.raises(ValidationError, match="reserved selector 'default'"):
            BranchConfig(
                default="t2",
                cases=[BranchCase(condition=" Default ", next="t2")],
            )

    def test_branching_requires_non_empty_cases(self):
        with pytest.raises(ValidationError, match="at least one case"):
            BranchConfig(default="t2", cases=[])

    def test_keyword_branching_requires_match(self):
        with pytest.raises(ValidationError, match="requires branching.cases\\[\\*\\]\\.match"):
            BranchConfig(
                mode=BranchMode.KEYWORD,
                default="t2",
                cases=[BranchCase(condition="billing", next="t2")],
            )

    def test_keyword_branching_rejects_regex(self):
        with pytest.raises(ValidationError, match="does not allow branching.cases\\[\\*\\]\\.regex"):
            BranchConfig(
                mode=BranchMode.KEYWORD,
                default="t2",
                cases=[BranchCase(condition="billing", next="t2", match="bill", regex="bill")],
            )

    def test_regex_branching_requires_valid_regex(self):
        with pytest.raises(ValidationError, match="regex invalid"):
            BranchConfig(
                mode=BranchMode.REGEX,
                default="t2",
                cases=[BranchCase(condition="billing", next="t2", regex="(")],
            )

    def test_classifier_branching_rejects_match_fields(self):
        with pytest.raises(ValidationError, match="does not allow case.match or case.regex"):
            BranchConfig(
                mode=BranchMode.CLASSIFIER,
                default="t2",
                cases=[BranchCase(condition="billing", next="t2", match="bill")],
            )

    def test_next_target_must_exist(self):
        with pytest.raises(ValidationError, match="next target 'missing' does not exist"):
            minimal_scenario(
                turns=[
                    Turn(id="t1", text="Hello", next="missing"),
                    Turn(id="t2", text="Bye"),
                ]
            )

    def test_branching_default_target_must_exist(self):
        with pytest.raises(ValidationError, match="branching.default target 'missing'"):
            minimal_scenario(
                turns=[
                    Turn(
                        id="t1",
                        text="Hello",
                        branching=BranchConfig(
                            default="missing",
                            cases=[BranchCase(condition="route", next="t2")],
                        ),
                    ),
                    Turn(id="t2", text="Bye"),
                ]
            )

    def test_branching_case_target_must_exist(self):
        with pytest.raises(ValidationError, match="branching case 'route' target 'missing'"):
            minimal_scenario(
                turns=[
                    Turn(
                        id="t1",
                        text="Hello",
                        branching=BranchConfig(
                            default="t2",
                            cases=[BranchCase(condition="route", next="missing")],
                        ),
                    ),
                    Turn(id="t2", text="Bye"),
                ]
            )

    def test_turn_ids_must_be_unique(self):
        with pytest.raises(ValidationError, match="turn ids must be unique"):
            minimal_scenario(
                turns=[
                    Turn(id="t1", text="Hello"),
                    Turn(id="t1", text="Duplicate"),
                ]
            )

    def test_time_route_default_target_must_exist(self):
        with pytest.raises(ValidationError, match="time_route default target 'missing'"):
            minimal_scenario(
                turns=[
                    {
                        "kind": "time_route",
                        "id": "t_route",
                        "timezone": "UTC",
                        "windows": [
                            {
                                "label": "business_hours",
                                "start": "09:00",
                                "end": "17:00",
                                "next": "t_business",
                            }
                        ],
                        "default": "missing",
                    },
                    Turn(id="t_business", text="business"),
                ]
            )

    def test_time_route_window_target_must_exist(self):
        with pytest.raises(
            ValidationError,
            match="time_route window 'business_hours' target 'missing'",
        ):
            minimal_scenario(
                turns=[
                    {
                        "kind": "time_route",
                        "id": "t_route",
                        "timezone": "UTC",
                        "windows": [
                            {
                                "label": "business_hours",
                                "start": "09:00",
                                "end": "17:00",
                                "next": "missing",
                            }
                        ],
                        "default": "t_default",
                    },
                    Turn(id="t_default", text="default"),
                ]
            )
