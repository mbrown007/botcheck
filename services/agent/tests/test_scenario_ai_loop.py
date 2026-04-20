from __future__ import annotations

import asyncio
import logging
from itertools import chain, repeat
from unittest.mock import AsyncMock

import pytest
from src.scenario_ai_loop import execute_ai_scenario_loop
from src.scenario_kind import AI_RUNTIME_TAG

from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn


class _FakeEvent:
    frame = object()


class _FakeChunked:
    def __init__(self) -> None:
        self._yielded = False

    async def __aenter__(self) -> "_FakeChunked":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def __aiter__(self) -> "_FakeChunked":
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return _FakeEvent()


class _FakeTTS:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str, **_kwargs) -> _FakeChunked:
        self.calls.append(text)
        return _FakeChunked()


class _FakeAudioSource:
    def __init__(self) -> None:
        self.frames: list[object] = []

    async def capture_frame(self, frame: object) -> None:
        self.frames.append(frame)


class _FakeBotListener:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def listen(
        self,
        *,
        timeout_s: float,
        merge_window_s: float,
        stt_endpointing_ms: int,
        listen_for_s: float | None = None,
        preview_callback=None,
    ) -> str:
        del timeout_s, merge_window_s, stt_endpointing_ms, preview_callback
        if not self._responses:
            return "(timeout)"
        return self._responses.pop(0)


class _FakeMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float | None]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def observe(self, value: float) -> None:
        self.calls.append((dict(self._labels), value))

    def inc(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))


