"""Shared fixtures/helpers for DSL tests."""

from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn


def minimal_scenario(**overrides) -> ScenarioDefinition:
    base = dict(
        id="test-scenario",
        name="Test Scenario",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[Turn(id="t1", text="Hello.")],
    )
    base.update(overrides)
    return ScenarioDefinition(**base)
