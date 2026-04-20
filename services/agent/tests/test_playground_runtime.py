from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import (
    BotConfig,
    BranchCase,
    BranchConfig,
    ScenarioDefinition,
    ScenarioType,
    Turn,
    TurnExpectation,
)

from src.playground_runtime import execute_playground_loop
from src.scenario_kind import AI_RUNTIME_TAG


class _FakeMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float | None]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def observe(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))

    def inc(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))


def _settings(**overrides):
    defaults = {
        "enable_branching_graph": True,
        "max_total_turns_hard_cap": 50,
        "branch_classifier_model": "claude-3-5-haiku-latest",
        "branch_classifier_timeout_s": 1.5,
        "ai_caller_use_llm": True,
        "ai_caller_model": "gpt-4o-mini",
        "ai_caller_timeout_s": 4.0,
        "ai_caller_api_base_url": "https://api.openai.com/v1",
        "ai_caller_max_context_turns": 8,
        "openai_api_key": "sk-test",
        "ai_voice_fast_ack_enabled": False,
        "ai_voice_fast_ack_trigger_s": 0.6,
    }
    defaults.update(overrides)
    return type("S", (), defaults)()


def _graph_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="playground-graph",
        name="Playground Graph",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="mock://playground"),
        turns=[Turn(id="t1", text="Check my account", wait_for_response=True)],
    )


def _branching_graph_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="playground-graph-branching",
        name="Playground Graph Branching",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="mock://playground"),
        turns=[
            Turn(
                id="t1",
                text="Transfer me to billing",
                wait_for_response=True,
                branching=BranchConfig(
                    default="t_done",
                    cases=[BranchCase(condition="billing", next="t_done")],
                ),
                expect=TurnExpectation(
                    transferred_to="billing",
                    no_forbidden_phrase=["forbidden"],
                ),
            ),
            Turn(id="t_done", speaker="bot"),
        ],
    )


def _ai_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="playground-ai",
        name="Playground AI",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="mock://playground"),
        tags=[AI_RUNTIME_TAG],
        turns=[Turn(id="ai_record_input", text="I need help with billing.", wait_for_response=True)],
    )


@pytest.mark.asyncio
async def test_execute_playground_loop_mock_graph_reports_turns_and_augments_prompt() -> None:
    reported: list[tuple[str, str]] = []
    captured: dict[str, object] = {}

    class _FakeMockAgent:
        def __init__(self, *, settings_obj) -> None:
            del settings_obj
            self._responses = ["Your account is active."]

        async def respond(self, system_prompt: str, history: list[dict[str, str]], turn_text: str) -> str:
            captured["system_prompt"] = system_prompt
            captured["history"] = history
            captured["turn_text"] = turn_text
            return self._responses.pop(0)

    async def _report_turn(run_id: str, turn, **_kwargs) -> None:
        reported.append((run_id, turn.text))

    conversation, turn_number = await execute_playground_loop(
        scenario=_graph_scenario(),
        run_id="run-playground-mock",
        settings_obj=_settings(),
        report_turn_fn=_report_turn,
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        fetch_run_transport_context_fn=AsyncMock(
            return_value={
                "run_id": "run-playground-mock",
                "playground_mode": "mock",
                "playground_system_prompt": "You are a calm support bot.",
                "playground_tool_stubs": {"lookup_account": {"status": "active"}},
            }
        ),
        run_metadata={"run_type": "playground", "playground_mode": "mock", "scenario_kind": "graph"},
        mock_agent_cls=_FakeMockAgent,
        post_playground_event_fn=AsyncMock(),
    )

    assert turn_number == 2
    assert [turn.text for turn in conversation] == ["Check my account", "Your account is active."]
    assert reported == [
        ("run-playground-mock", "Check my account"),
        ("run-playground-mock", "Your account is active."),
    ]
    assert "Available tool stub returns for this playground session" in str(captured["system_prompt"])
    assert "lookup_account" in str(captured["system_prompt"])
    assert captured["turn_text"] == "Check my account"
    # history must NOT contain the harness turn — it's already the final user message
    assert captured["history"] == [], "harness turn must not be duplicated in history"


