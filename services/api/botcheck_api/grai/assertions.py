from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import anthropic


_REFUSAL_MARKERS = (
    "i can't",
    "i cannot",
    "i'm sorry",
    "sorry,",
    "unable to",
    "i won't",
    "cannot help with",
    "not able to",
)

_LLM_ASSERTION_TYPES = {
    "llm-rubric",
    "factuality",
    "model-graded-closedqa",
    "answer-relevance",
}


@dataclass(slots=True)
class AssertionEvaluation:
    assertion_type: str
    passed: bool
    score: float | None
    threshold: float | None
    weight: float
    raw_value: str | None
    failure_reason: str | None
    latency_ms: int | None
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0


def render_prompt_text(template: str, vars_json: dict[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = vars_json.get(key, "")
        return "" if value is None else str(value)

    return re.sub(r"{{\s*([^{}]+)\s*}}", _replace, template)


def _parse_expected_list(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    try:
        loaded = json.loads(raw_value)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, list):
        return [str(item).strip() for item in loaded if str(item).strip()]
    candidate = raw_value.strip()
    return [candidate] if candidate else []


def _parse_float(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _threshold_passed(*, score: float | None, threshold: float | None, fallback: bool) -> bool:
    if score is None or threshold is None:
        return fallback
    return score >= threshold


def _deterministic_assertion(
    *,
    assertion_type: str,
    raw_value: str | None,
    threshold: float | None,
    weight: float,
    response_text: str,
    latency_ms: int,
) -> AssertionEvaluation:
    normalized = response_text.strip()
    normalized_lower = normalized.lower()
    failure_reason: str | None = None
    score: float | None = None
    passed = False

    if assertion_type == "contains":
        expected = (raw_value or "").strip()
        passed = bool(expected) and expected in normalized
        failure_reason = None if passed else f"response did not contain {expected!r}"
    elif assertion_type == "icontains":
        expected = (raw_value or "").strip().lower()
        passed = bool(expected) and expected in normalized_lower
        failure_reason = None if passed else f"response did not contain {raw_value!r} (case-insensitive)"
    elif assertion_type == "contains-all":
        expected_list = _parse_expected_list(raw_value)
        missing = [item for item in expected_list if item not in normalized]
        passed = bool(expected_list) and not missing
        failure_reason = None if passed else f"response missing required values: {missing}"
    elif assertion_type == "icontains-all":
        expected_list = [item.lower() for item in _parse_expected_list(raw_value)]
        missing = [item for item in expected_list if item not in normalized_lower]
        passed = bool(expected_list) and not missing
        failure_reason = None if passed else f"response missing required values: {missing}"
    elif assertion_type == "contains-any":
        expected_list = _parse_expected_list(raw_value)
        passed = any(item in normalized for item in expected_list)
        failure_reason = None if passed else "response did not contain any expected value"
    elif assertion_type == "icontains-any":
        expected_list = [item.lower() for item in _parse_expected_list(raw_value)]
        passed = any(item in normalized_lower for item in expected_list)
        failure_reason = None if passed else "response did not contain any expected value"
    elif assertion_type == "equals":
        expected = (raw_value or "").strip()
        passed = normalized == expected
        failure_reason = None if passed else f"response {normalized!r} did not equal {expected!r}"
    elif assertion_type == "starts-with":
        expected = (raw_value or "").strip()
        passed = bool(expected) and normalized.startswith(expected)
        failure_reason = None if passed else f"response did not start with {expected!r}"
    elif assertion_type == "regex":
        pattern = (raw_value or "").strip()
        try:
            passed = bool(pattern) and re.search(pattern, normalized) is not None
            failure_reason = None if passed else f"response did not match regex {pattern!r}"
        except re.error as exc:
            passed = False
            failure_reason = f"invalid regex {pattern!r}: {exc}"
    elif assertion_type == "is-json":
        try:
            json.loads(normalized)
            passed = True
            failure_reason = None
        except json.JSONDecodeError as exc:
            passed = False
            failure_reason = f"response was not valid JSON: {exc.msg}"
    elif assertion_type == "word-count":
        expected = _parse_float(raw_value)
        word_count = float(len([word for word in normalized.split() if word.strip()]))
        score = word_count
        if expected is not None:
            passed = int(word_count) == int(expected)
            failure_reason = None if passed else f"word count {int(word_count)} did not equal {int(expected)}"
        else:
            passed = _threshold_passed(score=word_count, threshold=threshold, fallback=word_count > 0)
            failure_reason = None if passed else "word count was below threshold"
    elif assertion_type == "levenshtein":
        expected = (raw_value or "").strip()
        if expected:
            distance = _levenshtein_distance(normalized, expected)
            max_length = max(len(normalized), len(expected), 1)
            score = max(0.0, 1.0 - (distance / max_length))
            passed = _threshold_passed(score=score, threshold=threshold, fallback=distance == 0)
            failure_reason = None if passed else f"similarity {score:.2f} was below threshold"
        else:
            passed = False
            failure_reason = "levenshtein assertion requires an expected value"
    elif assertion_type == "latency":
        limit = _parse_float(raw_value)
        score = float(latency_ms)
        if limit is not None:
            passed = latency_ms <= limit
            failure_reason = None if passed else f"latency {latency_ms}ms exceeded limit {limit}ms"
        else:
            passed = _threshold_passed(score=float(latency_ms), threshold=threshold, fallback=True)
            failure_reason = None if passed else f"latency {latency_ms}ms exceeded threshold"
    elif assertion_type == "is-refusal":
        passed = any(marker in normalized_lower for marker in _REFUSAL_MARKERS)
        failure_reason = None if passed else "response did not look like a refusal"
    else:
        passed = False
        failure_reason = f"unsupported deterministic assertion type: {assertion_type}"

    return AssertionEvaluation(
        assertion_type=assertion_type,
        passed=passed,
        score=score,
        threshold=threshold,
        weight=weight,
        raw_value=raw_value,
        failure_reason=failure_reason,
        latency_ms=latency_ms if assertion_type == "latency" else None,
    )


async def _llm_assertion(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    assertion_type: str,
    raw_value: str | None,
    threshold: float | None,
    weight: float,
    prompt_text: str,
    case_description: str | None,
    vars_json: dict[str, Any],
    response_text: str,
) -> AssertionEvaluation:
    response = await client.messages.create(
        model=model,
        max_tokens=400,
        system=(
            "You are grading one LLM-eval assertion for a chatbot response. "
            "Return only JSON with keys score (0.0-1.0 float) and reasoning (string)."
        ),
        messages=[
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "assertion_type": assertion_type,
                        "expected": raw_value,
                        "threshold": threshold,
                        "prompt_text": prompt_text,
                        "case_description": case_description,
                        "vars": vars_json,
                        "response_text": response_text,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            }
        ],
    )
    if not response.content or not hasattr(response.content[0], "text"):
        raise RuntimeError(
            f"LLM assertion returned unexpected response (stop_reason={response.stop_reason!r})"
        )
    raw = response.content[0].text.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM assertion returned invalid JSON: {exc}") from exc
    score = float(payload.get("score", 0.0))
    reasoning = str(payload.get("reasoning") or "LLM assertion failed")
    passed = score >= (threshold if threshold is not None else 0.5)
    return AssertionEvaluation(
        assertion_type=assertion_type,
        passed=passed,
        score=score,
        threshold=threshold,
        weight=weight,
        raw_value=raw_value,
        failure_reason=None if passed else reasoning,
        latency_ms=None,
        input_tokens=int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0),
        output_tokens=int(getattr(getattr(response, "usage", None), "output_tokens", 0) or 0),
        request_count=1,
    )


async def evaluate_assertion(
    *,
    assertion: dict[str, Any],
    prompt_text: str,
    case_description: str | None,
    vars_json: dict[str, Any],
    response_text: str,
    latency_ms: int,
    anthropic_client: anthropic.AsyncAnthropic | None,
    llm_model: str,
) -> AssertionEvaluation:
    assertion_type = str(assertion.get("assertion_type") or "").strip()
    raw_value = str(assertion["raw_value"]) if assertion.get("raw_value") is not None else None
    threshold = float(assertion["threshold"]) if assertion.get("threshold") is not None else None
    weight = float(assertion.get("weight") or 1.0)

    if assertion_type in _LLM_ASSERTION_TYPES:
        if anthropic_client is None:
            return AssertionEvaluation(
                assertion_type=assertion_type,
                passed=False,
                score=None,
                threshold=threshold,
                weight=weight,
                raw_value=raw_value,
                failure_reason="LLM assertion unavailable: ANTHROPIC_API_KEY not configured",
                latency_ms=None,
            )
        return await _llm_assertion(
            client=anthropic_client,
            model=llm_model,
            assertion_type=assertion_type,
            raw_value=raw_value,
            threshold=threshold,
            weight=weight,
            prompt_text=prompt_text,
            case_description=case_description,
            vars_json=vars_json,
            response_text=response_text,
        )

    return _deterministic_assertion(
        assertion_type=assertion_type,
        raw_value=raw_value,
        threshold=threshold,
        weight=weight,
        response_text=response_text,
        latency_ms=latency_ms,
    )
