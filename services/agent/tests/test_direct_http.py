from __future__ import annotations

from itertools import chain, repeat
from unittest.mock import AsyncMock

import httpx
import pytest

from src.direct_http import DirectHTTPBotClient, DirectHTTPTransportContext


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


@pytest.mark.asyncio
async def test_direct_http_client_records_latency_in_seconds(monkeypatch) -> None:
    request_counter = _MetricObserver()
    latency_histogram = _MetricObserver()
    monotonic_values = chain((10.0, 10.25), repeat(10.25))
    monkeypatch.setattr("src.direct_http.DIRECT_HTTP_REQUESTS_TOTAL", request_counter)
    monkeypatch.setattr("src.direct_http.DIRECT_HTTP_LATENCY_SECONDS", latency_histogram)
    monkeypatch.setattr("botcheck_http_client.client.time.monotonic", lambda: next(monotonic_values))

    client = DirectHTTPBotClient(
        context=DirectHTTPTransportContext(
            run_id="run_123",
            endpoint="https://example.invalid/respond",
        )
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
    assert request_counter.calls == [({"outcome": "success"}, None)]
    assert latency_histogram.calls == [({"outcome": "success"}, 0.25)]