def _ai_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-ai-loop",
        name="AI Loop",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@example.com"),
        tags=[AI_RUNTIME_TAG],
        turns=[
            Turn(
                id="ai_record_input",
                speaker="harness",
                text="I need to reschedule my appointment.",
                wait_for_response=True,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_runs_multiple_turns_until_bot_wraps_up():
    scenario = _ai_scenario()
    tts = _FakeTTS()
    audio_source = _FakeAudioSource()
    bot_listener = _FakeBotListener(
        responses=[
            "Sure, what day works for you?",
            "Friday morning is available. Anything else I can help with?",
        ]
    )
    report_turn = AsyncMock()

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
            },
        )(),
        bot_listener=bot_listener,
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=report_turn,
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "caller_opens"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=0.0,
    )

    assert turn_number == 4
    assert len(conversation) == 4
    assert [turn.speaker for turn in conversation] == ["harness", "bot", "harness", "bot"]
    assert conversation[0].text == "I need to reschedule my appointment."
    assert "next step" in conversation[2].text.lower() or "that's right" in conversation[2].text.lower()
    assert report_turn.await_count == 4
    assert len(tts.calls) == 2


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_uses_llm_generator_when_enabled():
    scenario = _ai_scenario()
    tts = _FakeTTS()
    audio_source = _FakeAudioSource()
    bot_listener = _FakeBotListener(
        responses=[
            "Can you share the reference number?",
            "Perfect, your request is submitted. Thanks for calling.",
        ]
    )
    report_turn = AsyncMock()
    generator = AsyncMock(side_effect=["Reference is 4477.", None])

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-llm",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=bot_listener,
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=report_turn,
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_scenario_objective": "reschedule and confirm details",
            "ai_opening_strategy": "caller_opens",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=generator,
        call_started_monotonic=0.0,
    )

    assert turn_number == 4
    assert len(conversation) == 4
    assert generator.await_count == 2
    assert conversation[2].text == "Reference is 4477."


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_waits_for_bot_greeting_before_opening():
    """After bot greeting the harness speaks the dataset input then the LLM drives
    subsequent turns. When the bot signals end-of-call the loop stops."""
    scenario = _ai_scenario()
    tts = _FakeTTS()
    audio_source = _FakeAudioSource()
    bot_listener = _FakeBotListener(
        responses=[
            "Hello, thanks for calling. How can I help today?",
            # Goodbye signal causes the heuristic to return None → loop ends.
            "I've rescheduled your appointment. Have a great day, goodbye!",
        ]
    )
    report_turn = AsyncMock()

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-wait",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
            },
        )(),
        bot_listener=bot_listener,
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=report_turn,
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=0.0,
    )

    assert turn_number == 3
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot"]
    assert conversation[0].text == "Hello, thanks for calling. How can I help today?"
    assert conversation[1].text == "I need to reschedule my appointment."


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_records_dataset_latency_breakdown(monkeypatch, caplog):
    reply_latency = _FakeMetric()
    decision_latency = _FakeMetric()
    llm_start_gap = _FakeMetric()
    decision_to_playback = _FakeMetric()
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_REPLY_LATENCY_SECONDS", reply_latency)
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_DECISION_LATENCY_SECONDS", decision_latency)
    monkeypatch.setattr(
        "src.scenario_ai_loop.AI_CALLER_LLM_REQUEST_START_GAP_SECONDS",
        llm_start_gap,
    )
    monkeypatch.setattr(
        "src.scenario_ai_loop.AI_CALLER_DECISION_TO_PLAYBACK_START_GAP_SECONDS",
        decision_to_playback,
    )
    monotonic_values = chain((100.30, 100.50, 100.70), repeat(100.70))
    monkeypatch.setattr("src.scenario_ai_loop.time.monotonic", lambda: next(monotonic_values))
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    bot_turns = iter(
        [
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_initial_bot",
                    "turn_number": 1,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 250,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_record_input_bot",
                    "turn_number": 3,
                    "speaker": "bot",
                    "text": "(timeout)",
                    "audio_start_ms": 900,
                    "audio_end_ms": 1200,
                },
            )(),
        ]
    )

    async def _fake_listen_bot_turn(**_kwargs):
        return next(bot_turns)

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    scenario = _ai_scenario()
    caplog.set_level(logging.INFO, logger="test.ai_loop")

    await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-latency",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=100.0,
    )

    assert reply_latency.calls[0][0]["opening_strategy"] == "wait_for_bot_greeting"
    assert reply_latency.calls[0][0]["source"] == "dataset_input"
    assert reply_latency.calls[0][0]["scenario_kind"] == "ai"
    assert reply_latency.calls[0][1] == pytest.approx(0.25)
    assert decision_latency.calls[0][0]["source"] == "dataset_input"
    assert decision_latency.calls[0][1] == pytest.approx(0.05)
    assert decision_to_playback.calls[0][1] == pytest.approx(0.20)
    assert llm_start_gap.calls == []
    assert "ai_turn_latency run_id=run-ai-loop-latency" in caplog.text
    assert "bot_to_decision_s=0.050" in caplog.text


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_records_llm_latency_breakdown(monkeypatch, caplog):
    reply_latency = _FakeMetric()
    decision_latency = _FakeMetric()
    llm_start_gap = _FakeMetric()
    decision_to_playback = _FakeMetric()
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_REPLY_LATENCY_SECONDS", reply_latency)
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_DECISION_LATENCY_SECONDS", decision_latency)
    monkeypatch.setattr(
        "src.scenario_ai_loop.AI_CALLER_LLM_REQUEST_START_GAP_SECONDS",
        llm_start_gap,
    )
    monkeypatch.setattr(
        "src.scenario_ai_loop.AI_CALLER_DECISION_TO_PLAYBACK_START_GAP_SECONDS",
        decision_to_playback,
    )
    monotonic_values = chain((100.22, 100.52, 100.72, 100.90), repeat(100.90))
    monkeypatch.setattr("src.scenario_ai_loop.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", AsyncMock())
    generator = AsyncMock(return_value="Reference is 4477.")

    bot_turns = iter(
        [
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_initial_bot",
                    "turn_number": 1,
                    "speaker": "bot",
                    "text": "Can you share the reference number?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 200,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_record_input_bot",
                    "turn_number": 3,
                    "speaker": "bot",
                    "text": "(timeout)",
                    "audio_start_ms": 950,
                    "audio_end_ms": 1200,
                },
            )(),
        ]
    )

    async def _fake_listen_bot_turn(**_kwargs):
        return next(bot_turns)

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)
    caplog.set_level(logging.INFO, logger="test.ai_loop")

    await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-loop-llm-latency",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=generator,
        call_started_monotonic=100.0,
    )

    assert llm_start_gap.calls[0][0]["opening_strategy"] == "wait_for_bot_greeting"
    assert llm_start_gap.calls[0][0]["scenario_kind"] == "ai"
    assert llm_start_gap.calls[0][1] == pytest.approx(0.02)
    assert decision_latency.calls[0][0]["source"] == "llm"
    assert decision_latency.calls[0][1] == pytest.approx(0.32)
    assert decision_to_playback.calls[0][1] == pytest.approx(0.20)
    assert reply_latency.calls[0][1] == pytest.approx(0.519)
    assert "ai_turn_latency run_id=run-ai-loop-llm-latency" in caplog.text
    assert "bot_to_llm_start_s=0.020" in caplog.text


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_records_preview_events_when_enabled(
    monkeypatch,
    caplog,
):
    preview_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_PREVIEW_EVENTS_TOTAL", preview_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", AsyncMock())

    async def _fake_listen_bot_turn(**kwargs):
        preview_callback = kwargs.get("preview_callback")
        if preview_callback is not None and kwargs.get("turn_id") == "ai_initial_bot":
            await preview_callback("Hello", "interim")
            await preview_callback("Hello, thanks for calling.", "final")
        return type(
            "Turn",
            (),
            {
                "turn_id": str(kwargs["turn_id"]),
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 0,
                "audio_end_ms": 300,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)
    caplog.set_level(logging.DEBUG, logger="test.ai_loop")

    await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-preview-events",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
                "ai_voice_preview_events_enabled": True,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=100.0,
    )

    assert preview_metric.calls == [
        ({"event_type": "interim", "scenario_kind": "ai"}, None),
        ({"event_type": "final", "scenario_kind": "ai"}, None),
    ]
    assert "ai_bot_preview run_id=run-ai-preview-events event_type=interim text=Hello" in caplog.text
    assert "ai_bot_preview run_id=run-ai-preview-events event_type=final text=Hello, thanks for calling." in caplog.text


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_commits_speculative_plan_when_preview_matches(
    monkeypatch,
):
    speculative_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_SPECULATIVE_PLANS_TOTAL", speculative_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", AsyncMock())

    async def _generator(**kwargs):
        await asyncio.sleep(0)
        return "Reference is 4477."

    async def _fake_listen_bot_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            if preview_callback is not None:
                await preview_callback("Can you share the reference", "interim")
                await asyncio.sleep(0)
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "Can you share the reference number?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 600,
                "audio_end_ms": 900,
            },
        )()

    generator = AsyncMock(side_effect=_generator)
    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, _turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-speculative-commit",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=generator,
        call_started_monotonic=100.0,
    )

    assert generator.await_count == 1
    assert conversation[1].text == "Reference is 4477."
    assert speculative_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "committed", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_discards_speculative_plan_when_preview_diverges(
    monkeypatch,
):
    speculative_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_SPECULATIVE_PLANS_TOTAL", speculative_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", AsyncMock())

    async def _generator(**kwargs):
        await asyncio.sleep(0)
        last_bot_text = str(kwargs["last_bot_text"])
        if "booking code" in last_bot_text.lower():
            return "Speculative wrong answer."
        return "Final correct answer."

    async def _fake_listen_bot_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            if preview_callback is not None:
                await preview_callback("Can you share the booking code", "interim")
                await asyncio.sleep(0)
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "I can reschedule that for you right now.",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 600,
                "audio_end_ms": 900,
            },
        )()

    generator = AsyncMock(side_effect=_generator)
    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, _turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-speculative-discard",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=generator,
        call_started_monotonic=100.0,
    )

    assert generator.await_count == 2
    assert conversation[1].text == "Final correct answer."
    assert speculative_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "discarded", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_triggers_fast_ack_on_slow_initial_llm(
    monkeypatch,
):
    fast_ack_metric = _FakeMetric()
    decision_latency = _FakeMetric()
    reply_latency = _FakeMetric()
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_DECISION_LATENCY_SECONDS", decision_latency)
    monkeypatch.setattr("src.scenario_ai_loop.AI_CALLER_REPLY_LATENCY_SECONDS", reply_latency)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    cancelled = asyncio.Event()

    async def _slow_generator(**_kwargs):
        try:
            await asyncio.sleep(999)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    bot_turns = iter(
        [
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_initial_bot",
                    "turn_number": 1,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 200,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_record_input_bot",
                    "turn_number": 3,
                    "speaker": "bot",
                    "text": "(timeout)",
                    "audio_start_ms": 800,
                    "audio_end_ms": 1000,
                },
            )(),
        ]
    )

    async def _fake_listen_bot_turn(**_kwargs):
        return next(bot_turns)

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-fast-ack",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_fast_ack_enabled": True,
                "ai_voice_fast_ack_trigger_s": 0.01,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Reschedule and confirm next steps.",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_slow_generator),
        call_started_monotonic=0.0,
    )

    assert turn_number == 3
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot"]
    assert conversation[1].text == "I need to reschedule my appointment."
    assert (
        play_audio.await_args.kwargs["turn_def"].content.text
        == "I need to reschedule my appointment."
    )
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
    assert decision_latency.calls[0][0]["source"] == "fast_ack"
    assert reply_latency.calls[0][0]["source"] == "fast_ack"
    assert cancelled.is_set() is True


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_skips_fast_ack_when_objective_mentions_opening(
    monkeypatch,
):
    fast_ack_metric = _FakeMetric()
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    bot_turns = iter(
        [
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_initial_bot",
                    "turn_number": 1,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 200,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_record_input_bot",
                    "turn_number": 3,
                    "speaker": "bot",
                    "text": "(timeout)",
                    "audio_start_ms": 800,
                    "audio_end_ms": 1000,
                },
            )(),
        ]
    )

    async def _fake_listen_bot_turn(**_kwargs):
        return next(bot_turns)

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)
    generator = AsyncMock(return_value="Real generated opener.")

    conversation, _turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-fast-ack-skip",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_fast_ack_enabled": True,
                "ai_voice_fast_ack_trigger_s": 0.01,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Evaluate caller opening quality and silence handling.",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=generator,
        call_started_monotonic=0.0,
    )

    assert conversation[1].text == "Real generated opener."
    assert play_audio.await_args.kwargs["turn_def"].content.text == "Real generated opener."
    assert fast_ack_metric.calls == []


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_triggers_heuristic_fast_ack_on_slow_followup_llm(
    monkeypatch,
):
    fast_ack_metric = _FakeMetric()
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    second_call_cancelled = asyncio.Event()

    async def _generator(**kwargs):
        last_bot_text = str(kwargs["last_bot_text"])
        if "how can i help today" in last_bot_text.lower():
            return "I need to reschedule my appointment."
        try:
            await asyncio.sleep(999)
        except asyncio.CancelledError:
            second_call_cancelled.set()
            raise

    bot_turns = iter(
        [
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_initial_bot",
                    "turn_number": 1,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 200,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_record_input_bot",
                    "turn_number": 3,
                    "speaker": "bot",
                    "text": "Friday morning is available. Can you confirm your email address?",
                    "audio_start_ms": 800,
                    "audio_end_ms": 1000,
                },
            )(),
            type(
                "Turn",
                (),
                {
                    "turn_id": "ai_followup_1_bot",
                    "turn_number": 5,
                    "speaker": "bot",
                    "text": "(timeout)",
                    "audio_start_ms": 1400,
                    "audio_end_ms": 1600,
                },
            )(),
        ]
    )

    async def _fake_listen_bot_turn(**_kwargs):
        return next(bot_turns)

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-fast-ack-heuristic",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_fast_ack_enabled": True,
                "ai_voice_fast_ack_trigger_s": 0.01,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Reschedule and confirm next steps.",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=0.0,
    )

    assert turn_number == 5
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot", "harness", "bot"]
    assert conversation[3].text == "Thanks, can you confirm the final next step before we end the call?"
    assert (
        play_audio.await_args_list[-1].kwargs["turn_def"].content.text
        == "Thanks, can you confirm the final next step before we end the call?"
    )
    assert fast_ack_metric.calls == [
        (
            {
                "source": "heuristic",
                "opening_strategy": "wait_for_bot_greeting",
                "scenario_kind": "ai",
            },
            None,
        )
    ]
    assert second_call_cancelled.is_set() is True


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_commits_initial_early_playback(
    monkeypatch,
):
    early_metric = _FakeMetric()
    play_audio = AsyncMock(
        return_value=type(
            "_Playback",
            (),
            {"completed": True, "cancelled": False, "source": "live"},
        )()
    )
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_EARLY_PLAYBACK_TOTAL", early_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    async def _generator(**_kwargs):
        await asyncio.sleep(0)
        return "Reference is 4477."

    async def _fake_listen_bot_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            if preview_callback is not None:
                await preview_callback("Can you share the reference number?", "interim")
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await preview_callback("Can you share the reference number?", "final")
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "Can you share the reference number?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 600,
                "audio_end_ms": 900,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-early-playback-commit",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "ai_voice_early_playback_enabled": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=100.0,
    )

    assert turn_number == 3
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot"]
    assert conversation[1].text == "Reference is 4477."
    assert play_audio.await_count == 1
    assert early_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "committed", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_suppresses_stale_initial_early_playback(
    monkeypatch,
):
    early_metric = _FakeMetric()

    async def _play_audio(**kwargs):
        cancel_event = kwargs.get("cancel_event")
        if cancel_event is not None:
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=0.05)
                return type(
                    "_Playback",
                    (),
                    {"completed": False, "cancelled": True, "source": "live"},
                )()
            except asyncio.TimeoutError:
                return type(
                    "_Playback",
                    (),
                    {"completed": True, "cancelled": False, "source": "live"},
                )()
        return type(
            "_Playback",
            (),
            {"completed": True, "cancelled": False, "source": "live"},
        )()

    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_EARLY_PLAYBACK_TOTAL", early_metric)
    play_audio = AsyncMock(side_effect=_play_audio)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    async def _generator(**kwargs):
        await asyncio.sleep(0)
        last_bot_text = str(kwargs["last_bot_text"])
        if "reference number" in last_bot_text.lower():
            return "Speculative wrong answer."
        return "Final correct answer."

    async def _fake_listen_bot_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            if preview_callback is not None:
                await preview_callback("Can you share the reference number?", "interim")
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await preview_callback("Can you share the reference number?", "final")
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "I can reschedule that for you right now.",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 600,
                "audio_end_ms": 900,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-early-playback-stale",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "ai_voice_early_playback_enabled": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=100.0,
    )

    assert turn_number == 3
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot"]
    assert conversation[1].text == "Final correct answer."
    assert play_audio.await_count == 2
    assert early_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "stale_suppressed", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_commits_follow_up_early_playback(
    monkeypatch,
):
    early_metric = _FakeMetric()
    play_audio = AsyncMock(
        return_value=type(
            "_Playback",
            (),
            {"completed": True, "cancelled": False, "source": "live"},
        )()
    )
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_EARLY_PLAYBACK_TOTAL", early_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    async def _generator(**kwargs):
        await asyncio.sleep(0)
        last_bot_text = str(kwargs["last_bot_text"])
        if "how can i help today" in last_bot_text.lower():
            return "I need to reschedule my appointment."
        return "Friday morning works for me."

    async def _fake_listen_bot_turn(**kwargs):
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        if turn_id == "ai_record_input_bot":
            if preview_callback is not None:
                await preview_callback("What day works best for you?", "interim")
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await preview_callback("What day works best for you?", "final")
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "What day works best for you?",
                    "audio_start_ms": 700,
                    "audio_end_ms": 1000,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 1200,
                "audio_end_ms": 1500,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-followup-early-playback",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "ai_voice_early_playback_enabled": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=100.0,
    )

    assert turn_number == 5
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot", "harness", "bot"]
    assert conversation[3].text == "Friday morning works for me."
    assert play_audio.await_count == 2
    assert early_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "committed", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_ignores_stale_preview_from_previous_epoch(
    monkeypatch,
):
    early_metric = _FakeMetric()
    play_audio = AsyncMock(
        return_value=type(
            "_Playback",
            (),
            {"completed": True, "cancelled": False, "source": "live"},
        )()
    )
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_EARLY_PLAYBACK_TOTAL", early_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    late_preview_task: asyncio.Task | None = None

    async def _generator(**kwargs):
        await asyncio.sleep(0)
        last_bot_text = str(kwargs["last_bot_text"])
        if "how can i help today" in last_bot_text.lower():
            return "I need to reschedule my appointment."
        return "Friday morning works for me."

    async def _fake_listen_bot_turn(**kwargs):
        nonlocal late_preview_task
        turn_id = str(kwargs["turn_id"])
        preview_callback = kwargs.get("preview_callback")
        if turn_id == "ai_initial_bot":
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How can I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 300,
                },
            )()
        if turn_id == "ai_record_input_bot":
            if preview_callback is not None:
                async def _late_preview():
                    await asyncio.sleep(0)
                    await preview_callback("STALE callback text", "final")

                late_preview_task = asyncio.create_task(_late_preview())
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "What day works best for you?",
                    "audio_start_ms": 700,
                    "audio_end_ms": 1000,
                },
            )()
        if turn_id == "ai_followup_1_bot":
            preview_callback = kwargs.get("preview_callback")
            if preview_callback is not None:
                await preview_callback("Which slot suits you?", "interim")
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await preview_callback("Which slot suits you?", "final")
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": int(kwargs["turn_number"]),
                    "speaker": "bot",
                    "text": "Which slot suits you?",
                    "audio_start_ms": 1200,
                    "audio_end_ms": 1500,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": int(kwargs["turn_number"]),
                "speaker": "bot",
                "text": "(timeout)",
                "audio_start_ms": 1700,
                "audio_end_ms": 1900,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-ai-early-playback-epoch-guard",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": True,
                "ai_voice_preview_events_enabled": True,
                "ai_voice_speculative_planning_enabled": True,
                "ai_voice_speculative_min_preview_chars": 10,
                "ai_voice_early_playback_enabled": True,
                "openai_api_key": "sk-test",
                "ai_caller_model": "gpt-4o-mini",
                "ai_caller_timeout_s": 4.0,
                "ai_caller_api_base_url": "https://api.openai.com/v1",
                "ai_caller_max_context_turns": 8,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=100.0,
    )

    if late_preview_task is not None:
        await late_preview_task

    assert turn_number == 7
    assert [turn.speaker for turn in conversation] == ["bot", "harness", "bot", "harness", "bot", "harness", "bot"]
    assert conversation[3].text == "Friday morning works for me."
    assert conversation[5].text == "Friday morning works for me."
    assert play_audio.await_count == 3
    assert early_metric.calls == [
        ({"outcome": "started", "scenario_kind": "ai"}, None),
        ({"outcome": "committed", "scenario_kind": "ai"}, None),
    ]


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_suppresses_followup_fast_ack_for_opening_objective(
    monkeypatch,
):
    """Fast-ack is suppressed on follow-up turns when the objective mentions an opening marker.

    _fast_ack_allowed() returns False → heuristic_fast_ack_prompt=None →
    _resolve_llm_prompt_with_fast_ack falls through to a plain LLM call.
    AI_VOICE_FAST_ACK_TOTAL must not fire.
    """
    fast_ack_metric = _FakeMetric()
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    call_count = 0

    async def _generator(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "I need to reschedule."
        return None  # signals end after first follow-up

    bot_turns = iter(
        [
            type("Turn", (), {"turn_id": "b1", "turn_number": 1, "speaker": "bot",
                              "text": "Hello! How can I help?",
                              "audio_start_ms": 0, "audio_end_ms": 200})(),
            type("Turn", (), {"turn_id": "b2", "turn_number": 3, "speaker": "bot",
                              "text": "Let me check availability for you.",
                              "audio_start_ms": 500, "audio_end_ms": 700})(),
        ]
    )

    monkeypatch.setattr(
        "src.scenario_ai_loop.listen_bot_turn",
        AsyncMock(side_effect=lambda **_: next(bot_turns)),
    )

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-no-fast-ack-opening",
        tenant_id="default",
        settings_obj=type("S", (), {
            "max_total_turns_hard_cap": 50,
            "ai_caller_use_llm": True,
            "ai_voice_fast_ack_enabled": True,
            "ai_voice_fast_ack_trigger_s": 0.01,
            "openai_api_key": "sk-test",
            "ai_caller_model": "gpt-4o-mini",
            "ai_caller_timeout_s": 4.0,
            "ai_caller_api_base_url": "https://api.openai.com/v1",
            "ai_caller_max_context_turns": 8,
        })(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            # "opening" marker → _objective_disallows_fast_ack returns True
            "ai_scenario_objective": "Evaluate call opening behavior and silence handling.",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=0.0,
    )

    assert fast_ack_metric.calls == [], "fast-ack must not fire when objective mentions opening"
    assert turn_number == 3


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_skips_fast_ack_when_bot_emits_stop_signal(
    monkeypatch,
):
    """generate_ai_followup_prompt returns None on a stop-signal bot turn.

    With fallback_prompt=None the code falls through to a plain LLM call.
    AI_VOICE_FAST_ACK_TOTAL must not fire even though fast-ack is enabled.
    """
    fast_ack_metric = _FakeMetric()
    play_audio = AsyncMock()
    monkeypatch.setattr("src.scenario_ai_loop.AI_VOICE_FAST_ACK_TOTAL", fast_ack_metric)
    monkeypatch.setattr("src.scenario_ai_loop.play_harness_turn_audio", play_audio)

    call_count = 0

    async def _generator(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "I need to reschedule."
        return None  # LLM returns nothing after bot goodbye

    bot_turns = iter(
        [
            type("Turn", (), {"turn_id": "b1", "turn_number": 1, "speaker": "bot",
                              "text": "Hello! How can I help?",
                              "audio_start_ms": 0, "audio_end_ms": 200})(),
            # Stop-signal bot turn — generate_ai_followup_prompt returns None
            type("Turn", (), {"turn_id": "b2", "turn_number": 3, "speaker": "bot",
                              "text": "Thanks for calling. Goodbye!",
                              "audio_start_ms": 500, "audio_end_ms": 700})(),
        ]
    )

    monkeypatch.setattr(
        "src.scenario_ai_loop.listen_bot_turn",
        AsyncMock(side_effect=lambda **_: next(bot_turns)),
    )

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=_ai_scenario(),
        run_id="run-stop-signal-no-fast-ack",
        tenant_id="default",
        settings_obj=type("S", (), {
            "max_total_turns_hard_cap": 50,
            "ai_caller_use_llm": True,
            "ai_voice_fast_ack_enabled": True,
            "ai_voice_fast_ack_trigger_s": 0.01,
            "openai_api_key": "sk-test",
            "ai_caller_model": "gpt-4o-mini",
            "ai_caller_timeout_s": 4.0,
            "ai_caller_api_base_url": "https://api.openai.com/v1",
            "ai_caller_max_context_turns": 8,
        })(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={
            "ai_opening_strategy": "wait_for_bot_greeting",
            "ai_scenario_objective": "Reschedule appointment.",
        },
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        ai_caller_circuit_breaker=None,
        ai_caller_generate_fn=AsyncMock(side_effect=_generator),
        call_started_monotonic=0.0,
    )

    assert fast_ack_metric.calls == [], "fast-ack must not fire on stop-signal bot turn"
    assert turn_number == 3


@pytest.mark.asyncio
async def test_execute_ai_scenario_loop_falls_through_when_bot_greeting_times_out():
    """If the bot is silent on greeting the harness still proceeds with the dataset
    input and continues until the bot signals end-of-call."""
    scenario = _ai_scenario()
    tts = _FakeTTS()
    audio_source = _FakeAudioSource()
    bot_listener = _FakeBotListener(
        responses=[
            "(timeout)",  # bot stays silent on greeting
            "I can help you reschedule. Goodbye!",  # goodbye stops the loop
        ]
    )
    report_turn = AsyncMock()

    conversation, turn_number = await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-greeting-timeout",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
            },
        )(),
        bot_listener=bot_listener,
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=report_turn,
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=0.0,
    )

    # bot=(timeout), harness=dataset_input, bot=goodbye — 3 turns total.
    assert turn_number == 3
    assert [t.speaker for t in conversation] == ["bot", "harness", "bot"]
    assert conversation[0].text == "(timeout)"
    assert conversation[1].text == "I need to reschedule my appointment."
    assert conversation[2].text == "I can help you reschedule. Goodbye!"
    assert len(tts.calls) == 1  # harness spoke once


