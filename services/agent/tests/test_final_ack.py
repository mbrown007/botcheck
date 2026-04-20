"""Tests for greedy final ACK hardening in harness agent."""

import asyncio
import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import BotConfig, ConversationTurn, ScenarioDefinition, ScenarioType, Turn

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

from src import agent  # noqa: E402
from src.config import settings  # noqa: E402
from src.graph import HarnessLoopError, HarnessMaxTurnsError  # noqa: E402


def _conversation() -> list[ConversationTurn]:
    return [
        ConversationTurn(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="hello",
            audio_start_ms=0,
            audio_end_ms=100,
        )
    ]


class TestGreedyFinalAck:
    async def test_complete_primary_success(self, monkeypatch):
        complete_mock = AsyncMock()
        fail_mock = AsyncMock()
        monkeypatch.setattr(agent, "complete_run", complete_mock)
        monkeypatch.setattr(agent, "fail_run_with_details", fail_mock)

        result = await agent.finalize_run_with_greedy_ack(
            run_id="run_ok",
            conversation=_conversation(),
            end_reason="max_turns_reached",
            primary="complete",
        )

        assert result == "complete"
        complete_mock.assert_awaited_once()
        fail_mock.assert_not_awaited()

    async def test_complete_fallback_to_fail(self, monkeypatch):
        complete_mock = AsyncMock(side_effect=RuntimeError("complete callback failed"))
        fail_mock = AsyncMock()
        monkeypatch.setattr(agent, "complete_run", complete_mock)
        monkeypatch.setattr(agent, "fail_run_with_details", fail_mock)

        result = await agent.finalize_run_with_greedy_ack(
            run_id="run_fallback",
            conversation=_conversation(),
            end_reason="max_turns_reached",
            primary="complete",
            failure_reason="complete callback failed after scenario execution",
        )

        assert result == "fail"
        complete_mock.assert_awaited_once()
        fail_mock.assert_awaited_once()

    async def test_complete_fallback_to_fail_passes_loop_guard_payload(self, monkeypatch):
        complete_mock = AsyncMock(side_effect=RuntimeError("complete callback failed"))
        fail_mock = AsyncMock()
        monkeypatch.setattr(agent, "complete_run", complete_mock)
        monkeypatch.setattr(agent, "fail_run_with_details", fail_mock)

        loop_guard = {
            "guard": "max_turns_reached",
            "turn_id": "t_retry",
            "visit": 7,
            "effective_cap": 25,
        }
        result = await agent.finalize_run_with_greedy_ack(
            run_id="run_fallback_with_loop_guard",
            conversation=_conversation(),
            end_reason="max_turns_reached",
            primary="complete",
            failure_reason="complete callback failed after scenario execution",
            failure_loop_guard=loop_guard,
        )

        assert result == "fail"
        complete_mock.assert_awaited_once()
        fail_mock.assert_awaited_once()
        call_kwargs = fail_mock.await_args.kwargs
        assert call_kwargs["loop_guard"] == loop_guard

    async def test_both_callbacks_fail_persists_recovery_record(self, monkeypatch, tmp_path):
        complete_mock = AsyncMock(side_effect=RuntimeError("complete callback failed"))
        fail_mock = AsyncMock(side_effect=RuntimeError("fail callback failed"))
        monkeypatch.setattr(agent, "complete_run", complete_mock)
        monkeypatch.setattr(agent, "fail_run_with_details", fail_mock)
        monkeypatch.setattr(settings, "final_ack_recovery_enabled", True)
        recovery_path = tmp_path / "final-ack-recovery.jsonl"
        monkeypatch.setattr(settings, "final_ack_recovery_log_path", str(recovery_path))

        with pytest.raises(RuntimeError, match="Final callback unreconciled"):
            await agent.finalize_run_with_greedy_ack(
                run_id="run_unreconciled",
                conversation=_conversation(),
                end_reason="service_not_available",
                primary="complete",
                failure_reason="complete callback failed after scenario execution",
            )

        assert recovery_path.exists()
        lines = recovery_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["run_id"] == "run_unreconciled"
        assert payload["preferred_finalizer"] == "complete"
        assert payload["end_reason"] == "service_not_available"

    async def test_fail_primary_passes_loop_guard_payload(self, monkeypatch):
        complete_mock = AsyncMock()
        fail_mock = AsyncMock()
        monkeypatch.setattr(agent, "complete_run", complete_mock)
        monkeypatch.setattr(agent, "fail_run_with_details", fail_mock)

        loop_guard = {
            "guard": "per_turn_loop_limit",
            "turn_id": "t1",
            "visit": 2,
            "max_visits": 1,
            "effective_cap": 50,
        }
        result = await agent.finalize_run_with_greedy_ack(
            run_id="run_loop_guard",
            conversation=_conversation(),
            end_reason="per_turn_loop_limit",
            primary="fail",
            failure_reason="Turn 't1' exceeded max_visits=1",
            failure_loop_guard=loop_guard,
        )

        assert result == "fail"
        complete_mock.assert_not_awaited()
        fail_mock.assert_awaited_once()
        call_kwargs = fail_mock.await_args.kwargs
        assert call_kwargs["loop_guard"] == loop_guard