@pytest.mark.asyncio
async def test_execute_playground_loop_mock_branching_emits_ordered_events() -> None:
    emitted: list[tuple[str, dict[str, object]]] = []

    class _FakeMockAgent:
        def __init__(self, *, settings_obj) -> None:
            del settings_obj
            self._responses = ["I can transfer you to billing now.", "Transferred to billing."]

        async def respond(self, system_prompt: str, history: list[dict[str, str]], turn_text: str) -> str:
            del system_prompt, history, turn_text
            return self._responses.pop(0)

    async def _post_event(run_id: str, *, event_type: str, payload: dict[str, object]) -> None:
        assert run_id == "run-playground-branching"
        emitted.append((event_type, payload))

    await execute_playground_loop(
        scenario=_branching_graph_scenario(),
        run_id="run-playground-branching",
        settings_obj=_settings(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="billing"),
        classifier_client=object(),
        fetch_run_transport_context_fn=AsyncMock(
            return_value={
                "run_id": "run-playground-branching",
                "playground_mode": "mock",
                "playground_system_prompt": "You are a routing bot.",
            }
        ),
        run_metadata={"run_type": "playground", "playground_mode": "mock", "scenario_kind": "graph"},
        mock_agent_cls=_FakeMockAgent,
        post_playground_event_fn=_post_event,
    )

    assert [event_type for event_type, _payload in emitted] == [
        "turn.start",
        "turn.response",
        "turn.start",
        "turn.response",
        "turn.branch",
        "turn.expect",
        "turn.expect",
        "turn.start",
        "turn.response",
        "run.complete",
    ]
    branch_events = [payload for event_type, payload in emitted if event_type == "turn.branch"]
    assert [payload["selected_case"] for payload in branch_events] == ["billing"]
    expect_events = [payload for event_type, payload in emitted if event_type == "turn.expect"]
    assert expect_events == [
        {"turn_id": "t1_bot", "assertion": "no_forbidden_phrase", "passed": True, "detail": ["forbidden"]},
        {"turn_id": "t1_bot", "assertion": "transferred_to", "passed": True, "detail": "billing"},
    ]
    assert emitted[-1][1]["summary"] == "Playground run completed after 3 turns."


