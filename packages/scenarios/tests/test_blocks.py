"""Tests for normalized scenario blocks and legacy turn loading."""

import pytest
from pydantic import ValidationError

from botcheck_scenarios import (
    AdversarialTechnique,
    BotListenBlock,
    HangupBlock,
    HarnessPromptBlock,
    TimeRouteBlock,
    WaitBlock,
    load_block,
    normalize_legacy_turn_to_block,
)


def test_load_block_validates_kind_tagged_harness_prompt() -> None:
    block = load_block(
        {
            "kind": "harness_prompt",
            "id": "t1",
            "content": {"text": "Hello"},
            "listen": False,
        }
    )
    assert isinstance(block, HarnessPromptBlock)
    assert block.content.text == "Hello"
    assert block.listen is False


def test_normalize_legacy_text_turn_to_harness_prompt() -> None:
    block = normalize_legacy_turn_to_block(
        {
            "id": "t1",
            "text": "Hello there",
            "wait_for_response": False,
        }
    )
    assert isinstance(block, HarnessPromptBlock)
    assert block.content.text == "Hello there"
    assert block.listen is False


def test_normalize_legacy_bot_turn_preserves_adversarial_fields() -> None:
    block = normalize_legacy_turn_to_block(
        {
            "id": "t_bot",
            "speaker": "bot",
            "expect": {"intent_recognized": True},
            "adversarial": True,
            "technique": "prompt_injection",
        }
    )
    assert isinstance(block, BotListenBlock)
    assert block.adversarial is True
    assert block.technique == AdversarialTechnique.PROMPT_INJECTION
    assert block.expect is not None
    assert block.expect.intent_recognized is True


def test_normalize_legacy_hangup_raw_mapping_before_turn_validation() -> None:
    block = normalize_legacy_turn_to_block(
        {
            "id": "t_end",
            "builder_block": "hangup",
            "wait_for_response": False,
            "silence_s": None,
        }
    )
    assert isinstance(block, HangupBlock)
    assert block.id == "t_end"


def test_load_block_missing_kind_uses_legacy_normalizer() -> None:
    block = load_block(
        {
            "id": "t1",
            "text": "Hello",
        }
    )
    assert isinstance(block, HarnessPromptBlock)


def test_load_block_validates_kind_tagged_wait_block() -> None:
    block = load_block(
        {
            "kind": "wait",
            "id": "t_wait",
            "wait_s": 2.5,
            "next": "t2",
        }
    )
    assert isinstance(block, WaitBlock)
    assert block.wait_s == 2.5
    assert block.next == "t2"


def test_wait_block_rejects_zero_duration() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        WaitBlock(
            id="t_wait",
            wait_s=0.0,
        )


def test_load_block_validates_kind_tagged_time_route_block() -> None:
    block = load_block(
        {
            "kind": "time_route",
            "id": "t_route",
            "timezone": "Europe/London",
            "windows": [
                {
                    "label": "business_hours",
                    "start": "08:00",
                    "end": "16:00",
                    "next": "t_business",
                }
            ],
            "default": "t_default",
        }
    )
    assert isinstance(block, TimeRouteBlock)
    assert block.timezone == "Europe/London"
    assert block.windows[0].label == "business_hours"


def test_time_route_block_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError, match="Invalid time_route timezone"):
        TimeRouteBlock(
            id="t_route",
            timezone="Mars/Olympus",
            windows=[
                {
                    "label": "business_hours",
                    "start": "08:00",
                    "end": "16:00",
                    "next": "t_business",
                }
            ],
            default="t_default",
        )


def test_time_route_block_rejects_duplicate_labels() -> None:
    with pytest.raises(ValidationError, match="labels must be unique"):
        TimeRouteBlock(
            id="t_route",
            timezone="UTC",
            windows=[
                {
                    "label": "business_hours",
                    "start": "08:00",
                    "end": "16:00",
                    "next": "t_business",
                },
                {
                    "label": "business_hours",
                    "start": "16:00",
                    "end": "22:00",
                    "next": "t_evening",
                },
            ],
            default="t_default",
        )


def test_harness_prompt_requires_exactly_one_content_field() -> None:
    with pytest.raises(ValidationError, match="exactly one content field required"):
        HarnessPromptBlock(
            id="t1",
            content={"text": "Hello", "dtmf": "1"},
        )


def test_harness_prompt_rejects_adversarial_without_technique() -> None:
    with pytest.raises(ValidationError, match="technique"):
        HarnessPromptBlock(
            id="t1",
            content={"text": "Hello"},
            adversarial=True,
        )


def test_bot_listen_rejects_adversarial_without_technique() -> None:
    with pytest.raises(ValidationError, match="technique"):
        BotListenBlock(
            id="t1",
            adversarial=True,
        )


def test_normalize_invalid_legacy_turn_without_content_raises() -> None:
    with pytest.raises(ValidationError, match="text, audio_file"):
        normalize_legacy_turn_to_block({"id": "t1"})


def test_normalize_legacy_turn_empty_text_with_silence_uses_silence() -> None:
    """Old scenarios with text: "" + silence_s both set must not fail the
    HarnessPromptBlock 'exactly one content field' check.  Empty text is
    treated as absent so that silence_s is the sole content field."""
    block = normalize_legacy_turn_to_block(
        {
            "id": "t_listen",
            "speaker": "harness",
            "text": "",
            "silence_s": 2,
            "wait_for_response": True,
            "next": "t_next",
        }
    )
    assert isinstance(block, HarnessPromptBlock)
    assert block.content.silence_s == 2.0
    assert block.content.text is None


def test_normalize_legacy_turn_whitespace_text_with_silence_uses_silence() -> None:
    """Whitespace-only text is also treated as absent."""
    block = normalize_legacy_turn_to_block(
        {
            "id": "t1",
            "speaker": "harness",
            "text": "   ",
            "silence_s": 1.5,
            "wait_for_response": False,
        }
    )
    assert isinstance(block, HarnessPromptBlock)
    assert block.content.silence_s == 1.5
    assert block.content.text is None
