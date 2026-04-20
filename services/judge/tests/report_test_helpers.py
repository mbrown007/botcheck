"""Shared helpers for assemble_report() tests."""

from datetime import UTC, datetime, timedelta

from botcheck_scenarios import (
    BotConfig,
    ConversationTurn,
    DeterministicChecks,
    ScenarioDefinition,
    ScenarioType,
    Turn,
)

from botcheck_judge.scoring.report import assemble_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_scenario(**overrides) -> ScenarioDefinition:
    base = dict(
        id="test-scenario",
        name="Test",
        type=ScenarioType.ADVERSARIAL,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[Turn(id="t1", text="Hello.")],
    )
    base.update(overrides)
    return ScenarioDefinition(**base)


def make_turn(turn_id="t1", speaker="harness", text="Hello.") -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        turn_number=1,
        speaker=speaker,
        text=text,
        audio_start_ms=0,
        audio_end_ms=1000,
    )


def ts(offset_s: float = 0) -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_s)


def passing_llm_scores(*, jailbreak=1.0, disclosure=1.0) -> dict:
    return {
        "scores": {
            "jailbreak": {
                "score": jailbreak,
                "reasoning": "Bot correctly refused.",
                "findings": [],
            },
            "disclosure": {
                "score": disclosure,
                "reasoning": "No disclosure.",
                "findings": [],
            },
        }
    }


def call_assemble(**kwargs) -> object:
    defaults = dict(
        run_id="run_test01",
        scenario=make_scenario(),
        scenario_version_hash="abc123",
        tenant_id="acme",
        conversation=[make_turn()],
        deterministic=DeterministicChecks(),
        llm_scores=passing_llm_scores(),
        started_at=ts(0),
        completed_at=ts(30),
        judge_model="claude-opus-4-6",
        judge_version="0.1",
    )
    defaults.update(kwargs)
    return assemble_report(**defaults)
