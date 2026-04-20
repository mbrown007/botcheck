from __future__ import annotations

from .telemetry import (
    attach_trace_context_from_carrier,
    instrument_httpx,
    setup_tracing,
)


def trace_carrier_from_room_metadata(metadata: dict[str, object]) -> dict[str, str]:
    traceparent = str(metadata.get("traceparent", "")).strip()
    tracestate = str(metadata.get("tracestate", "")).strip()
    carrier: dict[str, str] = {}
    if traceparent:
        carrier["traceparent"] = traceparent
    if tracestate:
        carrier["tracestate"] = tracestate
    return carrier


def attach_trace_context_from_room_metadata(metadata: dict[str, object]) -> object | None:
    return attach_trace_context_from_carrier(trace_carrier_from_room_metadata(metadata))


def bootstrap_telemetry(service_name: str) -> None:
    setup_tracing(service_name)
    instrument_httpx()
