from __future__ import annotations

import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from src import scenario_loop_executor
from src import scenario_time_route as scenario_time_route_module

from botcheck_scenarios import (
    BotConfig,
    HangupBlock,
    HarnessPromptBlock,
    PromptContent,
    ScenarioDefinition,
    ScenarioType,
    TimeRouteBlock,
    Turn,
    WaitBlock,
)


@pytest.mark.asyncio
async def test_execute_scenario_loop_skips_turn_helpers_for_hangup(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="hangup-seam",
        name="hangup-seam",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            Turn(id="t1", text="Hello", wait_for_response=False),
            HangupBlock(id="t_end"),
        ],
    )

    helper_turn_ids: list[str] = []

    def _effective_turn_timeout(turn_def, _scenario):
        helper_turn_ids.append(turn_def.id)
        return 1.0

    def _effective_stt_settings(turn_def, _scenario):
        assert turn_def.id == "t1"
        return 2000, 0.5

    monkeypatch.setattr(scenario_loop_executor, "effective_turn_timeout", _effective_turn_timeout)
    monkeypatch.setattr(
        scenario_loop_executor, "effective_stt_settings", _effective_stt_settings
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_harness_prompt_block",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_bot_listen_block",
        AsyncMock(return_value=(1, "default")),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_hangup_block",
        AsyncMock(return_value=1),
    )

    conversation, turn_number = await scenario_loop_executor.execute_scenario_loop(
        scenario=scenario,
        run_id="run-1",
        tenant_id="tenant-1",
        settings_obj=SimpleNamespace(
            enable_branching_graph=False,
            max_total_turns_hard_cap=20,
            branch_classifier_model="test-model",
            branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert conversation == []
    assert turn_number == 1
    assert helper_turn_ids == ["t1"]
    scenario_loop_executor.execute_harness_prompt_block.assert_awaited_once()
    scenario_loop_executor.execute_hangup_block.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_scenario_loop_stops_at_mid_sequence_hangup(monkeypatch) -> None:
    """A hangup block mid-scenario must stop execution; the turn after it must not run."""
    scenario = ScenarioDefinition(
        id="mid-hangup",
        name="mid-hangup",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            Turn(id="t1", text="Hello", wait_for_response=False),
            HangupBlock(id="t_hangup"),
            Turn(id="t2", text="Should never execute", wait_for_response=False),
        ],
    )

    executed_turn_ids: list[str] = []

    async def _fake_harness(*, turn_def, turn_number, **_kwargs):
        executed_turn_ids.append(turn_def.id)
        return turn_number + 1

    async def _fake_hangup(*, turn_def, turn_number, **_kwargs):
        executed_turn_ids.append(turn_def.id)
        return turn_number

    monkeypatch.setattr(scenario_loop_executor, "execute_harness_prompt_block", _fake_harness)
    monkeypatch.setattr(scenario_loop_executor, "execute_hangup_block", _fake_hangup)
    monkeypatch.setattr(
        scenario_loop_executor, "execute_bot_listen_block", AsyncMock(return_value=(0, "default"))
    )

    await scenario_loop_executor.execute_scenario_loop(
        scenario=scenario,
        run_id="run-mid",
        tenant_id="tenant-1",
        settings_obj=SimpleNamespace(
            enable_branching_graph=False,
            max_total_turns_hard_cap=20,
            branch_classifier_model="test-model",
            branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert executed_turn_ids == ["t1", "t_hangup"], (
        f"Expected only t1 and t_hangup to execute, got: {executed_turn_ids}"
    )


@pytest.mark.asyncio
async def test_execute_scenario_loop_executes_wait_without_turn_helpers(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="wait-seam",
        name="wait-seam",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            WaitBlock(id="t_wait", wait_s=2.5),
        ],
    )

    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_harness_prompt_block",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_bot_listen_block",
        AsyncMock(return_value=(1, "default")),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_hangup_block",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_wait_block",
        AsyncMock(return_value=0),
    )

    conversation, turn_number = await scenario_loop_executor.execute_scenario_loop(
        scenario=scenario,
        run_id="run-wait",
        tenant_id="tenant-1",
        settings_obj=SimpleNamespace(
            enable_branching_graph=False,
            max_total_turns_hard_cap=20,
            branch_classifier_model="test-model",
            branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert conversation == []
    assert turn_number == 0
    scenario_loop_executor.execute_wait_block.assert_awaited_once()
    scenario_loop_executor.execute_harness_prompt_block.assert_not_awaited()
    scenario_loop_executor.execute_bot_listen_block.assert_not_awaited()
    scenario_loop_executor.execute_hangup_block.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_scenario_loop_preserves_sequence_across_wait_block(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="wait-sequence",
        name="wait-sequence",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            HarnessPromptBlock(
                id="t_before",
                content=PromptContent(text="Before wait"),
                listen=False,
                next="t_wait",
            ),
            WaitBlock(id="t_wait", wait_s=2.5, next="t_after"),
            HarnessPromptBlock(
                id="t_after",
                content=PromptContent(text="After wait"),
                listen=False,
                next="t_end",
            ),
            HangupBlock(id="t_end"),
        ],
    )

    executed: list[tuple[str, str, int]] = []

    async def _fake_harness(*, turn_def, turn_number, graph_traversal, **_kwargs):
        executed.append(("harness_prompt", turn_def.id, turn_number))
        if graph_traversal is not None:
            maybe_advance = graph_traversal.advance("default")
            if inspect.isawaitable(maybe_advance):
                await maybe_advance
        return turn_number + 1

    async def _fake_wait(*, turn_def, turn_number, **_kwargs):
        executed.append(("wait", turn_def.id, turn_number))
        return turn_number

    async def _fake_hangup(*, turn_def, turn_number, **_kwargs):
        executed.append(("hangup", turn_def.id, turn_number))
        return turn_number

    monkeypatch.setattr(scenario_loop_executor, "execute_harness_prompt_block", _fake_harness)
    monkeypatch.setattr(scenario_loop_executor, "execute_wait_block", _fake_wait)
    monkeypatch.setattr(scenario_loop_executor, "execute_hangup_block", _fake_hangup)
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_bot_listen_block",
        AsyncMock(return_value=(0, "default")),
    )

    conversation, turn_number = await scenario_loop_executor.execute_scenario_loop(
        scenario=scenario,
        run_id="run-wait-sequence",
        tenant_id="tenant-1",
        settings_obj=SimpleNamespace(
            enable_branching_graph=False,
            max_total_turns_hard_cap=20,
            branch_classifier_model="test-model",
            branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert conversation == []
    assert turn_number == 2
    assert executed == [
        ("harness_prompt", "t_before", 0),
        ("wait", "t_wait", 1),
        ("harness_prompt", "t_after", 1),
        ("hangup", "t_end", 2),
    ]


@pytest.mark.asyncio
async def test_execute_scenario_loop_executes_time_route_without_turn_helpers(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="time-route-seam",
        name="time-route-seam",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            TimeRouteBlock(
                id="t_route",
                timezone="UTC",
                windows=[
                    {
                        "label": "business_hours",
                        "start": "09:00",
                        "end": "17:00",
                        "next": "t_end",
                    }
                ],
                default="t_end",
            ),
            HangupBlock(id="t_end"),
        ],
    )

    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_harness_prompt_block",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_bot_listen_block",
        AsyncMock(return_value=(1, "default")),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_hangup_block",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_wait_block",
        AsyncMock(return_value=1),
    )
    async def _fake_time_route(*, graph_traversal, turn_number, **_kwargs):
        graph_traversal.advance("default")
        return turn_number

    monkeypatch.setattr(scenario_loop_executor, "execute_time_route_block", _fake_time_route)

    conversation, turn_number = await scenario_loop_executor.execute_scenario_loop(
            scenario=scenario,
            run_id="run-time-route",
            tenant_id="tenant-1",
            settings_obj=SimpleNamespace(
                enable_branching_graph=True,
                max_total_turns_hard_cap=20,
                branch_classifier_model="test-model",
                branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert conversation == []
    assert turn_number == 1
    scenario_loop_executor.execute_harness_prompt_block.assert_not_awaited()
    scenario_loop_executor.execute_bot_listen_block.assert_not_awaited()
    scenario_loop_executor.execute_hangup_block.assert_awaited_once()
    scenario_loop_executor.execute_wait_block.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_scenario_loop_routes_through_selected_time_route_arm(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="time-route-sequence",
        name="time-route-sequence",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:test@example.com"),
        turns=[
            TimeRouteBlock(
                id="t_route",
                timezone="UTC",
                windows=[
                    {
                        "label": "business_hours",
                        "start": "09:00",
                        "end": "17:00",
                        "next": "t_hours",
                    }
                ],
                default="t_default",
            ),
            HarnessPromptBlock(
                id="t_hours",
                content=PromptContent(text="Business hours path"),
                listen=False,
                next="t_end",
            ),
            HarnessPromptBlock(
                id="t_default",
                content=PromptContent(text="Default path"),
                listen=False,
                next="t_end",
            ),
            HangupBlock(id="t_end"),
        ],
    )

    executed: list[tuple[str, str, int]] = []

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 4, 13, 9, 30, tzinfo=ZoneInfo("UTC"))
            return base if tz is None else base.astimezone(tz)

    async def _fake_harness(*, turn_def, turn_number, graph_traversal, **_kwargs):
        executed.append(("harness_prompt", turn_def.id, turn_number))
        if graph_traversal is not None:
            maybe_advance = graph_traversal.advance("default")
            if inspect.isawaitable(maybe_advance):
                await maybe_advance
        return turn_number + 1

    async def _fake_hangup(*, turn_def, turn_number, **_kwargs):
        executed.append(("hangup", turn_def.id, turn_number))
        return turn_number

    monkeypatch.setattr(scenario_time_route_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(scenario_loop_executor, "execute_harness_prompt_block", _fake_harness)
    monkeypatch.setattr(scenario_loop_executor, "execute_hangup_block", _fake_hangup)
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_bot_listen_block",
        AsyncMock(return_value=(0, "default")),
    )
    monkeypatch.setattr(
        scenario_loop_executor,
        "execute_wait_block",
        AsyncMock(return_value=0),
    )

    conversation, turn_number = await scenario_loop_executor.execute_scenario_loop(
        scenario=scenario,
        run_id="run-time-route-sequence",
        tenant_id="tenant-1",
        settings_obj=SimpleNamespace(
            enable_branching_graph=True,
            max_total_turns_hard_cap=20,
            branch_classifier_model="test-model",
            branch_classifier_timeout_s=1.0,
        ),
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        classify_branch_fn=AsyncMock(return_value="default"),
        classifier_client=object(),
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert conversation == []
    assert turn_number == 1
    assert executed == [
        ("harness_prompt", "t_hours", 0),
        ("hangup", "t_end", 1),
    ]
    # The default arm must NOT have been visited — routing selected business_hours.
    assert all(block_id != "t_default" for _, block_id, _ in executed)
