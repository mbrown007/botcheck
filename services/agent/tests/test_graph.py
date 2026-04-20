"""Phase 5 graph engine tests (linear parity + branching traversal guards)."""

from src.graph import (
    GraphTraversal,
    HarnessLoopError,
    HarnessMaxTurnsError,
    build_turn_sequence,
)

from botcheck_scenarios import (
    BotConfig,
    BranchCase,
    BranchConfig,
    ScenarioBlock,
    ScenarioConfig,
    ScenarioDefinition,
    ScenarioType,
    TimeRouteBlock,
    Turn,
    WaitBlock,
)


def _scenario(
    *, turns: list[ScenarioBlock | Turn], config: ScenarioConfig | None = None
) -> ScenarioDefinition:
    return ScenarioDefinition(
        id="graph-test",
        name="Graph Test",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=turns,
        config=config or ScenarioConfig(),
    )


def test_build_turn_sequence_linear_parity():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", wait_for_response=False),
            Turn(id="t2", text="two", wait_for_response=False),
            Turn(id="t3", text="three", wait_for_response=False),
        ]
    )

    sequence = build_turn_sequence(scenario, max_total_turns_hard_cap=50)
    assert [turn.id for turn in sequence] == ["t1", "t2", "t3"]


def test_build_turn_sequence_respects_explicit_next():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", next="t3", wait_for_response=False),
            Turn(id="t2", text="two", wait_for_response=False),
            Turn(id="t3", text="three", wait_for_response=False),
        ]
    )

    sequence = build_turn_sequence(scenario, max_total_turns_hard_cap=50)
    assert [turn.id for turn in sequence] == ["t1", "t3"]


def test_build_turn_sequence_branches_to_selected_condition():
    scenario = _scenario(
        turns=[
            Turn(
                id="t1",
                text="route me",
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[
                        BranchCase(condition="billing", next="t_billing"),
                        BranchCase(condition="technical", next="t_tech"),
                    ],
                ),
                wait_for_response=False,
            ),
            Turn(id="t_billing", text="billing branch", next="t_end", wait_for_response=False),
            Turn(id="t_tech", text="tech branch", next="t_end", wait_for_response=False),
            Turn(id="t_fallback", text="fallback branch", wait_for_response=False),
            Turn(id="t_end", text="end", wait_for_response=False),
        ]
    )

    sequence = build_turn_sequence(
        scenario,
        max_total_turns_hard_cap=50,
        select_condition=lambda _turn, _conditions: "technical",
    )
    assert [turn.id for turn in sequence] == ["t1", "t_tech", "t_end"]


def test_build_turn_sequence_uses_default_when_condition_unknown():
    scenario = _scenario(
        turns=[
            Turn(
                id="t1",
                text="route me",
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[BranchCase(condition="billing", next="t_billing")],
                ),
                wait_for_response=False,
            ),
            Turn(id="t_billing", text="billing branch", wait_for_response=False),
            Turn(id="t_fallback", text="fallback branch", wait_for_response=False),
        ]
    )

    sequence = build_turn_sequence(
        scenario,
        max_total_turns_hard_cap=50,
        select_condition=lambda _turn, _conditions: "not-a-real-branch",
    )
    assert [turn.id for turn in sequence] == ["t1", "t_fallback"]


def test_build_turn_sequence_raises_loop_error_at_max_visits_limit():
    scenario = _scenario(
        turns=[Turn(id="t1", text="loop", next="t1", max_visits=1, wait_for_response=False)]
    )

    try:
        build_turn_sequence(scenario, max_total_turns_hard_cap=50)
        raise AssertionError("expected HarnessLoopError")
    except HarnessLoopError as exc:
        assert "max_visits=1" in str(exc)
        assert exc.turn_id == "t1"
        assert exc.visit == 2
        assert exc.max_visits == 1
        assert exc.effective_cap == 50


def test_build_turn_sequence_raises_max_turns_with_hard_cap_precedence():
    scenario = _scenario(
        turns=[Turn(id="t1", text="loop", next="t1", max_visits=0, wait_for_response=False)],
        config=ScenarioConfig(max_total_turns=100),
    )

    try:
        build_turn_sequence(scenario, max_total_turns_hard_cap=3)
        raise AssertionError("expected HarnessMaxTurnsError")
    except HarnessMaxTurnsError as exc:
        assert "max_total_turns=3" in str(exc)
        assert exc.effective_cap == 3
        assert exc.turn_id == "t1"
        assert exc.visit == 4


def test_graph_traversal_advances_using_runtime_branch_decision():
    scenario = _scenario(
        turns=[
            Turn(
                id="t1",
                text="route me",
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[
                        BranchCase(condition="billing", next="t_billing"),
                        BranchCase(condition="technical", next="t_tech"),
                    ],
                ),
                wait_for_response=False,
            ),
            Turn(id="t_billing", text="billing branch", next="t_end", wait_for_response=False),
            Turn(id="t_tech", text="tech branch", next="t_end", wait_for_response=False),
            Turn(id="t_fallback", text="fallback branch", next="t_end", wait_for_response=False),
            Turn(id="t_end", text="end", wait_for_response=False),
        ]
    )

    traversal = GraphTraversal(scenario, max_total_turns_hard_cap=50)
    step_1 = traversal.consume_current()
    assert step_1.turn.id == "t1"
    assert step_1.visit == 1
    traversal.advance("technical")

    step_2 = traversal.consume_current()
    assert step_2.turn.id == "t_tech"
    traversal.advance("default")
    step_3 = traversal.consume_current()
    assert step_3.turn.id == "t_end"
    traversal.advance("default")
    assert traversal.has_next() is False


def test_build_turn_sequence_includes_wait_block_in_linear_order():
    scenario = _scenario(
        turns=[
            Turn(id="t1", text="one", wait_for_response=False),
            WaitBlock(id="t_wait", wait_s=2.5),
            Turn(id="t2", text="two", wait_for_response=False),
        ]
    )

    sequence = build_turn_sequence(scenario, max_total_turns_hard_cap=50)
    assert [turn.id for turn in sequence] == ["t1", "t_wait", "t2"]


def test_graph_traversal_routes_time_route_block_by_window_label():
    scenario = _scenario(
        turns=[
            TimeRouteBlock(
                id="t_route",
                timezone="UTC",
                windows=[
                    {
                        "label": "business_hours",
                        "start": "09:00",
                        "end": "17:00",
                        "next": "t_business",
                    }
                ],
                default="t_default",
            ),
            Turn(id="t_business", text="business", wait_for_response=False),
            Turn(id="t_default", text="default", wait_for_response=False),
        ]
    )

    traversal = GraphTraversal(scenario, max_total_turns_hard_cap=50)
    step_1 = traversal.consume_current()
    assert step_1.turn.id == "t_route"
    traversal.advance("business_hours")

    step_2 = traversal.consume_current()
    assert step_2.turn.id == "t_business"


def test_graph_traversal_time_route_unknown_label_falls_back_to_default():
    scenario = _scenario(
        turns=[
            TimeRouteBlock(
                id="t_route",
                timezone="UTC",
                windows=[
                    {
                        "label": "business_hours",
                        "start": "09:00",
                        "end": "17:00",
                        "next": "t_business",
                    }
                ],
                default="t_default",
            ),
            Turn(id="t_business", text="business", wait_for_response=False),
            Turn(id="t_default", text="default", wait_for_response=False),
        ]
    )

    traversal = GraphTraversal(scenario, max_total_turns_hard_cap=50)
    traversal.consume_current()
    traversal.advance("not-a-real-window")

    step_2 = traversal.consume_current()
    assert step_2.turn.id == "t_default"
