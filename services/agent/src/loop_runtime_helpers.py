from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .media_engine import AgentTtsCircuitBridge, ProviderCircuitStateCallback

HeartbeatStateCallback = Callable[[int | None, str | None], None]


def build_heartbeat_state_emitter(
    heartbeat_state_callback: HeartbeatStateCallback | None,
) -> Callable[..., None]:
    def emit_heartbeat_state(
        *,
        turn_number: int | None = None,
        listener_state: str | None = None,
    ) -> None:
        if heartbeat_state_callback is None:
            return
        heartbeat_state_callback(turn_number, listener_state)

    return emit_heartbeat_state


def build_now_ms_fn(*, call_started_monotonic: float) -> Callable[[], int]:
    def now_ms() -> int:
        return int((time.monotonic() - call_started_monotonic) * 1000)

    return now_ms


def init_tts_circuit_bridge(
    *,
    tts: Any,
    logger_obj: logging.Logger | Any,
    provider_circuit_state_callback: ProviderCircuitStateCallback = None,
) -> AgentTtsCircuitBridge:
    tts_circuit_bridge = AgentTtsCircuitBridge(
        provider=getattr(tts, "provider_id", "openai"),
        logger_obj=logger_obj,
        provider_circuit_state_callback=provider_circuit_state_callback,
    )
    tts_circuit_bridge.init_gauge()
    return tts_circuit_bridge
