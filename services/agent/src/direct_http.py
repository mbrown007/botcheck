from __future__ import annotations

from botcheck_http_client import (
    DirectHTTPBotClient as SharedDirectHTTPBotClient,
    DirectHTTPConfig,
    DirectHTTPResponse,
    DirectHTTPTransportContext,
    build_direct_http_payload,
    extract_direct_http_text,
)

from .metrics import _counter, _histogram

__all__ = [
    "DirectHTTPBotClient",
    "DirectHTTPConfig",
    "DirectHTTPResponse",
    "DirectHTTPTransportContext",
    "build_direct_http_payload",
    "extract_direct_http_text",
    "DIRECT_HTTP_REQUESTS_TOTAL",
    "DIRECT_HTTP_LATENCY_SECONDS",
]

DIRECT_HTTP_REQUESTS_TOTAL = _counter(
    "botcheck_direct_http_requests_total",
    "Direct HTTP transport request outcomes.",
    ["outcome"],
)

DIRECT_HTTP_LATENCY_SECONDS = _histogram(
    "botcheck_direct_http_latency_seconds",
    "Direct HTTP transport request latency in seconds.",
    ["outcome"],
    buckets=(0.05, 0.1, 0.2, 0.4, 0.8, 1.2, 2, 3, 5, 8, 12),
)


def _record_request_outcome(outcome: str) -> None:
    DIRECT_HTTP_REQUESTS_TOTAL.labels(outcome=outcome).inc()


def _record_request_latency(outcome: str, elapsed_s: float) -> None:
    DIRECT_HTTP_LATENCY_SECONDS.labels(outcome=outcome).observe(elapsed_s)


class DirectHTTPBotClient(SharedDirectHTTPBotClient):
    def __init__(self, *, context: DirectHTTPTransportContext) -> None:
        super().__init__(
            context=context,
            on_request_outcome=_record_request_outcome,
            on_request_latency=_record_request_latency,
        )
