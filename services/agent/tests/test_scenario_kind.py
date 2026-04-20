from __future__ import annotations

from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn

from src.scenario_kind import AI_RUNTIME_TAG, materialize_runtime_scenario


def _base_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-base",
        name="Base",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@example.com"),
        turns=[
            Turn(id="t1", text="hello"),
            Turn(id="t2", text="follow up"),
        ],
    )


def test_materialize_runtime_scenario_graph_passthrough():
    scenario = _base_scenario()
    out = materialize_runtime_scenario(
        scenario=scenario,
        metadata={"scenario_kind": "graph"},
    )
    assert out == scenario
    assert [turn.id for turn in out.turns] == ["t1", "t2"]


def test_materialize_runtime_scenario_ai_rewrites_turns_from_dispatch_context():
    scenario = _base_scenario()
    out = materialize_runtime_scenario(
        scenario=scenario,
        metadata={
            "scenario_kind": "ai",
            "ai_dataset_input": "I need help booking an appointment tomorrow.",
        },
    )
    assert len(out.turns) == 1
    assert out.turns[0].id == "ai_record_input"
    assert out.turns[0].kind == "harness_prompt"
    assert out.turns[0].content.text == "I need help booking an appointment tomorrow."
    assert out.turns[0].listen is True
    assert AI_RUNTIME_TAG in out.tags


def test_materialize_runtime_scenario_ai_requires_dataset_input():
    scenario = _base_scenario()
    try:
        materialize_runtime_scenario(
            scenario=scenario,
            metadata={"scenario_kind": "ai"},
        )
    except ValueError as exc:
        assert "ai_dataset_input" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing ai_dataset_input")