class TestLoopGuardPayload:
    def test_build_loop_guard_payload_from_loop_error(self):
        exc = HarnessLoopError(
            turn_id="t1_open",
            visit=2,
            max_visits=1,
            effective_cap=40,
        )
        payload = agent._build_loop_guard_payload(exc)
        assert payload == {
            "guard": "per_turn_loop_limit",
            "turn_id": "t1_open",
            "visit": 2,
            "max_visits": 1,
            "effective_cap": 40,
        }

    def test_build_loop_guard_payload_from_max_turns_error(self):
        exc = HarnessMaxTurnsError(
            effective_cap=25,
            turn_id="t_retry",
            visit=7,
        )
        payload = agent._build_loop_guard_payload(exc)
        assert payload == {
            "guard": "max_turns_reached",
            "effective_cap": 25,
            "turn_id": "t_retry",
            "visit": 7,
        }


class TestTraceContext:
    def test_trace_carrier_from_room_metadata_extracts_w3c_fields(self):
        carrier = agent._trace_carrier_from_room_metadata(
            {
                "run_id": "run_1",
                "traceparent": " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 ",
                "tracestate": " vendor=test ",
            }
        )
        assert carrier == {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        }

    def test_trace_carrier_from_room_metadata_ignores_missing_fields(self):
        assert agent._trace_carrier_from_room_metadata({"run_id": "run_1"}) == {}


class _FakeRoom:
    def __init__(self, metadata: str) -> None:
        self.metadata = metadata
        self.name = "room-test"


class _FakeCtx:
    def __init__(self, metadata: str) -> None:
        self.room = _FakeRoom(metadata)
        self._connected = False

    async def connect(self) -> None:
        self._connected = True


