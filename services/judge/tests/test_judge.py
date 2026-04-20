"""Tests for judge_conversation() orchestration behavior."""

from datetime import UTC, datetime

import pytest
from botcheck_scenarios import (
    BotConfig,
    ConversationTurn,
    DeterministicChecks,
    ScenarioDefinition,
    ScenarioType,
    Turn,
)

from botcheck_judge.judge import judge_conversation


def _scenario(scenario_type: ScenarioType) -> ScenarioDefinition:
    return ScenarioDefinition(
        id="test-scenario",
        name="Test Scenario",
        type=scenario_type,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[Turn(id="t1", text="hello")],
    )


def _conversation() -> list[ConversationTurn]:
    return [
        ConversationTurn(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="Hello",
            audio_start_ms=0,
            audio_end_ms=500,
        ),
        ConversationTurn(
            turn_id="t2",
            turn_number=2,
            speaker="bot",
            text="Hi there, how can I help?",
            audio_start_ms=700,
            audio_end_ms=1400,
        ),
    ]


@pytest.mark.asyncio
async def test_multi_sample_adversarial_aggregates_minimum_score(monkeypatch):
    samples = [
        {"scores": {"jailbreak": {"score": 0.90, "reasoning": "s1", "findings": []}}},
        {"scores": {"jailbreak": {"score": 0.20, "reasoning": "s2", "findings": []}}},
        {"scores": {"jailbreak": {"score": 0.70, "reasoning": "s3", "findings": []}}},
    ]
    calls = {"count": 0}

    async def fake_score_with_llm(**kwargs):
        idx = calls["count"]
        calls["count"] += 1
        return samples[idx], {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    report, _ = await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        anthropic_client=object(),  # not used by fake scorer
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        multi_sample_judge=True,
        multi_sample_n=3,
    )

    assert calls["count"] == 3
    assert report.scores["jailbreak"].score == 0.20


@pytest.mark.asyncio
async def test_multi_sample_disabled_calls_llm_once(monkeypatch):
    calls = {"count": 0}

    async def fake_score_with_llm(**kwargs):
        calls["count"] += 1
        return {"scores": {"jailbreak": {"score": 0.8, "reasoning": "ok", "findings": []}}}, {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        multi_sample_judge=False,
        multi_sample_n=3,
    )

    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_multi_sample_only_applies_to_adversarial(monkeypatch):
    calls = {"count": 0}

    async def fake_score_with_llm(**kwargs):
        calls["count"] += 1
        return {"scores": {"routing": {"score": 0.9, "reasoning": "ok", "findings": []}}}, {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.GOLDEN_PATH),
        conversation=_conversation(),
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        multi_sample_judge=True,
        multi_sample_n=3,
    )

    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_multi_sample_treats_absent_dimension_as_zero(monkeypatch):
    """If a sample omits a dimension, aggregate_scores_min should pessimistically score 0.0."""
    samples = [
        # sample 1: jailbreak present and high
        {"scores": {"jailbreak": {"score": 0.95, "reasoning": "ok", "findings": []}}},
        # sample 2: jailbreak absent (partial LLM response / parse issue)
        {"scores": {"disclosure": {"score": 1.0, "reasoning": "ok", "findings": []}}},
        # sample 3: jailbreak present and high
        {"scores": {"jailbreak": {"score": 0.90, "reasoning": "ok", "findings": []}}},
    ]
    calls = {"count": 0}

    async def fake_score_with_llm(**kwargs):
        idx = calls["count"]
        calls["count"] += 1
        return samples[idx], {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    report, _ = await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        multi_sample_judge=True,
        multi_sample_n=3,
    )

    # The missing jailbreak in sample 2 should force the merged score to 0.0,
    # not the 0.90 min of the two samples that had it.
    assert report.scores["jailbreak"].score == 0.0


@pytest.mark.asyncio
async def test_judge_passes_tool_context_to_llm(monkeypatch):
    captured: dict = {}

    async def fake_score_with_llm(**kwargs):
        captured["tool_context"] = kwargs.get("tool_context")
        return {"scores": {"jailbreak": {"score": 0.8, "reasoning": "ok", "findings": []}}}, {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    tool_context = [
        {
            "tool_name": "lookup_customer",
            "turn_number": 2,
            "status": "success",
            "request": {"account_id": "abc"},
            "response": {"customer_tier": "gold"},
        }
    ]

    await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        tool_context=tool_context,
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert captured["tool_context"] == tool_context


@pytest.mark.asyncio
async def test_judge_passes_taken_path_steps_to_deterministic_and_llm(monkeypatch):
    captured: dict = {}

    def fake_run_deterministic_checks(*args, **kwargs):
        captured["det_taken_path_steps"] = kwargs.get("taken_path_steps")
        return DeterministicChecks()

    async def fake_score_with_llm(**kwargs):
        captured["llm_taken_path_steps"] = kwargs.get("taken_path_steps")
        return {
            "scores": {
                "jailbreak": {
                    "score": 1.0,
                    "reasoning": "ok",
                    "findings": [],
                }
            }
        }, {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr(
        "botcheck_judge.judge.run_deterministic_checks",
        fake_run_deterministic_checks,
    )
    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    taken_path_steps = [
        {"turn_id": "t1", "visit": 1, "turn_number": 1},
        {"turn_id": "t2", "visit": 1, "turn_number": 2},
    ]
    await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        taken_path_steps=taken_path_steps,
    )

    assert captured["det_taken_path_steps"] == taken_path_steps
    assert captured["llm_taken_path_steps"] == taken_path_steps


@pytest.mark.asyncio
async def test_judge_passes_ai_context_to_llm(monkeypatch):
    captured: dict = {}

    async def fake_score_with_llm(**kwargs):
        captured["ai_context"] = kwargs.get("ai_context")
        return {
            "scores": {
                "jailbreak": {
                    "score": 1.0,
                    "reasoning": "ok",
                    "findings": [],
                }
            }
        }, {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("botcheck_judge.judge.score_with_llm", fake_score_with_llm)

    ai_context = {
        "dataset_input": "Caller wants a condo in Queens.",
        "expected_output": "Recommend options and avoid booking a tour.",
        "persona_id": "persona_real_estate_1",
    }

    await judge_conversation(
        run_id="run_test",
        scenario=_scenario(ScenarioType.ADVERSARIAL),
        conversation=_conversation(),
        anthropic_client=object(),
        model="test-model",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ai_context=ai_context,
    )

    assert captured["ai_context"] == ai_context
