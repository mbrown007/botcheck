from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import BotConfig, ConversationTurn, ScenarioDefinition, ScenarioType, Turn

from src import scenario_runner
from src.scenario_kind import AI_RUNTIME_TAG


class _FakeBotParticipant:
    identity = "bot-test"


class _FakeRecorder:
    def __init__(self, enabled: bool) -> None:
        del enabled
        self.reset_calls = 0

    def capture_frame(self, frame) -> None:
        del frame

    def reset(self) -> None:
        self.reset_calls += 1


class _FakeListener:
    def __init__(self, *_args, **_kwargs) -> None:
        self.drain_calls: list[float] = []
        return

    async def start(self) -> None:
        return

    async def drain(self, _duration_s: float) -> None:
        if not hasattr(self, "drain_calls"):
            self.drain_calls = []
        self.drain_calls.append(_duration_s)
        return

    async def stop(self) -> None:
        return


class _FakeOpenAI:
    class TTS:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs


class _FakeDeepgram:
    class STT:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs


class _FakeAzure:
    class STT:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs


class _FakeRoom:
    name = "room-ai"


def _run_context(
    *,
    settings_obj=None,
    wait_for_bot_fn=None,
    bot_listener_cls=_FakeListener,
    bot_audio_recorder_cls=_FakeRecorder,
    read_cached_turn_wav_fn=None,
    publish_cached_wav_fn=None,
    report_turn_fn=None,
    upload_run_recording_fn=None,
    classify_branch_fn=None,
    classifier_client=None,
    rtc_module=None,
    fetch_run_transport_context_fn=None,
    logger_name="test.scenario_runner",
    run_metadata=None,
    heartbeat_state_callback=None,
):
    return scenario_runner.ScenarioRunContext(
        tenant_id="default",
        settings_obj=settings_obj or _settings(),
        wait_for_bot_fn=wait_for_bot_fn or AsyncMock(return_value=_FakeBotParticipant()),
        bot_listener_cls=bot_listener_cls,
        bot_audio_recorder_cls=bot_audio_recorder_cls,
        read_cached_turn_wav_fn=read_cached_turn_wav_fn or AsyncMock(return_value=None),
        publish_cached_wav_fn=publish_cached_wav_fn or AsyncMock(),
        report_turn_fn=report_turn_fn or AsyncMock(),
        upload_run_recording_fn=upload_run_recording_fn or AsyncMock(),
        classify_branch_fn=classify_branch_fn or AsyncMock(return_value="default"),
        classifier_client=classifier_client or object(),
        livekit_api_cls=object,
        room_participant_identity_cls=object,
        rtc_module=rtc_module or object(),
        openai_module=_FakeOpenAI,
        stt_plugin_modules={"deepgram": _FakeDeepgram, "azure": _FakeAzure},
        logger_obj=logging.getLogger(logger_name),
        fetch_run_transport_context_fn=fetch_run_transport_context_fn,
        heartbeat_state_callback=heartbeat_state_callback,
        run_metadata=run_metadata,
    )


def _settings(**overrides):
    defaults = {
        "feature_ai_scenarios_enabled": True,
        "feature_stt_provider_deepgram_enabled": True,
        "feature_stt_provider_azure_enabled": False,
        "deepgram_api_key": "test-deepgram-key",
        "azure_speech_key": "",
        "azure_speech_region": "",
        "azure_speech_endpoint": "",
    }
    defaults.update(overrides)
    return type("S", (), defaults)()


def _ai_runtime_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-ai-runner",
        name="AI Runner",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@example.com"),
        tags=[AI_RUNTIME_TAG],
        turns=[Turn(id="ai_record_input", text="I need help with billing.")],
    )


def _graph_harness_first_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-graph-runner",
        name="Graph Runner",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@example.com"),
        turns=[Turn(id="t1", text="Hello there", wait_for_response=False)],
    )


@pytest.mark.asyncio
async def test_run_scenario_routes_ai_tagged_scenarios_to_ai_loop(monkeypatch):
    scenario = _ai_runtime_scenario()
    ai_loop = AsyncMock(return_value=([], 0))
    graph_loop = AsyncMock(return_value=([], 0))

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_ai_scenario_loop", ai_loop)
    monkeypatch.setattr(scenario_runner, "execute_scenario_loop", graph_loop)
    monkeypatch.setattr(scenario_runner, "finalize_run_media", AsyncMock())

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-ai-routing",
        context=_run_context(logger_name="test.scenario_runner_ai"),
    )

    ai_loop.assert_awaited_once()
    graph_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scenario_ai_tagged_raises_when_feature_disabled(monkeypatch):
    scenario = _ai_runtime_scenario()
    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))

    with pytest.raises(RuntimeError, match="AI caller runtime is disabled"):
        await scenario_runner.run_scenario(
            _FakeRoom(),
            scenario,
            run_id="run-ai-routing-disabled",
            context=_run_context(
                settings_obj=_settings(feature_ai_scenarios_enabled=False),
                logger_name="test.scenario_runner_ai",
            ),
        )


