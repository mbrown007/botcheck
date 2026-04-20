"""Canonical BotCheck trace contract and W3C propagation helpers.

Phase 33 assumes the current default OpenTelemetry sampling policy remains
parent-based always-on unless a later phase explicitly changes sampling.

Expected high-level span hierarchy:

    run.lifecycle
      ├─ dispatch.livekit
      ├─ dispatch.sip
      │    └─ harness.session
      └─ judge.run
           └─ judge.llm_score
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SPAN_RUN_LIFECYCLE = "run.lifecycle"
SPAN_LIVEKIT_DISPATCH = "dispatch.livekit"
SPAN_SIP_DISPATCH = "dispatch.sip"
SPAN_HARNESS_SESSION = "harness.session"
SPAN_JUDGE_RUN = "judge.run"
SPAN_JUDGE_LLM_SCORE = "judge.llm_score"

CANONICAL_SPAN_NAMES = frozenset(
    {
        SPAN_RUN_LIFECYCLE,
        SPAN_LIVEKIT_DISPATCH,
        SPAN_SIP_DISPATCH,
        SPAN_HARNESS_SESSION,
        SPAN_JUDGE_RUN,
        SPAN_JUDGE_LLM_SCORE,
    }
)

ATTR_RUN_ID = "run.id"
ATTR_TENANT_ID = "tenant.id"
ATTR_SCENARIO_ID = "scenario.id"
ATTR_SCENARIO_KIND = "scenario.kind"
ATTR_TRIGGER_SOURCE = "trigger.source"
ATTR_SCHEDULE_ID = "schedule.id"
ATTR_TRANSPORT_KIND = "transport.kind"
ATTR_TRANSPORT_PROFILE_ID = "transport_profile.id"
ATTR_JUDGE_CONTRACT_VERSION = "judge.contract_version"

# Attribute keys for judge.llm_score child spans
ATTR_SCORE_DIMENSION = "score.dimension"
ATTR_JUDGE_METRIC_TYPE = "judge.metric_type"
ATTR_JUDGE_STATUS = "judge.status"
ATTR_JUDGE_THRESHOLD = "judge.threshold"
ATTR_JUDGE_GATE = "judge.gate"
ATTR_JUDGE_PASSED = "judge.passed"
ATTR_JUDGE_SCORE = "judge.score"

REQUIRED_TRACE_ATTRIBUTES = (
    ATTR_RUN_ID,
    ATTR_TENANT_ID,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_KIND,
    ATTR_TRIGGER_SOURCE,
    ATTR_TRANSPORT_KIND,
    ATTR_TRANSPORT_PROFILE_ID,
    ATTR_SCHEDULE_ID,
    ATTR_JUDGE_CONTRACT_VERSION,
)

TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"
_TRACE_HEADER_KEYS = (TRACEPARENT_HEADER, TRACESTATE_HEADER)


def extract_trace_context_headers(carrier: Mapping[str, Any] | None) -> dict[str, str]:
    """Return only trimmed W3C trace headers from an arbitrary carrier."""
    if not carrier:
        return {}
    payload: dict[str, str] = {}
    for key in _TRACE_HEADER_KEYS:
        value = str(carrier.get(key, "")).strip()
        if value:
            payload[key] = value
    return payload


def current_w3c_trace_context() -> dict[str, str]:
    """Inject current OTEL context into a carrier and return only W3C fields."""
    carrier: dict[str, str] = {}
    try:
        from opentelemetry.propagate import inject  # noqa: PLC0415
    except Exception:
        return {}
    inject(carrier=carrier)
    return extract_trace_context_headers(carrier)


def inject_trace_context_into_headers(headers: Mapping[str, str] | None = None) -> dict[str, str]:
    """Merge current W3C trace headers into an existing header mapping."""
    merged = dict(headers or {})
    merged.update(current_w3c_trace_context())
    return merged


def attach_trace_context_from_carrier(carrier: Mapping[str, str] | None) -> object | None:
    """Extract and attach W3C trace headers, returning the OTEL context token."""
    headers = extract_trace_context_headers(carrier)
    if not headers:
        return None
    try:
        from opentelemetry import context as otel_context  # noqa: PLC0415
        from opentelemetry.propagate import extract  # noqa: PLC0415
    except Exception:
        return None
    extracted = extract(carrier=headers)
    return otel_context.attach(extracted)


def detach_trace_context(token: object | None) -> None:
    """Detach a previously attached OTEL context token."""
    if token is None:
        return
    try:
        from opentelemetry import context as otel_context  # noqa: PLC0415
    except Exception:
        return
    otel_context.detach(token)
