from __future__ import annotations

import pytest

from botcheck_api.grai.assertions import evaluate_assertion, render_prompt_text


def test_render_prompt_text_substitutes_vars() -> None:
    rendered = render_prompt_text(
        "Answer clearly: {{ question }} for {{customer}}.",
        {"question": "What is the refund policy?", "customer": "Acme"},
    )

    assert rendered == "Answer clearly: What is the refund policy? for Acme."


@pytest.mark.asyncio
async def test_evaluate_assertion_contains_all_passes() -> None:
    evaluation = await evaluate_assertion(
        assertion={
            "assertion_type": "contains-all",
            "raw_value": '["refund", "policy"]',
            "threshold": None,
            "weight": 1.0,
        },
        prompt_text="Answer: {{question}}",
        case_description="Refund policy",
        vars_json={"question": "What is the refund policy?"},
        response_text="Our refund policy allows a refund within 30 days.",
        latency_ms=120,
        anthropic_client=None,
        llm_model="claude-sonnet-4-6",
    )

    assert evaluation.passed is True
    assert evaluation.failure_reason is None


@pytest.mark.asyncio
async def test_evaluate_assertion_llm_unavailable_fails_cleanly() -> None:
    evaluation = await evaluate_assertion(
        assertion={
            "assertion_type": "llm-rubric",
            "raw_value": "Did the answer address billing clearly?",
            "threshold": 0.8,
            "weight": 1.0,
        },
        prompt_text="Answer: {{question}}",
        case_description="Billing clarity",
        vars_json={"question": "Explain my invoice"},
        response_text="Your invoice shows the monthly platform charge.",
        latency_ms=90,
        anthropic_client=None,
        llm_model="claude-sonnet-4-6",
    )

    assert evaluation.passed is False
    assert evaluation.failure_reason == "LLM assertion unavailable: ANTHROPIC_API_KEY not configured"
