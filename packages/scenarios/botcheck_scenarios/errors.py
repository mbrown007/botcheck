"""Shared run error taxonomy and judge-failure classification helpers."""

from __future__ import annotations

import json
from enum import Enum

from pydantic import ValidationError


class ErrorCode(str, Enum):
    HARNESS_TIMEOUT = "harness_timeout"
    AI_CALLER_UNAVAILABLE = "ai_caller_unavailable"
    REAPER_FORCE_CLOSED = "reaper_force_closed"
    OPERATOR_ABORTED = "operator_aborted"
    JUDGE_LLM_FAILURE = "judge_llm_failure"
    JUDGE_PARSE_FAILURE = "judge_parse_failure"
    TELEPHONY_FAILURE = "telephony_failure"
    INTERNAL = "internal"


def classify_judge_error(exc: Exception) -> ErrorCode:
    if isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError)):
        return ErrorCode.JUDGE_PARSE_FAILURE
    return ErrorCode.JUDGE_LLM_FAILURE
