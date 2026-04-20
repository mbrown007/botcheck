from __future__ import annotations

from typing import Callable

import httpx

from .metrics import PROVIDER_API_CALLS_TOTAL
from .openai_chat_client import (
    extract_chat_completion_content,
    normalize_text,
    request_chat_completion,
)


def _normalize_history_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        role = normalize_text(str(entry.get("role") or "")).lower()
        content = normalize_text(str(entry.get("content") or ""))
        if role not in {"system", "user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


class MockAgent:
    def __init__(
        self,
        *,
        settings_obj,
        http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self._settings = settings_obj
        self._http_client_cls = http_client_cls

    async def respond(
        self,
        system_prompt: str,
        history: list[dict[str, str]],
        turn_text: str,
    ) -> str:
        api_key = normalize_text(str(getattr(self._settings, "openai_api_key", "")))
        if not api_key:
            raise RuntimeError("Mock agent OpenAI API key is missing.")

        model = normalize_text(
            str(getattr(self._settings, "playground_mock_agent_model", "gpt-4o-mini"))
        ) or "gpt-4o-mini"
        timeout_s = float(getattr(self._settings, "playground_mock_agent_timeout_s", 6.0))
        api_base_url = normalize_text(
            str(
                getattr(
                    self._settings,
                    "playground_mock_agent_api_base_url",
                    "https://api.openai.com/v1",
                )
            )
        ) or "https://api.openai.com/v1"

        prompt = normalize_text(system_prompt)
        turn = normalize_text(turn_text)
        if not prompt:
            raise RuntimeError("Mock agent system prompt is required.")
        if not turn:
            raise RuntimeError("Mock agent turn text is required.")

        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 240,
            "messages": [
                {"role": "system", "content": prompt},
                *_normalize_history_messages(history),
                {"role": "user", "content": turn},
            ],
        }

        try:
            response_payload = await request_chat_completion(
                api_key=api_key,
                api_base_url=api_base_url,
                timeout_s=timeout_s,
                payload=payload,
                http_client_cls=self._http_client_cls,
            )
        except httpx.TimeoutException as exc:
            PROVIDER_API_CALLS_TOTAL.labels(
                provider="openai",
                service="llm",
                model=model,
                outcome="timeout",
            ).inc()
            raise RuntimeError("Mock agent request timed out.") from exc
        except Exception as exc:
            PROVIDER_API_CALLS_TOTAL.labels(
                provider="openai",
                service="llm",
                model=model,
                outcome="error",
            ).inc()
            raise RuntimeError("Mock agent generation failed.") from exc

        content = extract_chat_completion_content(
            response_payload,
            response_label="Mock agent",
        )
        PROVIDER_API_CALLS_TOTAL.labels(
            provider="openai",
            service="llm",
            model=model,
            outcome="success",
        ).inc()
        return normalize_text(content)
