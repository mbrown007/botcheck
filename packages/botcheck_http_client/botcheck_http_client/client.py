from __future__ import annotations

import json
import math
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import httpx
from pydantic import BaseModel, Field, field_validator

RequestLatencyObserver = Callable[[str, float], None]
RequestOutcomeObserver = Callable[[str], None]


class DirectHTTPTransportContext(BaseModel):
    run_id: str
    transport_profile_id: str | None = None
    endpoint: str
    headers: dict[str, object] = Field(default_factory=dict)
    direct_http_config: dict[str, object] = Field(default_factory=dict)


class DirectHTTPConfig(BaseModel):
    method: str = "POST"
    request_content_type: str = "json"
    request_text_field: str = "message"
    request_history_field: str | None = "history"
    request_session_id_field: str | None = "session_id"
    request_body_defaults: dict[str, object] = Field(default_factory=dict)
    response_text_field: str = "response"
    timeout_s: float = Field(default=30.0, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)

    @field_validator("request_text_field", "response_text_field")
    @classmethod
    def _require_field_name(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("field name must be a non-empty string")
        return candidate

    @field_validator("request_history_field", "request_session_id_field")
    @classmethod
    def _normalize_field_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        return candidate or None

    @field_validator("request_body_defaults", mode="before")
    @classmethod
    def _normalize_request_body_defaults(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("request_body_defaults must be an object")
        return dict(value)


@dataclass(slots=True)
class DirectHTTPResponse:
    text: str
    latency_ms: int


def _history_payload(conversation) -> list[dict[str, object]]:
    return [
        {
            "turn_id": turn.turn_id,
            "turn_number": turn.turn_number,
            "speaker": turn.speaker,
            "text": turn.text,
        }
        for turn in conversation
    ]


def _set_path(payload: dict[str, object], path: str, value: object) -> None:
    parts = [segment.strip() for segment in path.split(".") if segment.strip()]
    if not parts:
        return
    cursor = payload
    for key in parts[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[parts[-1]] = value


def _extract_path(payload: object, path: str) -> object | None:
    parts = [segment.strip() for segment in path.split(".") if segment.strip()]
    cursor = payload
    for key in parts:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _normalize_response_text(value: object) -> str:
    if value is None:
        raise RuntimeError("Direct HTTP response text is missing")
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, bool)):
        text = str(value)
    else:
        raise RuntimeError("Direct HTTP response text must resolve to a scalar value")
    if not text:
        raise RuntimeError("Direct HTTP response text is empty")
    return text


def _extract_sse_text(payload: str) -> str:
    complete_message: str | None = None
    token_parts: list[str] = []
    parsed_any_chunk = False

    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, dict):
            continue
        parsed_any_chunk = True
        chunk_type = str(chunk.get("type", "")).strip().lower()
        message = chunk.get("message")
        if chunk_type == "complete" and message is not None:
            complete_message = _normalize_response_text(message)
        elif chunk_type == "token" and message is not None:
            token_parts.append(str(message))

    if complete_message:
        return complete_message
    if token_parts:
        text = "".join(token_parts).strip()
        if text:
            return text
    if parsed_any_chunk:
        raise RuntimeError("Direct HTTP SSE response did not contain a usable assistant message")
    raise RuntimeError("Direct HTTP SSE response body is empty")


def _deep_merge_dicts(
    base: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    # deepcopy(base) guarantees the returned dict owns all its values.
    # When recursing, `existing` is already a member of the deep-copied
    # `merged` dict, so it is safe to pass directly — no mutation risk.
    # Non-dict values from `updates` are also deep-copied so callers
    # cannot mutate the result through a shared reference.
    merged = deepcopy(base)
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def build_direct_http_payload(
    *,
    prompt: str,
    conversation,
    session_id: str,
    config: DirectHTTPConfig,
    request_context: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = dict(config.request_body_defaults or {})
    if request_context:
        payload = _deep_merge_dicts(payload, request_context)
    _set_path(payload, config.request_text_field, prompt)
    if config.request_history_field:
        _set_path(payload, config.request_history_field, _history_payload(conversation))
    if config.request_session_id_field:
        _set_path(payload, config.request_session_id_field, session_id)
    return payload


def extract_direct_http_text(*, response: httpx.Response, config: DirectHTTPConfig) -> str:
    content_type = str(response.headers.get("content-type", "")).lower()
    if "application/json" in content_type:
        payload = response.json()
        return _normalize_response_text(_extract_path(payload, config.response_text_field))
    if "text/event-stream" in content_type:
        return _extract_sse_text(response.text)
    text = response.text.strip()
    if text:
        return text
    raise RuntimeError("Direct HTTP response body is empty")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


class DirectHTTPBotClient:
    def __init__(
        self,
        *,
        context: DirectHTTPTransportContext,
        on_request_latency: RequestLatencyObserver | None = None,
        on_request_outcome: RequestOutcomeObserver | None = None,
    ) -> None:
        self.context = context
        self.config = DirectHTTPConfig.model_validate(context.direct_http_config or {})
        self._on_request_latency = on_request_latency
        self._on_request_outcome = on_request_outcome
        self._client = httpx.AsyncClient(
            headers={str(key).strip(): str(value).strip() for key, value in (context.headers or {}).items()},
            timeout=self.config.timeout_s,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _emit_latency(self, outcome: str, elapsed_s: float) -> None:
        if self._on_request_latency is not None:
            self._on_request_latency(outcome, elapsed_s)

    def _emit_outcome(self, outcome: str) -> None:
        if self._on_request_outcome is not None:
            self._on_request_outcome(outcome)

    async def respond(
        self,
        *,
        prompt: str,
        conversation,
        session_id: str,
        request_context: dict[str, object] | None = None,
    ) -> DirectHTTPResponse:
        payload = build_direct_http_payload(
            prompt=prompt,
            conversation=conversation,
            session_id=session_id,
            config=self.config,
            request_context=request_context,
        )
        attempts = self.config.max_retries + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            started = time.monotonic()
            try:
                extra_headers: dict[str, str] = {}
                if self.config.request_content_type != "json":
                    extra_headers["content-type"] = "application/json"
                response = await self._client.request(
                    self.config.method,
                    self.context.endpoint,
                    json=payload if self.config.request_content_type == "json" else None,
                    content=None if self.config.request_content_type == "json" else json.dumps(payload).encode(),
                    headers=extra_headers or None,
                )
                response.raise_for_status()
                text = extract_direct_http_text(response=response, config=self.config)
                elapsed_s = time.monotonic() - started
                self._emit_outcome("success")
                self._emit_latency("success", elapsed_s)
                return DirectHTTPResponse(text=text, latency_ms=max(1, math.ceil(elapsed_s * 1000)) if elapsed_s > 0 else 0)
            except Exception as exc:
                last_exc = exc
                outcome = "retryable_error" if _is_retryable(exc) else "error"
                elapsed_s = time.monotonic() - started
                self._emit_latency(outcome, elapsed_s)
                if attempt < attempts - 1 and _is_retryable(exc):
                    self._emit_outcome("retry")
                    continue
                self._emit_outcome(outcome)
                break
        if isinstance(last_exc, RuntimeError):
            raise last_exc
        if last_exc is not None:
            raise RuntimeError(f"Direct HTTP request failed: {type(last_exc).__name__}: {last_exc}") from last_exc
        raise RuntimeError("Direct HTTP request failed")
