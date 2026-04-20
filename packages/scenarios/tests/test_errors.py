"""Tests for shared error taxonomy and judge error classification."""

import json

import pytest
from pydantic import ValidationError

from botcheck_scenarios import ErrorCode, classify_judge_error
from botcheck_scenarios.evidence import ConversationTurn


def test_error_code_enum_values_are_stable():
    assert ErrorCode.HARNESS_TIMEOUT.value == "harness_timeout"
    assert ErrorCode.AI_CALLER_UNAVAILABLE.value == "ai_caller_unavailable"
    assert ErrorCode.REAPER_FORCE_CLOSED.value == "reaper_force_closed"
    assert ErrorCode.JUDGE_LLM_FAILURE.value == "judge_llm_failure"
    assert ErrorCode.JUDGE_PARSE_FAILURE.value == "judge_parse_failure"
    assert ErrorCode.TELEPHONY_FAILURE.value == "telephony_failure"
    assert ErrorCode.INTERNAL.value == "internal"


def test_classify_json_decode_error_as_parse_failure():
    exc = json.JSONDecodeError("bad json", "{}", 0)
    assert classify_judge_error(exc) == ErrorCode.JUDGE_PARSE_FAILURE


def test_classify_validation_error_as_parse_failure():
    with pytest.raises(ValidationError) as exc_info:
        ConversationTurn(turn_id="t1")
    assert classify_judge_error(exc_info.value) == ErrorCode.JUDGE_PARSE_FAILURE


def test_classify_runtime_error_as_llm_failure():
    assert (
        classify_judge_error(RuntimeError("upstream model call failed"))
        == ErrorCode.JUDGE_LLM_FAILURE
    )
