from __future__ import annotations

from typing import Any

import pytest
from botcheck_scenarios import BotConfig, ConversationTurn, ScenarioDefinition, ScenarioType, Turn

from src.ai_caller_policy import generate_next_ai_caller_decision, generate_next_ai_caller_utterance


def _scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-ai-policy",
        name="AI Policy",
        type=ScenarioType.GOLDEN_PATH,
        description="Confirm booking details and close politely.",
        bot=BotConfig(endpoint="sip:bot@example.com"),
        turns=[Turn(id="t1", text="hello")],
    )


def _conversation() -> list[ConversationTurn]:
    return [
        ConversationTurn(
            turn_id="ai_record_input",
            turn_number=1,
            speaker="harness",
            text="I need to reschedule my appointment.",
            audio_start_ms=0,
            audio_end_ms=100,
        ),
        ConversationTurn(
            turn_id="ai_record_input_bot",
            turn_number=2,
            speaker="bot",
            text="Sure, what date works for you?",
            audio_start_ms=150,
            audio_end_ms=300,
        ),
    ]


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, *, payload: dict[str, Any], captured: dict[str, Any], **kwargs: Any) -> None:
        self._payload = payload
        self._captured = captured
        self._captured["init_kwargs"] = kwargs

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, path: str, json: dict[str, Any], headers: dict[str, str] | None = None):
        self._captured["path"] = path
        self._captured["json"] = json
        self._captured["headers"] = headers
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_generate_next_ai_caller_utterance_returns_continue_utterance():
    captured: dict[str, Any] = {}
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"continue","utterance":"Friday morning works for me."}'
                }
            }
        ]
    }

    async_result = await generate_next_ai_caller_utterance(
        openai_api_key="sk-test",
        model="gpt-4o-mini",
        timeout_s=3.0,
        api_base_url="https://api.openai.com/v1",
        scenario=_scenario(),
        conversation=_conversation(),
        last_bot_text="Sure, what date works for you?",
        objective_hint="Reschedule and confirm next steps.",
        persona_name="Alex",
        max_context_turns=6,
        circuit_breaker=None,
        http_client_cls=lambda **kwargs: _FakeClient(payload=payload, captured=captured, **kwargs),
    )

    assert async_result == "Friday morning works for me."
    assert captured["path"] == "/chat/completions"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert captured["headers"] == {
        "Authorization": "Bearer sk-test",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_generate_next_ai_caller_decision_includes_reasoning_summary_and_confidence():
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"action":"continue","utterance":"Friday morning works for me.",'
                        '"reasoning_summary":"Continue by proposing a concrete new appointment time.",'
                        '"confidence":0.82}'
                    )
                }
            }
        ]
    }

    decision = await generate_next_ai_caller_decision(
        openai_api_key="sk-test",
        model="gpt-4o-mini",
        timeout_s=3.0,
        api_base_url="https://api.openai.com/v1",
        scenario=_scenario(),
        conversation=_conversation(),
        last_bot_text="Sure, what date works for you?",
        objective_hint="Reschedule and confirm next steps.",
        persona_name="Alex",
        max_context_turns=6,
        circuit_breaker=None,
        http_client_cls=lambda **kwargs: _FakeClient(payload=payload, captured={}, **kwargs),
    )

    assert decision.action == "continue"
    assert decision.utterance == "Friday morning works for me."
    assert decision.reasoning_summary == "Continue by proposing a concrete new appointment time."
    assert decision.confidence == 0.82


@pytest.mark.asyncio
async def test_generate_next_ai_caller_utterance_returns_none_on_end_action():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"end","utterance":""}'
                }
            }
        ]
    }

    result = await generate_next_ai_caller_utterance(
        openai_api_key="sk-test",
        model="gpt-4o-mini",
        timeout_s=3.0,
        api_base_url="https://api.openai.com/v1",
        scenario=_scenario(),
        conversation=_conversation(),
        last_bot_text="Anything else I can help with?",
        objective_hint="Reschedule and confirm next steps.",
        persona_name="Alex",
        max_context_turns=6,
        circuit_breaker=None,
        http_client_cls=lambda **kwargs: _FakeClient(payload=payload, captured={}, **kwargs),
    )

    assert result is None


@pytest.mark.asyncio
async def test_generate_next_ai_caller_decision_falls_back_when_reasoning_summary_missing():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"end","utterance":""}'
                }
            }
        ]
    }

    decision = await generate_next_ai_caller_decision(
        openai_api_key="sk-test",
        model="gpt-4o-mini",
        timeout_s=3.0,
        api_base_url="https://api.openai.com/v1",
        scenario=_scenario(),
        conversation=_conversation(),
        last_bot_text="Anything else I can help with?",
        objective_hint="Reschedule and confirm next steps.",
        persona_name="Alex",
        max_context_turns=6,
        circuit_breaker=None,
        http_client_cls=lambda **kwargs: _FakeClient(payload=payload, captured={}, **kwargs),
    )

    assert decision.action == "end"
    assert decision.utterance is None
    assert "scenario objective" in decision.reasoning_summary.lower()


@pytest.mark.asyncio
async def test_generate_next_ai_caller_utterance_rejects_non_json_response():
    payload = {
        "choices": [
            {
                "message": {
                    "content": "Sure, Friday morning works."
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="valid JSON"):
        await generate_next_ai_caller_utterance(
            openai_api_key="sk-test",
            model="gpt-4o-mini",
            timeout_s=3.0,
            api_base_url="https://api.openai.com/v1",
            scenario=_scenario(),
            conversation=_conversation(),
            last_bot_text="Sure, what date works for you?",
            objective_hint="Reschedule and confirm next steps.",
            persona_name="Alex",
            max_context_turns=6,
            circuit_breaker=None,
            http_client_cls=lambda **kwargs: _FakeClient(payload=payload, captured={}, **kwargs),
        )
