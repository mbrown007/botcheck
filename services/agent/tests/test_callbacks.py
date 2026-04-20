"""Tests for callback helper functions."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import ConversationTurn

from src import callbacks


class _CounterVec:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def labels(self, *, endpoint: str, outcome: str):
        key = (endpoint, outcome)

        class _Counter:
            def inc(self_nonlocal, amount: float = 1.0) -> None:
                del self_nonlocal
                self.counts[key] = self.counts.get(key, 0) + int(amount)

        return _Counter()


class _TurnCounterVec:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def labels(self, *, speaker: str, outcome: str):
        key = (speaker, outcome)

        class _Counter:
            def inc(self_nonlocal, amount: float = 1.0) -> None:
                del self_nonlocal
                self.counts[key] = self.counts.get(key, 0) + int(amount)

        return _Counter()


def test_api_headers_injects_trace_context(monkeypatch):
    def _fake_inject(headers: dict[str, str]) -> dict[str, str]:
        merged = dict(headers)
        merged["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        return merged

    monkeypatch.setattr(callbacks, "inject_trace_context_into_headers", _fake_inject)

    headers = callbacks.api_headers(harness_secret="h-secret")
    assert headers["Authorization"] == "Bearer h-secret"
    assert headers["traceparent"].startswith("00-")


class TestPostRunHeartbeat:
    async def test_post_run_heartbeat_success(self):
        post_with_retry_fn = AsyncMock()
        counters = _CounterVec()
        sent_at = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)

        await callbacks.post_run_heartbeat(
            "run_hb",
            seq=3,
            sent_at=sent_at,
            turn_number=7,
            listener_state=" Awaiting_Bot ",
            post_with_retry_fn=post_with_retry_fn,
            callbacks_total=counters,
        )

        post_with_retry_fn.assert_awaited_once()
        path, payload = post_with_retry_fn.await_args.args
        assert path == "/runs/run_hb/heartbeat"
        assert payload["seq"] == 3
        assert payload["sent_at"] == "2026-03-04T12:00:00+00:00"
        assert payload["turn_number"] == 7
        assert payload["listener_state"] == "awaiting_bot"
        assert counters.counts[("heartbeat", "success")] == 1

    async def test_post_run_heartbeat_error_increments_callback_metric(self):
        post_with_retry_fn = AsyncMock(side_effect=RuntimeError("network down"))
        counters = _CounterVec()

        with pytest.raises(RuntimeError, match="network down"):
            await callbacks.post_run_heartbeat(
                "run_hb",
                seq=1,
                sent_at=datetime.now(UTC),
                turn_number=None,
                listener_state=None,
                post_with_retry_fn=post_with_retry_fn,
                callbacks_total=counters,
            )

        assert counters.counts[("heartbeat", "error")] == 1


class TestPostProviderCircuitState:
    async def test_post_provider_circuit_state_success(self):
        post_with_retry_fn = AsyncMock()
        counters = _CounterVec()
        observed_at = datetime(2026, 3, 4, 12, 34, 56, tzinfo=UTC)

        await callbacks.post_provider_circuit_state(
            source="agent",
            provider="OpenAI",
            service="TTS",
            component="Agent_Live_TTS",
            state="open",
            observed_at=observed_at,
            post_with_retry_fn=post_with_retry_fn,
            callbacks_total=counters,
        )

        post_with_retry_fn.assert_awaited_once()
        path, payload = post_with_retry_fn.await_args.args
        assert path == "/internal/provider-circuits/state"
        assert payload == {
            "source": "agent",
            "provider": "openai",
            "service": "tts",
            "component": "agent_live_tts",
            "state": "open",
            "observed_at": "2026-03-04T12:34:56+00:00",
        }
        assert counters.counts[("provider_circuit", "success")] == 1

    async def test_post_provider_circuit_state_error_increments_callback_metric(self):
        post_with_retry_fn = AsyncMock(side_effect=RuntimeError("unreachable"))
        counters = _CounterVec()

        with pytest.raises(RuntimeError, match="unreachable"):
            await callbacks.post_provider_circuit_state(
                source="agent",
                provider="openai",
                service="tts",
                component="agent_live_tts",
                state="closed",
                observed_at=None,
                post_with_retry_fn=post_with_retry_fn,
                callbacks_total=counters,
            )

        assert counters.counts[("provider_circuit", "error")] == 1


class TestFailRunWithDetails:
    async def test_fail_run_with_details_includes_error_code_when_provided(self):
        post_with_retry_fn = AsyncMock()
        counters = _CounterVec()

        await callbacks.fail_run_with_details(
            "run_fail",
            reason="AI caller unavailable",
            end_reason="service_not_available",
            error_code="ai_caller_unavailable",
            loop_guard=None,
            post_with_retry_fn=post_with_retry_fn,
            callbacks_total=counters,
        )

        post_with_retry_fn.assert_awaited_once()
        path, payload = post_with_retry_fn.await_args.args
        assert path == "/runs/run_fail/fail"
        assert payload["error_code"] == "ai_caller_unavailable"
        assert counters.counts[("fail", "success")] == 1


class TestReportTurn:
    async def test_report_turn_records_normal_outcome_on_turn_counter(self):
        post_with_retry_fn = AsyncMock()
        callback_counters = _CounterVec()
        turn_counters = _TurnCounterVec()

        await callbacks.report_turn(
            "run_turn",
            ConversationTurn(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="hello",
                audio_start_ms=0,
                audio_end_ms=100,
            ),
            visit=None,
            branch_condition_matched=None,
            branch_response_snippet=None,
            post_with_retry_fn=post_with_retry_fn,
            callbacks_total=callback_counters,
            turns_total=turn_counters,
        )

        assert callback_counters.counts[("turns", "success")] == 1
        assert turn_counters.counts[("harness", "normal")] == 1

    async def test_report_turn_records_timeout_outcome_on_turn_counter(self):
        post_with_retry_fn = AsyncMock()
        callback_counters = _CounterVec()
        turn_counters = _TurnCounterVec()

        await callbacks.report_turn(
            "run_turn",
            ConversationTurn(
                turn_id="t2",
                turn_number=2,
                speaker="bot",
                text="(timeout)",
                audio_start_ms=100,
                audio_end_ms=200,
            ),
            visit=None,
            branch_condition_matched=None,
            branch_response_snippet=None,
            post_with_retry_fn=post_with_retry_fn,
            callbacks_total=callback_counters,
            turns_total=turn_counters,
        )

        assert callback_counters.counts[("turns", "success")] == 1
        assert turn_counters.counts[("bot", "timeout")] == 1