class TestHeartbeatLifecycle:
    async def test_entrypoint_stops_heartbeat_task_after_terminal_ack(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-heartbeat-lifecycle",
                "scenario_id": "scenario-1",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)

        monkeypatch.setattr(settings, "run_heartbeat_enabled", True)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=object()))
        monkeypatch.setattr(agent, "run_scenario", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            agent,
            "finalize_run_with_greedy_ack",
            AsyncMock(return_value="complete"),
        )

        heartbeat_stopped = asyncio.Event()

        async def _fake_pump(
            *,
            run_id: str,
            stop_event,
            send_heartbeat_fn,
            interval_s: float,
            jitter_s: float,
            logger_obj,
        ) -> None:
            del run_id, send_heartbeat_fn, interval_s, jitter_s, logger_obj
            await stop_event.wait()
            heartbeat_stopped.set()

        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", _fake_pump)
        monkeypatch.setattr(agent, "post_run_heartbeat", AsyncMock())

        await agent.entrypoint(ctx)

        assert ctx._connected is True
        assert heartbeat_stopped.is_set()

    async def test_entrypoint_cancelled_run_attempts_fail_callback(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-cancelled",
                "scenario_id": "scenario-1",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)

        monkeypatch.setattr(settings, "run_heartbeat_enabled", False)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=object()))

        async def _cancelled_run_scenario(*args, **kwargs):
            del args, kwargs
            raise asyncio.CancelledError()

        monkeypatch.setattr(agent, "run_scenario", _cancelled_run_scenario)
        finalizer = AsyncMock(return_value="fail")
        monkeypatch.setattr(agent, "finalize_run_with_greedy_ack", finalizer)

        with pytest.raises(asyncio.CancelledError):
            await agent.entrypoint(ctx)

        finalizer.assert_awaited_once()
        kwargs = finalizer.await_args.kwargs
        assert kwargs["run_id"] == "run-cancelled"
        assert kwargs["primary"] == "fail"
        assert kwargs["end_reason"] == "service_not_available"

    async def test_entrypoint_heartbeat_uses_runtime_diagnostics(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-heartbeat-diagnostics",
                "scenario_id": "scenario-1",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)
        state_ready = asyncio.Event()

        monkeypatch.setattr(settings, "run_heartbeat_enabled", True)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=object()))

        async def _fake_run_scenario(
            room,
            scenario,
            run_id,
            *,
            tenant_id,
            heartbeat_state_callback=None,
        ):
            del room, scenario, run_id, tenant_id
            if heartbeat_state_callback is not None:
                heartbeat_state_callback(4, "awaiting_bot")
            state_ready.set()
            await asyncio.sleep(0.01)
            return []

        monkeypatch.setattr(agent, "run_scenario", _fake_run_scenario)
        monkeypatch.setattr(
            agent,
            "finalize_run_with_greedy_ack",
            AsyncMock(return_value="complete"),
        )
        post_hb_mock = AsyncMock()
        monkeypatch.setattr(agent, "post_run_heartbeat", post_hb_mock)

        async def _fake_pump(
            *,
            run_id: str,
            stop_event,
            send_heartbeat_fn,
            interval_s: float,
            jitter_s: float,
            logger_obj,
        ) -> None:
            del run_id, stop_event, interval_s, jitter_s, logger_obj
            await state_ready.wait()
            await send_heartbeat_fn(1, datetime.now(UTC))

        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", _fake_pump)

        await agent.entrypoint(ctx)

        post_hb_mock.assert_awaited()
        kwargs = post_hb_mock.await_args.kwargs
        assert kwargs["turn_number"] == 4
        assert kwargs["listener_state"] == "awaiting_bot"

    async def test_entrypoint_attaches_and_detaches_trace_context(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-trace-context",
                "scenario_id": "scenario-1",
                "tenant_id": "default",
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            }
        )
        ctx = _FakeCtx(metadata)

        monkeypatch.setattr(settings, "run_heartbeat_enabled", False)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=object()))
        monkeypatch.setattr(agent, "run_scenario", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            agent,
            "finalize_run_with_greedy_ack",
            AsyncMock(return_value="complete"),
        )
        captured: dict[str, object] = {}

        def _fake_attach(meta: dict[str, object]) -> str:
            captured["metadata"] = meta
            return "ctx-token"

        # detach_trace_context is synchronous; use simple callable for assertions.
        detach_called: list[object] = []

        def _fake_detach(token: object | None) -> None:
            detach_called.append(token)

        monkeypatch.setattr(agent, "_attach_trace_context_from_room_metadata", _fake_attach)
        monkeypatch.setattr(agent, "detach_trace_context", _fake_detach)
        monkeypatch.setattr(agent, "post_run_heartbeat", AsyncMock())
        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", AsyncMock())

        await agent.entrypoint(ctx)

        assert json.loads(metadata).items() <= captured["metadata"].items()
        assert detach_called == ["ctx-token"]

    async def test_entrypoint_ai_materializes_dataset_turn(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-ai-materialize",
                "scenario_id": "scenario-ai-1",
                "scenario_kind": "ai",
                "ai_dataset_input": "I need to reschedule my booking to Friday morning.",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)

        base_scenario = ScenarioDefinition(
            id="scenario-ai-1",
            name="AI Scenario Base",
            type=ScenarioType.GOLDEN_PATH,
            bot=BotConfig(endpoint="sip:bot@example.com"),
            turns=[
                Turn(id="t1", text="legacy turn one"),
                Turn(id="t2", text="legacy turn two"),
            ],
        )

        monkeypatch.setattr(settings, "run_heartbeat_enabled", False)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=base_scenario))

        captured: dict[str, object] = {}

        async def _fake_run_scenario(
            room,
            scenario,
            run_id,
            *,
            tenant_id,
            heartbeat_state_callback=None,
        ):
            del room, run_id, tenant_id, heartbeat_state_callback
            captured["scenario"] = scenario
            return []

        monkeypatch.setattr(agent, "run_scenario", _fake_run_scenario)
        monkeypatch.setattr(
            agent,
            "finalize_run_with_greedy_ack",
            AsyncMock(return_value="complete"),
        )
        monkeypatch.setattr(agent, "post_run_heartbeat", AsyncMock())
        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", AsyncMock())

        await agent.entrypoint(ctx)

        runtime_scenario = captured["scenario"]
        assert isinstance(runtime_scenario, ScenarioDefinition)
        assert len(runtime_scenario.turns) == 1
        assert runtime_scenario.turns[0].id == "ai_record_input"
        assert runtime_scenario.turns[0].content.text == "I need to reschedule my booking to Friday morning."

    async def test_entrypoint_ai_missing_dataset_input_sets_ai_error_code(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-ai-missing-context",
                "scenario_id": "scenario-ai-2",
                "scenario_kind": "ai",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)

        base_scenario = ScenarioDefinition(
            id="scenario-ai-2",
            name="AI Scenario Base",
            type=ScenarioType.GOLDEN_PATH,
            bot=BotConfig(endpoint="sip:bot@example.com"),
            turns=[Turn(id="t1", text="legacy turn")],
        )

        monkeypatch.setattr(settings, "run_heartbeat_enabled", False)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=base_scenario))
        monkeypatch.setattr(agent, "run_scenario", AsyncMock(return_value=[]))
        finalizer = AsyncMock(return_value="fail")
        monkeypatch.setattr(agent, "finalize_run_with_greedy_ack", finalizer)
        monkeypatch.setattr(agent, "post_run_heartbeat", AsyncMock())
        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", AsyncMock())

        await agent.entrypoint(ctx)

        finalizer.assert_awaited_once()
        kwargs = finalizer.await_args.kwargs
        assert kwargs["primary"] == "fail"
        assert kwargs["failure_error_code"] == "ai_caller_unavailable"

    async def test_entrypoint_passes_run_metadata_when_runner_accepts_it(self, monkeypatch):
        metadata = json.dumps(
            {
                "run_id": "run-ai-metadata-forward",
                "scenario_id": "scenario-ai-3",
                "scenario_kind": "ai",
                "ai_dataset_input": "Need to update contact details.",
                "tenant_id": "default",
            }
        )
        ctx = _FakeCtx(metadata)

        base_scenario = ScenarioDefinition(
            id="scenario-ai-3",
            name="AI Scenario Base",
            type=ScenarioType.GOLDEN_PATH,
            bot=BotConfig(endpoint="sip:bot@example.com"),
            turns=[Turn(id="t1", text="legacy turn")],
        )
        monkeypatch.setattr(settings, "run_heartbeat_enabled", False)
        monkeypatch.setattr(agent, "fetch_scenario", AsyncMock(return_value=base_scenario))

        captured: dict[str, object] = {}

        async def _fake_run_scenario(
            room,
            scenario,
            run_id,
            *,
            tenant_id,
            heartbeat_state_callback=None,
            run_metadata=None,
        ):
            del room, scenario, run_id, tenant_id, heartbeat_state_callback
            captured["run_metadata"] = run_metadata
            return []

        monkeypatch.setattr(agent, "run_scenario", _fake_run_scenario)
        monkeypatch.setattr(
            agent,
            "finalize_run_with_greedy_ack",
            AsyncMock(return_value="complete"),
        )
        monkeypatch.setattr(agent, "post_run_heartbeat", AsyncMock())
        monkeypatch.setattr(agent._heartbeat, "heartbeat_pump", AsyncMock())

        await agent.entrypoint(ctx)

        forwarded = captured["run_metadata"]
        assert isinstance(forwarded, dict)
        assert forwarded.get("scenario_kind") == "ai"
        assert forwarded.get("ai_dataset_input") == "Need to update contact details."
