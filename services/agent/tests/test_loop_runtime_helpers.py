from __future__ import annotations

from unittest.mock import Mock

from src.loop_runtime_helpers import (
    build_heartbeat_state_emitter,
    build_now_ms_fn,
    init_tts_circuit_bridge,
)


def test_build_heartbeat_state_emitter_noops_without_callback() -> None:
    emit = build_heartbeat_state_emitter(None)

    emit(turn_number=3, listener_state="awaiting_bot")


def test_build_heartbeat_state_emitter_forwards_values() -> None:
    callback = Mock()

    emit = build_heartbeat_state_emitter(callback)
    emit(turn_number=5, listener_state="speaking_harness")

    callback.assert_called_once_with(5, "speaking_harness")


def test_build_now_ms_fn_uses_elapsed_monotonic(monkeypatch) -> None:
    monkeypatch.setattr("src.loop_runtime_helpers.time.monotonic", lambda: 103.275)

    now_ms = build_now_ms_fn(call_started_monotonic=100.0)

    assert now_ms() == 3275


def test_build_now_ms_fn_re_reads_monotonic_on_each_call(monkeypatch) -> None:
    readings = iter([101.0, 102.5])
    monkeypatch.setattr("src.loop_runtime_helpers.time.monotonic", lambda: next(readings))

    now_ms = build_now_ms_fn(call_started_monotonic=100.0)

    assert now_ms() == 1000
    assert now_ms() == 2500


def test_init_tts_circuit_bridge_constructs_and_initializes(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, provider: str, logger_obj, provider_circuit_state_callback) -> None:
            calls["provider"] = provider
            calls["logger_obj"] = logger_obj
            calls["provider_circuit_state_callback"] = provider_circuit_state_callback
            calls["bridge"] = self

        def init_gauge(self) -> None:
            calls["init_gauge_called"] = True

    monkeypatch.setattr("src.loop_runtime_helpers.AgentTtsCircuitBridge", _FakeBridge)
    fake_tts = type("FakeTTS", (), {"provider_id": "cartesia"})()
    callback = Mock()

    bridge = init_tts_circuit_bridge(
        tts=fake_tts,
        logger_obj="logger",
        provider_circuit_state_callback=callback,
    )

    assert bridge is calls["bridge"]
    assert calls["provider"] == "cartesia"
    assert calls["logger_obj"] == "logger"
    assert calls["provider_circuit_state_callback"] is callback
    assert calls["init_gauge_called"] is True


def test_init_tts_circuit_bridge_falls_back_to_openai_without_provider_id(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, provider: str, logger_obj, provider_circuit_state_callback) -> None:
            calls["provider"] = provider

        def init_gauge(self) -> None:
            pass

    monkeypatch.setattr("src.loop_runtime_helpers.AgentTtsCircuitBridge", _FakeBridge)
    fake_tts = object()  # no provider_id attribute

    init_tts_circuit_bridge(tts=fake_tts, logger_obj=None)

    assert calls["provider"] == "openai"