@pytest.mark.asyncio
async def test_wait_for_bot_greeting_uses_extended_initial_listen_settings(monkeypatch):
    scenario = _ai_scenario()
    scenario.config.transcript_merge_window_s = 1.5
    scenario.config.stt_endpointing_ms = 2000

    listen_calls: list[dict[str, object]] = []

    async def _fake_listen_bot_turn(**kwargs):
        listen_calls.append(kwargs)
        turn_id = str(kwargs["turn_id"])
        turn_number = int(kwargs["turn_number"])
        if turn_id == "ai_initial_bot":
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": turn_number,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How may I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 1000,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": turn_number,
                "speaker": "bot",
                "text": "Goodbye!",
                "audio_start_ms": 1500,
                "audio_end_ms": 2200,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-initial-greeting-window",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=0.0,
    )

    assert len(listen_calls) >= 2
    initial_call = listen_calls[0]
    assert initial_call["turn_id"] == "ai_initial_bot"
    assert initial_call["merge_window_s"] == 3.0
    assert initial_call["stt_endpointing_ms"] == 3500

    follow_up_call = listen_calls[1]
    assert follow_up_call["turn_id"] == "ai_record_input_bot"
    assert follow_up_call["merge_window_s"] == 1.5
    assert follow_up_call["stt_endpointing_ms"] == 2000


