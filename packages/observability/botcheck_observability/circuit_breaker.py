from __future__ import annotations

from typing import Literal

from .helpers import counter, gauge

PROVIDER_CIRCUIT_TRANSITIONS_TOTAL = counter(
    "botcheck_provider_circuit_transitions_total",
    "External provider circuit-breaker state transitions.",
    ["provider", "service", "component", "from_state", "to_state"],
)

PROVIDER_CIRCUIT_REJECTIONS_TOTAL = counter(
    "botcheck_provider_circuit_rejections_total",
    "External provider requests rejected due to open circuit.",
    ["provider", "service", "component"],
)

PROVIDER_CIRCUIT_STATE = gauge(
    "botcheck_provider_circuit_state",
    "Current provider circuit state (one-hot by state label).",
    ["source", "provider", "service", "component", "state"],
)

_CIRCUIT_STATES: tuple[str, ...] = ("open", "half_open", "closed", "unknown")


def set_provider_circuit_state(
    *,
    source: Literal["api", "agent", "judge"],
    provider: str,
    service: str,
    component: str,
    state: str,
) -> None:
    normalized_state = state.strip().lower()
    if normalized_state not in _CIRCUIT_STATES:
        normalized_state = "unknown"
    for candidate in _CIRCUIT_STATES:
        PROVIDER_CIRCUIT_STATE.labels(
            source=source,
            provider=provider,
            service=service,
            component=component,
            state=candidate,
        ).set(1.0 if candidate == normalized_state else 0.0)