@pytest.mark.asyncio
async def test_execute_playground_loop_direct_http_delegates_to_http_runtime(monkeypatch) -> None:
    direct_loop = AsyncMock(return_value=([], 0))
    direct_ai_loop = AsyncMock(return_value=([], 0))

    monkeypatch.setattr("src.playground_runtime.execute_direct_http_scenario_loop", direct_loop)
    monkeypatch.setattr("src.playground_runtime.execute_direct_http_ai_loop", direct_ai_loop)

    await execute_playground_loop(
        scenario=_graph_scenario(),
        run_id="run-playground-http",
        settings_obj=_settings(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        fetch_run_transport_context_fn=AsyncMock(
            return_value={
                "run_id": "run-playground-http",
                "playground_mode": "direct_http",
                "transport_profile_id": "dest_http",
                "endpoint": "https://bot.internal/chat",
                "headers": {},
                "direct_http_config": {},
            }
        ),
        run_metadata={"run_type": "playground", "playground_mode": "direct_http", "scenario_kind": "graph"},
        post_playground_event_fn=AsyncMock(),
    )

    direct_loop.assert_awaited_once()
    direct_ai_loop.assert_not_awaited()
    assert "event_emitter" in direct_loop.await_args.kwargs


@pytest.mark.asyncio
async def test_execute_playground_loop_mock_ai_uses_ai_caller_generator() -> None:
    reported: list[str] = []
    emitted: list[tuple[str, dict[str, object]]] = []

    class _FakeMockAgent:
        def __init__(self, *, settings_obj) -> None:
            del settings_obj
            self._responses = ["Hello, how can I help?", "I can help with that billing issue."]

        async def respond(self, system_prompt: str, history: list[dict[str, str]], turn_text: str) -> str:
            del system_prompt, history, turn_text
            return self._responses.pop(0)

    generator = AsyncMock(side_effect=["I need help with billing.", None])

    async def _report_turn(run_id: str, turn, **_kwargs) -> None:
        del run_id
        reported.append(turn.text)

    async def _post_event(run_id: str, *, event_type: str, payload: dict[str, object]) -> None:
        assert run_id == "run-playground-ai"
        emitted.append((event_type, payload))

    conversation, turn_number = await execute_playground_loop(
        scenario=_ai_scenario(),
        run_id="run-playground-ai",
        settings_obj=_settings(),
        report_turn_fn=_report_turn,
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        fetch_run_transport_context_fn=AsyncMock(
            return_value={
                "run_id": "run-playground-ai",
                "playground_mode": "mock",
                "playground_system_prompt": "You are a support bot.",
            }
        ),
        run_metadata={
            "run_type": "playground",
            "playground_mode": "mock",
            "scenario_kind": "ai",
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Resolve the billing question.",
            "ai_persona_name": "Alex",
        },
        mock_agent_cls=_FakeMockAgent,
        ai_caller_generate_fn=generator,
        post_playground_event_fn=_post_event,
    )

    assert turn_number == 3
    assert reported == [
        "Hello, how can I help?",
        "I need help with billing.",
        "I can help with that billing issue.",
    ]
    assert [turn.text for turn in conversation] == reported
    debug_events = [payload for event_type, payload in emitted if event_type.startswith("harness.")]
    assert debug_events == [
        {"transcript": "Hello, how can I help?"},
        {"selected_case": "continue", "confidence": None},
        {"summary": "Continuing based on the latest bot reply and the scenario objective."},
        {"transcript": "I can help with that billing issue."},
        {"selected_case": "end", "confidence": None},
        {"summary": "Ending because the caller objective appears satisfied."},
    ]


@pytest.mark.asyncio
async def test_execute_playground_loop_mock_ai_triggers_fast_ack_on_slow_initial_llm(monkeypatch) -> None:
    fast_ack_metric = _FakeMetric()
    emitted: list[tuple[str, dict[str, object]]] = []

    class _FakeMockAgent:
        def __init__(self, *, settings_obj) -> None:
            del settings_obj
            self._responses = ["Hello, how can I help?", "Thanks for calling. Goodbye!"]

        async def respond(self, system_prompt: str, history: list[dict[str, str]], turn_text: str) -> str:
            del system_prompt, history, turn_text
            return self._responses.pop(0)

    async def _slow_generator(**_kwargs):
        await asyncio.sleep(999)
        return "This should never be spoken."

    async def _post_event(run_id: str, *, event_type: str, payload: dict[str, object]) -> None:
        assert run_id == "run-playground-ai-fast-ack"
        emitted.append((event_type, payload))

    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)

    conversation, turn_number = await execute_playground_loop(
        scenario=_ai_scenario(),
        run_id="run-playground-ai-fast-ack",
        settings_obj=_settings(
            ai_voice_fast_ack_enabled=True,
            ai_voice_fast_ack_trigger_s=0.01,
        ),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        fetch_run_transport_context_fn=AsyncMock(
            return_value={
                "run_id": "run-playground-ai-fast-ack",
                "playground_mode": "mock",
                "playground_system_prompt": "You are a support bot.",
            }
        ),
        run_metadata={
            "run_type": "playground",
            "playground_mode": "mock",
            "scenario_kind": "ai",
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Resolve the billing question.",
            "ai_persona_name": "Alex",
        },
        mock_agent_cls=_FakeMockAgent,
        ai_caller_generate_fn=_slow_generator,
        post_playground_event_fn=_post_event,
    )

    assert turn_number == 3
    assert [turn.text for turn in conversation] == [
        "Hello, how can I help?",
        "I need help with billing.",
        "Thanks for calling. Goodbye!",
    ]
    assert fast_ack_metric.calls == [
        (
            {
                "source": "dataset_input",
                "opening_strategy": "wait_for_bot_greeting",
                "scenario_kind": "ai",
            },
            None,
        )
    ]
    assert [payload for event_type, payload in emitted if event_type == "harness.caller_reasoning"] == [
        {"summary": "Using dataset input fast-ack fallback while the caller LLM is still pending."}
    ]