@pytest.mark.asyncio
async def test_run_scenario_resets_recorder_after_initial_drain_before_timing_origin(monkeypatch):
    scenario = _graph_harness_first_scenario()
    recorder: _FakeRecorder | None = None

    def _make_recorder(*, enabled: bool):
        nonlocal recorder
        recorder = _FakeRecorder(enabled=enabled)
        return recorder

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_scenario_loop", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(scenario_runner, "finalize_run_media", AsyncMock())

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-recorder-reset",
        context=_run_context(
            bot_audio_recorder_cls=_make_recorder,
            logger_name="test.scenario_runner_reset",
        ),
    )

    assert recorder is not None
    assert recorder.reset_calls == 1


@pytest.mark.asyncio
async def test_run_scenario_skips_initial_drain_for_ai_wait_for_bot_greeting(monkeypatch):
    scenario = _ai_runtime_scenario()
    listener: _FakeListener | None = None

    class _CapturingListener(_FakeListener):
        def __init__(self, *_args, **_kwargs) -> None:
            nonlocal listener
            super().__init__(*_args, **_kwargs)
            listener = self

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_ai_scenario_loop", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(scenario_runner, "finalize_run_media", AsyncMock())

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-ai-no-drain",
        context=_run_context(
            bot_listener_cls=_CapturingListener,
            run_metadata={"ai_opening_strategy": "wait_for_bot_greeting"},
            logger_name="test.scenario_runner_ai_wait_for_greeting",
        ),
    )

    assert listener is not None
    assert listener.drain_calls == []


@pytest.mark.asyncio
async def test_run_scenario_passes_resolved_stt_provider_to_listener(monkeypatch):
    scenario = _graph_harness_first_scenario()
    captured: dict[str, object] = {}

    class _CapturingListener(_FakeListener):
        def __init__(self, participant, stt_provider, stt_plugin_module, **kwargs) -> None:
            del participant
            captured["provider_id"] = stt_provider.provider_id
            captured["model_label"] = stt_provider.model_label
            captured["stt_plugin_module"] = stt_plugin_module
            captured["kwargs"] = kwargs

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_scenario_loop", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(scenario_runner, "finalize_run_media", AsyncMock())

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-stt-provider",
        context=_run_context(
            bot_listener_cls=_CapturingListener,
            logger_name="test.scenario_runner_stt",
        ),
    )

    assert captured["provider_id"] == "deepgram"
    assert captured["model_label"] == scenario.config.stt_model
    assert captured["stt_plugin_module"] is _FakeDeepgram


@pytest.mark.asyncio
async def test_run_scenario_selects_azure_stt_plugin_by_provider(monkeypatch):
    scenario = _graph_harness_first_scenario()
    scenario.config.stt_provider = "azure"
    scenario.config.stt_model = "azure-default"
    captured: dict[str, object] = {}

    class _CapturingListener(_FakeListener):
        def __init__(self, participant, stt_provider, stt_plugin_module, **kwargs) -> None:
            del participant, kwargs
            captured["provider_id"] = stt_provider.provider_id
            captured["stt_plugin_module"] = stt_plugin_module

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_scenario_loop", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(scenario_runner, "finalize_run_media", AsyncMock())

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-stt-provider-azure",
        context=_run_context(
            settings_obj=_settings(
                feature_stt_provider_azure_enabled=True,
                azure_speech_key="test-azure-key",
                azure_speech_region="uksouth",
            ),
            bot_listener_cls=_CapturingListener,
            logger_name="test.scenario_runner_stt_azure",
        ),
    )

    assert captured["provider_id"] == "azure"
    assert captured["stt_plugin_module"] is _FakeAzure


