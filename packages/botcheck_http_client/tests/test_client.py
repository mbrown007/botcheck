from __future__ import annotations

from itertools import chain, repeat
from unittest.mock import AsyncMock

import httpx
import pytest

from botcheck_http_client import (
    DirectHTTPBotClient,
    DirectHTTPConfig,
    DirectHTTPTransportContext,
    build_direct_http_payload,
    extract_direct_http_text,
)


def test_build_direct_http_payload_maps_prompt_history_and_session() -> None:
    config = DirectHTTPConfig(
        request_text_field="input.text",
        request_history_field="context.history",
        request_session_id_field="context.session_id",
    )
    payload = build_direct_http_payload(
        prompt="hello",
        conversation=[],
        session_id="run_123",
        config=config,
    )

    assert payload == {
        "input": {"text": "hello"},
        "context": {"history": [], "session_id": "run_123"},
    }


def test_build_direct_http_payload_merges_defaults_and_request_context() -> None:
    config = DirectHTTPConfig(
        request_text_field="message",
        request_history_field="history",
        request_session_id_field="session_id",
        request_body_defaults={
            "dashboard_context": {
                "uid": "ops-overview",
                "time_range": {"from": "now-6h", "to": "now"},
            },
            "selected_context": [
                {"type": "datasource", "id": "prom-main", "display_name": "Prometheus"}
            ],
        },
    )

    payload = build_direct_http_payload(
        prompt="rank anomalies",
        conversation=[],
        session_id="run_456",
        config=config,
        request_context={
            "dashboard_context": {
                "name": "Operations Overview",
                "explore": {"datasource": "prom-main"},
            }
        },
    )

    assert payload == {
        "message": "rank anomalies",
        "history": [],
        "session_id": "run_456",
        "dashboard_context": {
            "uid": "ops-overview",
            "name": "Operations Overview",
            "time_range": {"from": "now-6h", "to": "now"},
            "explore": {"datasource": "prom-main"},
        },
        "selected_context": [
            {"type": "datasource", "id": "prom-main", "display_name": "Prometheus"}
        ],
    }


def test_build_direct_http_payload_prompt_field_wins_over_same_key_default() -> None:
    # If request_body_defaults contains a key that matches request_text_field,
    # the prompt value always overwrites it — defaults are never a fallback for
    # the core message/history/session fields.
    config = DirectHTTPConfig(
        request_text_field="message",
        request_body_defaults={"message": "default-message-should-be-clobbered"},
    )

    payload = build_direct_http_payload(
        prompt="actual prompt",
        conversation=[],
        session_id="run_1",
        config=config,
    )

    assert payload["message"] == "actual prompt"


def test_extract_direct_http_text_supports_dotted_json_path() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"response": {"text": "Hi there"}},
    )

    text = extract_direct_http_text(
        response=response,
        config=DirectHTTPConfig(response_text_field="response.text"),
    )

    assert text == "Hi there"


def test_extract_direct_http_text_falls_back_to_plain_text() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/plain"},
        text="Plain text reply",
    )

    text = extract_direct_http_text(
        response=response,
        config=DirectHTTPConfig(),
    )

    assert text == "Plain text reply"


def test_extract_direct_http_text_reads_complete_message_from_sse() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=(
            'data: {"type":"token","message":"Hello"}\n\n'
            'data: {"type":"token","message":" world"}\n\n'
            'data: {"type":"complete","message":"Hello world"}\n\n'
            'data: {"type":"done"}\n\n'
        ),
    )

    text = extract_direct_http_text(
        response=response,
        config=DirectHTTPConfig(),
    )

    assert text == "Hello world"


def test_extract_direct_http_text_falls_back_to_joined_sse_tokens() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=(
            'data: {"type":"token","message":"Disk"}\n\n'
            'data: {"type":"token","message":" pressure rising"}\n\n'
            'data: {"type":"done"}\n\n'
        ),
    )

    text = extract_direct_http_text(
        response=response,
        config=DirectHTTPConfig(),
    )

    assert text == "Disk pressure rising"


@pytest.mark.asyncio
async def test_direct_http_client_emits_observer_callbacks(monkeypatch) -> None:
    outcomes: list[str] = []
    latencies: list[tuple[str, float]] = []
    monotonic_values = chain((10.0, 10.25), repeat(10.25))
    monkeypatch.setattr("botcheck_http_client.client.time.monotonic", lambda: next(monotonic_values))

    client = DirectHTTPBotClient(
        context=DirectHTTPTransportContext(
            run_id="run_123",
            endpoint="https://example.invalid/respond",
        ),
        on_request_outcome=outcomes.append,
        on_request_latency=lambda outcome, elapsed_s: latencies.append((outcome, elapsed_s)),
    )
    client._client.request = AsyncMock(
        return_value=httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.invalid/respond"),
            headers={"content-type": "application/json"},
            json={"response": "Hello from bot"},
        )
    )

    response = await client.respond(prompt="hello", conversation=[], session_id="run_123")
    await client.aclose()

    assert response.text == "Hello from bot"
    assert response.latency_ms == 250
    assert outcomes == ["success"]
    assert latencies == [("success", 0.25)]
