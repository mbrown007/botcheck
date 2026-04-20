from __future__ import annotations

import asyncio

import pytest

from src import metrics
from src.media_engine import AgentSttCircuitBridge


def test_agent_stt_listen_latency_labels() -> None:
    """STT_LISTEN_LATENCY_SECONDS is agent-specific (not in the shared package)."""
    assert tuple(metrics.STT_LISTEN_LATENCY_SECONDS._labelnames) == (
        "provider",
        "model",
        "result",
        "scenario_kind",
    )


def test_agent_turns_labels_include_outcome() -> None:
    assert tuple(metrics.AGENT_TURNS_TOTAL._labelnames) == ("speaker", "outcome")


@pytest.mark.asyncio
async def test_agent_stt_circuit_bridge_publishes_closed_snapshot() -> None:
    published: list[dict[str, str]] = []

    async def _publish(**kwargs) -> None:
        published.append({key: str(value) for key, value in kwargs.items() if key != "observed_at"})

    bridge = AgentSttCircuitBridge(
        provider="deepgram",
        logger_obj=type("LoggerStub", (), {"warning": lambda *args, **kwargs: None})(),
        provider_circuit_state_callback=_publish,
    )

    bridge.init_gauge()
    bridge.mark_closed(reason="session_started")
    await asyncio.sleep(0)

    assert published[-1] == {
        "source": "agent",
        "provider": "deepgram",
        "service": "stt",
        "component": "agent_live_stt",
        "state": "closed",
    }
