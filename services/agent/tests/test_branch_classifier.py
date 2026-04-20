"""Tests for Phase 5 branch classifier fallback and metrics semantics."""

from __future__ import annotations

import asyncio

import pytest

from src import branch_classifier


class _LabelCounter:
    def __init__(self) -> None:
        self.value = 0
        self.by_label: dict[str, int] = {}

    def labels(self, **kwargs):
        outcome = str(kwargs.get("outcome", "unknown"))
        parent = self

        class _Child:
            def inc(self, amount: float = 1.0) -> None:
                delta = int(amount)
                parent.value += delta
                parent.by_label[outcome] = parent.by_label.get(outcome, 0) + delta

        return _Child()

    def inc(self, amount: float = 1.0) -> None:
        self.value += int(amount)


class _LabelHistogram:
    def __init__(self) -> None:
        self.by_label: dict[str, list[float]] = {}

    def labels(self, **kwargs):
        outcome = str(kwargs.get("outcome", "unknown"))
        parent = self

        class _Child:
            def observe(self, value: float) -> None:
                parent.by_label.setdefault(outcome, []).append(float(value))

        return _Child()


class _SuccessClient:
    async def choose_condition(self, **_kwargs) -> str:
        return " TECHNICAL "


class _TimeoutClient:
    async def choose_condition(self, **_kwargs) -> str:
        await asyncio.sleep(0.05)
        return "billing"


class _ErrorClient:
    async def choose_condition(self, **_kwargs) -> str:
        raise RuntimeError("classifier unavailable")


@pytest.fixture
def fake_metrics(monkeypatch):
    calls = _LabelCounter()
    latency = _LabelHistogram()
    monkeypatch.setattr(branch_classifier, "BRANCH_CLASSIFIER_CALLS_TOTAL", calls)
    monkeypatch.setattr(branch_classifier, "BRANCH_CLASSIFIER_LATENCY_SECONDS", latency)
    return {
        "calls": calls,
        "latency": latency,
    }


@pytest.mark.asyncio
async def test_classify_branch_success_normalizes_choice(fake_metrics):
    chosen = await branch_classifier.classify_branch(
        bot_response="Let's go technical.",
        conditions=["billing", "technical"],
        conversation_history=[{"speaker": "bot", "text": "Let's go technical."}],
        scenario_intent="Route to support lane.",
        client=_SuccessClient(),
        model="claude-3-5-haiku-latest",
        timeout_s=0.5,
    )
    assert chosen == "technical"
    assert fake_metrics["calls"].by_label.get("success") == 1
    assert len(fake_metrics["latency"].by_label.get("success", [])) == 1


@pytest.mark.asyncio
async def test_classify_branch_timeout_falls_back_to_default(fake_metrics):
    chosen = await branch_classifier.classify_branch(
        bot_response="anything",
        conditions=["billing", "technical"],
        conversation_history=[],
        scenario_intent="Route to support lane.",
        client=_TimeoutClient(),
        model="claude-3-5-haiku-latest",
        timeout_s=0.01,
    )
    assert chosen == "default"
    assert fake_metrics["calls"].by_label.get("timeout") == 1
    assert len(fake_metrics["latency"].by_label.get("timeout", [])) == 1


@pytest.mark.asyncio
async def test_classify_branch_error_falls_back_to_default(fake_metrics):
    chosen = await branch_classifier.classify_branch(
        bot_response="anything",
        conditions=["billing", "technical"],
        conversation_history=[],
        scenario_intent="Route to support lane.",
        client=_ErrorClient(),
        model="claude-3-5-haiku-latest",
        timeout_s=0.1,
    )
    assert chosen == "default"
    assert fake_metrics["calls"].by_label.get("error") == 1
    assert len(fake_metrics["latency"].by_label.get("error", [])) == 1


@pytest.mark.asyncio
async def test_classify_branch_empty_conditions_returns_default_without_client_call(fake_metrics):
    class _ShouldNotCall:
        async def choose_condition(self, **_kwargs) -> str:
            raise AssertionError("choose_condition should not be called for empty conditions")

    chosen = await branch_classifier.classify_branch(
        bot_response="anything",
        conditions=[],
        conversation_history=[],
        scenario_intent="Route to support lane.",
        client=_ShouldNotCall(),
        model="claude-3-5-haiku-latest",
        timeout_s=0.1,
    )
    assert chosen == "default"
    assert fake_metrics["calls"].value == 0


@pytest.mark.asyncio
async def test_heuristic_client_unmatched_response_returns_default(fake_metrics):
    client = branch_classifier.HeuristicBranchClassifierClient()
    chosen = await branch_classifier.classify_branch(
        bot_response="I can help with mortgage refinancing.",
        conditions=["billing support", "technical support"],
        conversation_history=[],
        scenario_intent="Route to support lane.",
        client=client,
        model="claude-3-5-haiku-latest",
        timeout_s=0.1,
    )
    assert chosen == "default"
    assert fake_metrics["calls"].by_label.get("success") == 1
