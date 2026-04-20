from __future__ import annotations

from typing import Any

import pytest

from src.mock_agent import MockAgent


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

    async def post(self, path: str, *, json: dict[str, Any], headers: dict[str, Any] | None = None):
        self._captured["path"] = path
        self._captured["json"] = json
        self._captured["headers"] = headers
        return _FakeResponse(self._payload)


def _settings(**overrides):
    defaults = {
        "openai_api_key": "sk-test",
        "playground_mock_agent_model": "gpt-4o-mini",
        "playground_mock_agent_timeout_s": 6.0,
        "playground_mock_agent_api_base_url": "https://api.openai.com/v1",
    }
    defaults.update(overrides)
    return type("S", (), defaults)()


@pytest.mark.asyncio
async def test_mock_agent_respond_posts_history_and_latest_turn() -> None:
    captured: dict[str, Any] = {}
    agent = MockAgent(
        settings_obj=_settings(),
        http_client_cls=lambda **kwargs: _FakeClient(
            payload={"choices": [{"message": {"content": "Sure, I can help with that."}}]},
            captured=captured,
            **kwargs,
        ),
    )

    response = await agent.respond(
        "You are a calm support bot.",
        history=[
            {"role": "user", "content": "I need help with my order."},
            {"role": "assistant", "content": "Sure, what seems to be wrong?"},
            {"role": "user", "content": " It has not arrived yet. "},
        ],
        turn_text="Can you check the status?",
    )

    assert response == "Sure, I can help with that."
    assert captured["path"] == "/chat/completions"
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "You are a calm support bot."},
        {"role": "user", "content": "I need help with my order."},
        {"role": "assistant", "content": "Sure, what seems to be wrong?"},
        {"role": "user", "content": "It has not arrived yet."},
        {"role": "user", "content": "Can you check the status?"},
    ]


@pytest.mark.asyncio
async def test_mock_agent_uses_fixed_model_from_settings() -> None:
    captured: dict[str, Any] = {}
    agent = MockAgent(
        settings_obj=_settings(playground_mock_agent_model="gpt-4.1-mini"),
        http_client_cls=lambda **kwargs: _FakeClient(
            payload={"choices": [{"message": {"content": "OK"}}]},
            captured=captured,
            **kwargs,
        ),
    )

    await agent.respond(
        "You are a support bot.",
        history=[],
        turn_text="Hello there",
    )

    assert captured["json"]["model"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_mock_agent_rejects_missing_api_key() -> None:
    agent = MockAgent(settings_obj=_settings(openai_api_key=""))

    with pytest.raises(RuntimeError, match="OpenAI API key is missing"):
        await agent.respond(
            "You are a support bot.",
            history=[],
            turn_text="Hello there",
        )