@pytest.mark.asyncio
async def test_run_scenario_routes_http_transport_to_direct_http_loop(monkeypatch):
    scenario = _graph_harness_first_scenario()
    conversation = [
        ConversationTurn(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="hello",
            audio_start_ms=0,
            audio_end_ms=1,
        )
    ]
    direct_loop = AsyncMock(return_value=(conversation, 1))

    monkeypatch.setattr(scenario_runner, "execute_direct_http_scenario_loop", direct_loop)
    monkeypatch.setattr(scenario_runner, "execute_direct_http_ai_loop", AsyncMock(return_value=([], 0)))

    wait_for_bot = AsyncMock(side_effect=AssertionError("wait_for_bot should not be called for http transport"))
    fetch_transport_context = AsyncMock(
        return_value={
            "run_id": "run-http",
            "transport_profile_id": "dest_http",
            "endpoint": "https://bot.internal/chat",
            "headers": {},
            "direct_http_config": {},
        }
    )

    result = await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-http",
        context=_run_context(
            wait_for_bot_fn=wait_for_bot,
            fetch_run_transport_context_fn=fetch_transport_context,
            run_metadata={"transport": "http", "scenario_kind": "graph"},
            logger_name="test.scenario_runner_http",
        ),
    )

    fetch_transport_context.assert_awaited_once_with("run-http")
    direct_loop.assert_awaited_once()
    wait_for_bot.assert_not_awaited()
    assert result == conversation


@pytest.mark.asyncio
async def test_run_scenario_routes_http_ai_transport_to_direct_http_ai_loop(monkeypatch):
    scenario = _ai_runtime_scenario()
    conversation = [
        ConversationTurn(
            turn_id="t1",
            turn_number=1,
            speaker="bot",
            text="hello",
            audio_start_ms=0,
            audio_end_ms=1,
        )
    ]
    direct_ai_loop = AsyncMock(return_value=(conversation, 1))

    monkeypatch.setattr(scenario_runner, "execute_direct_http_ai_loop", direct_ai_loop)
    monkeypatch.setattr(scenario_runner, "execute_direct_http_scenario_loop", AsyncMock(return_value=([], 0)))

    fetch_transport_context = AsyncMock(
        return_value={
            "run_id": "run-http-ai",
            "transport_profile_id": "dest_http",
            "endpoint": "https://bot.internal/chat",
            "headers": {},
            "direct_http_config": {},
        }
    )

    result = await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-http-ai",
        context=_run_context(
            wait_for_bot_fn=AsyncMock(side_effect=AssertionError("wait_for_bot should not be called for http transport")),
            fetch_run_transport_context_fn=fetch_transport_context,
            run_metadata={"transport": "http", "scenario_kind": "ai"},
            logger_name="test.scenario_runner_http_ai",
        ),
    )

    fetch_transport_context.assert_awaited_once_with("run-http-ai")
    direct_ai_loop.assert_awaited_once()
    assert result == conversation


@pytest.mark.asyncio
async def test_run_scenario_routes_playground_runs_to_playground_runtime(monkeypatch):
    scenario = _graph_harness_first_scenario()
    playground_loop = AsyncMock(return_value=([], 0))

    monkeypatch.setattr(scenario_runner, "execute_playground_loop", playground_loop)

    wait_for_bot = AsyncMock(side_effect=AssertionError("wait_for_bot should not be called for playground runs"))

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-playground",
        context=_run_context(
            wait_for_bot_fn=wait_for_bot,
            fetch_run_transport_context_fn=AsyncMock(return_value={"run_id": "run-playground"}),
            run_metadata={"run_type": "playground", "playground_mode": "mock", "scenario_kind": "graph"},
            logger_name="test.scenario_runner_playground",
        ),
    )

    playground_loop.assert_awaited_once()
    wait_for_bot.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scenario_skips_participant_removal_for_webrtc_transport(monkeypatch):
    scenario = _graph_harness_first_scenario()
    finalize_media = AsyncMock()

    monkeypatch.setattr(scenario_runner, "publish_harness_audio_track", AsyncMock(return_value=object()))
    monkeypatch.setattr(scenario_runner, "execute_scenario_loop", AsyncMock(return_value=([], 0)))
    monkeypatch.setattr(scenario_runner, "finalize_run_media", finalize_media)

    await scenario_runner.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-webrtc-finalize",
        context=_run_context(
            run_metadata={"transport": "webrtc", "scenario_kind": "graph"},
            logger_name="test.scenario_runner_webrtc",
        ),
    )

    assert finalize_media.await_args.kwargs["participant_removal_enabled"] is False


def test_run_scenario_requires_context_argument() -> None:
    # TypeError is raised synchronously at the call site (missing required
    # keyword-only argument), before any coroutine is created, so this test
    # does not need to be async.
    scenario = _graph_harness_first_scenario()

    with pytest.raises(TypeError, match="required keyword-only argument: 'context'"):
        scenario_runner.run_scenario(  # type: ignore[call-arg]
            _FakeRoom(),
            scenario,
            run_id="run-missing-context",
        )
