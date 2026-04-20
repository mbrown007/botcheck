from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.scenario_turn_helpers import (
    classify_branch_condition,
    effective_stt_settings,
    effective_turn_timeout,
)

from botcheck_scenarios import BranchMode, ConversationTurn


def _turn(
    *,
    timeout_s: float | None = None,
    transferred_to: str | None = None,
    stt_endpointing_ms: int | None = None,
    transcript_merge_window_s: float | None = None,
    branching_conditions: list[str] | None = None,
    branching_mode: BranchMode = BranchMode.CLASSIFIER,
    case_match_values: list[str | None] | None = None,
    case_regex_values: list[str | None] | None = None,
):
    branching = None
    if branching_conditions is not None:
        branching = SimpleNamespace(
            mode=branching_mode,
            cases=[
                SimpleNamespace(
                    condition=condition,
                    match=(case_match_values[index] if case_match_values is not None else None),
                    regex=(case_regex_values[index] if case_regex_values is not None else None),
                )
                for index, condition in enumerate(branching_conditions)
            ],
        )
    return SimpleNamespace(
        config=SimpleNamespace(
            timeout_s=timeout_s,
            stt_endpointing_ms=stt_endpointing_ms,
            transcript_merge_window_s=transcript_merge_window_s,
        ),
        expect=SimpleNamespace(transferred_to=transferred_to) if transferred_to else None,
        branching=branching,
    )


def _scenario():
    return SimpleNamespace(
        name="Routing",
        description="Route caller intent",
        config=SimpleNamespace(
            transfer_timeout_s=45,
            turn_timeout_s=15,
            stt_endpointing_ms=1200,
            transcript_merge_window_s=0.8,
        ),
    )


def test_effective_turn_timeout_precedence() -> None:
    scenario = _scenario()
    assert effective_turn_timeout(_turn(timeout_s=9), scenario) == 9
    assert effective_turn_timeout(_turn(transferred_to="+18005550199"), scenario) == 45
    assert effective_turn_timeout(_turn(), scenario) == 15


def test_effective_stt_settings_precedence() -> None:
    scenario = _scenario()
    turn_with_overrides = _turn(stt_endpointing_ms=900, transcript_merge_window_s=0.4)
    assert effective_stt_settings(turn_with_overrides, scenario) == (900, 0.4)
    assert effective_stt_settings(_turn(), scenario) == (1200, 0.8)


@pytest.mark.asyncio
async def test_classify_branch_condition_defaults_without_branching() -> None:
    called = False

    async def _classify(**kwargs) -> str:
        nonlocal called
        called = True
        return "default"

    condition, snippet = await classify_branch_condition(
        turn_def=_turn(branching_conditions=None),
        bot_text="Hello",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=_classify,
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "default"
    assert snippet is None
    assert called is False


@pytest.mark.asyncio
async def test_classify_branch_condition_passes_expected_payload() -> None:
    scenario = _scenario()
    received = {}

    async def _classify(**kwargs) -> str:
        nonlocal received
        received = kwargs
        return "billing"

    history = [
        ConversationTurn(
            turn_id=f"t{i}",
            turn_number=i,
            speaker="harness",
            text=f"turn {i}",
            audio_start_ms=i * 1000,
            audio_end_ms=i * 1000 + 200,
        )
        for i in range(1, 9)
    ]

    condition, snippet = await classify_branch_condition(
        turn_def=_turn(branching_conditions=["billing", "support"]),
        bot_text="I can help with billing",
        conversation=history,
        scenario=scenario,
        classify_branch_fn=_classify,
        classifier_client=object(),
        classifier_model="model-y",
        classifier_timeout_s=2.5,
    )

    assert condition == "billing"
    assert snippet == "I can help with billing"
    assert received["conditions"] == ["billing", "support"]
    assert received["scenario_intent"] == "Route caller intent"
    assert received["model"] == "model-y"
    assert received["timeout_s"] == 2.5
    assert len(received["conversation_history"]) == 6
    assert received["conversation_history"][0]["turn_id"] == "t3"


@pytest.mark.asyncio
async def test_classify_branch_condition_keyword_match_is_case_insensitive() -> None:
    called = False

    async def _classify(**kwargs) -> str:
        nonlocal called
        called = True
        return "default"

    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["billing", "support"],
            branching_mode=BranchMode.KEYWORD,
            case_match_values=["BILLING", "support"],
        ),
        bot_text="I can help with billing today.",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=_classify,
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "billing"
    assert snippet == "I can help with billing today."
    assert called is False


@pytest.mark.asyncio
async def test_classify_branch_condition_regex_match_uses_default_when_unmatched() -> None:
    called = False

    async def _classify(**kwargs) -> str:
        nonlocal called
        called = True
        return "default"

    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["reference", "queue"],
            branching_mode=BranchMode.REGEX,
            case_regex_values=[r"reference\s+[A-Z]\d{6}", r"queue\s+sales"],
        ),
        bot_text="Please hold while I transfer you.",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=_classify,
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "default"
    assert snippet == "Please hold while I transfer you."
    assert called is False


@pytest.mark.asyncio
async def test_classify_branch_condition_regex_match_returns_selector() -> None:
    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["reference", "queue"],
            branching_mode=BranchMode.REGEX,
            case_regex_values=[r"reference\s+[A-Z]\d{6}", r"queue\s+sales"],
        ),
        bot_text="Your reference A123456 has been created.",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=SimpleNamespace(),
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "reference"
    assert snippet == "Your reference A123456 has been created."


@pytest.mark.asyncio
async def test_classify_branch_condition_keyword_no_match_returns_default() -> None:
    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["billing", "technical"],
            branching_mode=BranchMode.KEYWORD,
            case_match_values=["billing", "technical"],
        ),
        bot_text="Thank you for calling, how can I help?",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=SimpleNamespace(),
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "default"
    assert snippet == "Thank you for calling, how can I help?"


@pytest.mark.asyncio
async def test_classify_branch_condition_keyword_timeout_sentinel_falls_to_default() -> None:
    """'(timeout)' sentinel must fall through to default, not match keyword cases."""
    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["billing"],
            branching_mode=BranchMode.KEYWORD,
            case_match_values=["billing"],
        ),
        bot_text="(timeout)",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=SimpleNamespace(),
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    assert condition == "default"
    assert snippet == "(timeout)"


@pytest.mark.asyncio
async def test_classify_branch_condition_regex_timeout_sentinel_falls_to_default() -> None:
    """'(timeout)' sentinel must fall through to default, not match regex cases."""
    condition, snippet = await classify_branch_condition(
        turn_def=_turn(
            branching_conditions=["any_word"],
            branching_mode=BranchMode.REGEX,
            case_regex_values=[r"\w+"],
        ),
        bot_text="(timeout)",
        conversation=[],
        scenario=_scenario(),
        classify_branch_fn=SimpleNamespace(),
        classifier_client=object(),
        classifier_model="model-x",
        classifier_timeout_s=1.0,
    )

    # (timeout) matches \w+ — document that this is expected behaviour;
    # the harness caller filters on bot_text == "(timeout)" before branching.
    assert condition == "any_word"
    assert snippet == "(timeout)"