@pytest.mark.asyncio
async def test_ai_voice_latency_profile_tightens_follow_up_listen_settings(monkeypatch):
    scenario = _ai_scenario()
    scenario.config.transcript_merge_window_s = 1.5
    scenario.config.stt_endpointing_ms = 2000

    listen_calls: list[dict[str, object]] = []

    async def _fake_listen_bot_turn(**kwargs):
        listen_calls.append(kwargs)
        turn_id = str(kwargs["turn_id"])
        turn_number = int(kwargs["turn_number"])
        if turn_id == "ai_initial_bot":
            return type(
                "Turn",
                (),
                {
                    "turn_id": turn_id,
                    "turn_number": turn_number,
                    "speaker": "bot",
                    "text": "Hello, thanks for calling. How may I help today?",
                    "audio_start_ms": 0,
                    "audio_end_ms": 1000,
                },
            )()
        return type(
            "Turn",
            (),
            {
                "turn_id": turn_id,
                "turn_number": turn_number,
                "speaker": "bot",
                "text": "Goodbye!",
                "audio_start_ms": 1500,
                "audio_end_ms": 2200,
            },
        )()

    monkeypatch.setattr("src.scenario_ai_loop.listen_bot_turn", _fake_listen_bot_turn)

    await execute_ai_scenario_loop(
        scenario=scenario,
        run_id="run-ai-loop-latency-profile",
        tenant_id="default",
        settings_obj=type(
            "S",
            (),
            {
                "max_total_turns_hard_cap": 50,
                "ai_caller_use_llm": False,
                "ai_voice_latency_profile_enabled": True,
                "ai_voice_latency_profile_stt_endpointing_ms": 900,
                "ai_voice_latency_profile_transcript_merge_window_s": 0.4,
            },
        )(),
        bot_listener=_FakeBotListener([]),
        audio_source=_FakeAudioSource(),
        tts=_FakeTTS(),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        report_turn_fn=AsyncMock(),
        logger_obj=logging.getLogger("test.ai_loop"),
        heartbeat_state_callback=None,
        run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
        tts_live_circuit_breaker=None,
        provider_circuit_state_callback=None,
        call_started_monotonic=0.0,
    )

    assert len(listen_calls) >= 2
    initial_call = listen_calls[0]
    assert initial_call["turn_id"] == "ai_initial_bot"
    assert initial_call["merge_window_s"] == 3.0
    assert initial_call["stt_endpointing_ms"] == 3500

    follow_up_call = listen_calls[1]
    assert follow_up_call["turn_id"] == "ai_record_input_bot"
    assert follow_up_call["merge_window_s"] == 0.4
    assert follow_up_call["stt_endpointing_ms"] == 900
