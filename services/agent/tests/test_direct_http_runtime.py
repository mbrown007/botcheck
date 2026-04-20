from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn

from src.direct_http_runtime import execute_direct_http_ai_loop
from src.scenario_kind import AI_RUNTIME_TAG


class _MetricObserver:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float | None]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {key: str(value) for key, value in kwargs.items()}
        return self

    def inc(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))

    def observe(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def respond(self, *, prompt: str, conversation, session_id: str, request_context=None):
        del prompt, conversation, session_id, request_context
        return SimpleNamespace(text=self._responses.pop(0), latency_ms=1)


def _settings(**overrides):
    defaults = {
        "max_total_turns_hard_cap": 50,
        "ai_caller_use_llm": True,
        "ai_caller_model": "gpt-4o-mini",
        "ai_caller_timeout_s": 4.0,
        "ai_caller_api_base_url": "https://api.openai.com/v1",
        "ai_caller_max_context_turns": 8,
        "openai_api_key": "sk-test",
        "ai_voice_fast_ack_enabled": True,
        "ai_voice_fast_ack_trigger_s": 0.01,
    }
    defaults.update(overrides)
    return type("S", (), defaults)()


def _ai_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="direct-http-ai",
        name="Direct HTTP AI",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="https://bot.internal/respond"),
        tags=[AI_RUNTIME_TAG],
        turns=[Turn(id="ai_record_input", text="I need help with billing.", wait_for_response=True)],
    )


@pytest.mark.asyncio
async def test_execute_direct_http_ai_loop_uses_fast_ack_source_for_slow_initial_llm(monkeypatch) -> None:
    reply_latency = _MetricObserver()
    fast_ack_metric = _MetricObserver()

    async def _slow_generator(**_kwargs):
        await asyncio.sleep(999)
        return "This should never be spoken."

    monkeypatch.setattr("src.direct_http_runtime.AI_CALLER_REPLY_LATENCY_SECONDS", reply_latency)
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)

    conversation, turn_number = await execute_direct_http_ai_loop(
        client=_FakeClient(
            responses=[
                "Hello, thanks for calling. How can I help today?",
                "Thanks for calling. Goodbye!",
            ]
        ),
        scenario=_ai_scenario(),
        run_id="run-direct-http-fast-ack",
        settings_obj=_settings(),
        report_turn_fn=AsyncMock(),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Resolve the billing question.",
        },
        ai_caller_generate_fn=_slow_generator,
        event_emitter=None,
    )

    assert turn_number == 3
    assert [turn.text for turn in conversation] == [
        "Hello, thanks for calling. How can I help today?",
        "I need help with billing.",
        "Thanks for calling. Goodbye!",
    ]
    assert fast_ack_metric.calls == [
        (
            {
                "source": "dataset_input",
                "opening_strategy": "wait_for_bot_greeting",
                "scenario_kind": "ai",
            },
            None,
        )
    ]
    assert reply_latency.calls[0][0]["source"] == "fast_ack"


@pytest.mark.asyncio
async def test_execute_direct_http_ai_loop_uses_llm_source_when_llm_wins_race(monkeypatch) -> None:
    """When the LLM responds before the fast-ack deadline, source must be 'llm'."""
    reply_latency = _MetricObserver()
    fast_ack_metric = _MetricObserver()

    async def _fast_generator(**_kwargs):
        return "I need help with my billing statement."

    monkeypatch.setattr("src.direct_http_runtime.AI_CALLER_REPLY_LATENCY_SECONDS", reply_latency)
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)

    conversation, turn_number = await execute_direct_http_ai_loop(
        client=_FakeClient(
            responses=[
                "Hello, thanks for calling. How can I help today?",
                "Thanks for calling. Goodbye!",
            ]
        ),
        scenario=_ai_scenario(),
        run_id="run-direct-http-llm-wins",
        settings_obj=_settings(ai_voice_fast_ack_trigger_s=10.0),
        report_turn_fn=AsyncMock(),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Resolve the billing question.",
        },
        ai_caller_generate_fn=_fast_generator,
        event_emitter=None,
    )

    assert turn_number == 3
    assert conversation[1].text == "I need help with my billing statement."
    # LLM won the race — no fast-ack metric should be emitted.
    assert fast_ack_metric.calls == []
    assert reply_latency.calls[0][0]["source"] == "llm"
