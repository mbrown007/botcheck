"""Harness run_scenario cache-hit path tests."""

import os
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from botcheck_scenarios import (
    BotConfig,
    BranchCase,
    BranchConfig,
    CircuitOpenError,
    ScenarioDefinition,
    ScenarioType,
    Turn,
)

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-env-openai-key-MUST-NOT-REACH-PROVIDER")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-env-deepgram-key-MUST-NOT-REACH-PROVIDER")

from src import (
    agent,  # noqa: E402
    scenario_runner,  # noqa: E402
)
from src.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def reset_tts_circuit() -> None:
    agent._AGENT_TTS_BREAKERS.reset()


def _provider_runtime_context() -> dict[str, object]:
    return {
        "feature_flags": {
            "feature_tts_provider_openai_enabled": True,
            "feature_stt_provider_deepgram_enabled": True,
        },
        "tts": {
            "vendor": "openai",
            "secret_fields": {"api_key": "stored-openai-key"},
        },
        "stt": {
            "vendor": "deepgram",
            "secret_fields": {"api_key": "stored-deepgram-key"},
        },
    }


class _Counter:
    def __init__(self) -> None:
        self.value = 0
        self.by_scenario_kind: dict[str, int] = {}

    def inc(self, amount: float = 1.0) -> None:
        self.value += int(amount)

    def labels(self, **kwargs):
        scenario_kind = str(kwargs.get("scenario_kind", "unknown"))
        parent = self

        class _Child:
            def inc(self, amount: float = 1.0) -> None:
                delta = int(amount)
                parent.value += delta
                parent.by_scenario_kind[scenario_kind] = (
                    parent.by_scenario_kind.get(scenario_kind, 0) + delta
                )

        return _Child()


class _ObserveMetric:
    def __init__(self) -> None:
        self.values: list[float] = []

    def observe(self, value: float) -> None:
        self.values.append(float(value))


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        return {"Body": _FakeBody(self.payload)}


class _FakeS3ClientCM:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> _FakeS3Client:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeS3Session:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    def client(self, *_args, **_kwargs):
        return _FakeS3ClientCM(self._client)


class _FakeAudioSource:
    def __init__(self, *args, **kwargs) -> None:
        self.frames: list[Any] = []

    async def capture_frame(self, frame: Any) -> None:
        self.frames.append(frame)


class _FakeLocalAudioTrack:
    @staticmethod
    def create_audio_track(_name: str, _source: _FakeAudioSource) -> object:
        return object()


class _FakeTrackPublishOptions:
    def __init__(self, *, source: str) -> None:
        self.source = source


class _FakeLocalParticipant:
    async def publish_track(self, *_args, **_kwargs) -> None:
        return None


class _FakeRoom:
    def __init__(self) -> None:
        self.name = "room-test"
        self.local_participant = _FakeLocalParticipant()
        self.remote_participants: dict[str, object] = {}


class _FakeBotParticipant:
    identity = "bot-test"


class _FakeBotListener:
    def __init__(self, *_args, **_kwargs) -> None:
        return

    async def start(self) -> None:
        return

    async def drain(self, duration_s: float = 2.0) -> None:
        return

    async def listen(self, timeout_s: float, merge_window_s: float = 1.5, stt_endpointing_ms: int | None = None, listen_for_s: float | None = None, preview_callback=None) -> str:
        return "(timeout)"

    async def stop(self) -> None:
        return


class _SequencedBotListener(_FakeBotListener):
    def __init__(self, *_args, responses: list[str] | None = None, **_kwargs) -> None:
        self._responses = list(responses or ["(timeout)"])

    async def listen(self, timeout_s: float, merge_window_s: float = 1.5, stt_endpointing_ms: int | None = None, listen_for_s: float | None = None, preview_callback=None) -> str:
        del timeout_s, merge_window_s, stt_endpointing_ms
        if not self._responses:
            return "(timeout)"
        return self._responses.pop(0)


class _FailingBotListener(_FakeBotListener):
    async def listen(
        self,
        timeout_s: float,
        merge_window_s: float = 1.5,
        stt_endpointing_ms: int | None = None,
        listen_for_s: float | None = None,
        preview_callback=None,
    ) -> str:
        del timeout_s, merge_window_s, stt_endpointing_ms
        raise RuntimeError("simulated listener failure")


class _FakeLiveKitRoomAPI:
    def __init__(self) -> None:
        self.remove_participant = AsyncMock()


class _FakeLiveKitAPI:
    def __init__(self, *args, **kwargs) -> None:
        self.room = _FakeLiveKitRoomAPI()

    async def __aenter__(self) -> "_FakeLiveKitAPI":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache-hit",
        name="Scenario Cache Hit",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(id="t1", text="hello one", wait_for_response=False),
            Turn(id="t2", text="hello two", wait_for_response=False),
        ],
    )


def _scenario_wait_for_response() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache-error",
        name="Scenario Cache Error",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(id="t1", silence_s=0.1, wait_for_response=True),
        ],
    )


@pytest.mark.asyncio
async def test_run_scenario_fully_warm_uses_cache_without_live_tts(monkeypatch):
    scenario = _scenario()
    fake_s3 = _FakeS3Client(payload=b"cached-wav")

    hit = _Counter()
    miss = _Counter()
    fallback = _Counter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)

    monkeypatch.setattr(
        agent.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")
    monkeypatch.setattr(settings, "recording_upload_enabled", False)

    synth_calls = {"count": 0}

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs):
            synth_calls["count"] += 1
            raise AssertionError("Live TTS synth should not be called on cache hit path")

    publish_cached_wav_mock = AsyncMock()
    report_turn_mock = AsyncMock()
    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "_publish_cached_wav", publish_cached_wav_mock)
    monkeypatch.setattr(agent, "report_turn", report_turn_mock)
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FakeBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    conversation = await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-cache-hit",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
    )

    assert synth_calls["count"] == 0
    assert hit.value == 2
    assert hit.by_scenario_kind == {"graph": 2}
    assert miss.value == 0
    assert fallback.value == 0
    assert publish_cached_wav_mock.await_count == 2
    assert report_turn_mock.await_count == 2
    assert len(conversation) == 2
    assert all(turn.speaker == "harness" for turn in conversation)


@pytest.mark.asyncio
async def test_run_scenario_cancels_cache_prefetcher_after_completion(monkeypatch):
    scenario = _scenario()
    cancel_mock = Mock()

    async def _prefetched_read_cached_turn_wav(*, scenario, turn, tenant_id):
        del scenario, turn, tenant_id
        return b"cached-wav"

    monkeypatch.setattr(
        agent,
        "_build_prefetched_read_cached_turn_wav",
        lambda **_kwargs: (
            _prefetched_read_cached_turn_wav,
            type("_FakePrefetcher", (), {"cancel": cancel_mock})(),
        ),
    )
    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(agent, "_publish_cached_wav", AsyncMock())
    monkeypatch.setattr(agent, "report_turn", AsyncMock())
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FakeBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs):
            raise AssertionError("Live TTS synth should not be called on cache hit path")

    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)

    await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-cache-prefetch-cancel",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
    )

    cancel_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_run_scenario_emits_heartbeat_state_updates(monkeypatch):
    scenario = _scenario()
    fake_s3 = _FakeS3Client(payload=b"cached-wav")
    state_updates: list[tuple[int | None, str | None]] = []

    monkeypatch.setattr(
        agent.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")
    monkeypatch.setattr(settings, "recording_upload_enabled", False)

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs):
            raise AssertionError("Live TTS synth should not be called on cache hit path")

    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "_publish_cached_wav", AsyncMock())
    monkeypatch.setattr(agent, "report_turn", AsyncMock())
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FakeBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-cache-heartbeat-state",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
        heartbeat_state_callback=lambda turn_number, listener_state: state_updates.append(
            (turn_number, listener_state)
        ),
    )

    assert (1, "speaking_harness") in state_updates
    assert (2, "speaking_harness") in state_updates
    assert state_updates[-1] == (2, "finalizing")


@pytest.mark.asyncio
async def test_run_scenario_s3_fallback_uses_live_tts_without_abort(monkeypatch):
    scenario = _scenario()

    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(agent, "_read_cached_turn_wav", AsyncMock(return_value=None))

    synth_calls = {"count": 0}

    class _FakeEvent:
        frame = object()

    class _FakeChunked:
        async def __aenter__(self) -> "_FakeChunked":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def __aiter__(self) -> "_FakeChunked":
            self._yielded = False
            return self

        async def __anext__(self) -> _FakeEvent:
            if self._yielded:
                raise StopAsyncIteration
            self._yielded = True
            return _FakeEvent()

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs) -> _FakeChunked:
            synth_calls["count"] += 1
            return _FakeChunked()

    report_turn_mock = AsyncMock()
    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "report_turn", report_turn_mock)
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FakeBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    conversation = await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-s3-fallback",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
    )

    assert synth_calls["count"] == 2
    assert report_turn_mock.await_count == 2
    assert len(conversation) == 2
    assert all(turn.speaker == "harness" for turn in conversation)


@pytest.mark.asyncio
async def test_run_scenario_live_tts_fails_fast_when_circuit_open(monkeypatch):
    scenario = _scenario()
    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(agent, "_read_cached_turn_wav", AsyncMock(return_value=None))

    class _OpenBreaker:
        async def call(self, _operation, *, on_transition=None, on_reject=None):
            del on_transition
            if on_reject is not None:
                on_reject(None)
            raise CircuitOpenError("agent.live_tts.openai")

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs):
            raise AssertionError("synthesize should not run when circuit is open")

    monkeypatch.setattr(
        agent,
        "_AGENT_TTS_BREAKERS",
        type("OpenBreakerRegistry", (), {"get": staticmethod(lambda _provider: _OpenBreaker())})(),
    )
    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "report_turn", AsyncMock())
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FakeBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    with pytest.raises(RuntimeError, match="circuit is open"):
        await agent.run_scenario(
            _FakeRoom(),
            scenario,
            run_id="run-cache-circuit-open",
            tenant_id="tenant-a",
            provider_runtime_context=_provider_runtime_context(),
        )


@pytest.mark.asyncio
async def test_run_scenario_branching_uses_classifier_and_reports_branch_metadata(monkeypatch):
    scenario = ScenarioDefinition(
        id="scenario-branching",
        name="Scenario Branching",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(
                id="t1",
                text="Do you handle billing or technical support?",
                wait_for_response=True,
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[
                        BranchCase(condition="billing support", next="t_billing"),
                        BranchCase(condition="technical support", next="t_tech"),
                    ],
                ),
            ),
            Turn(id="t_billing", text="I need help with my invoice.", next="t_end", wait_for_response=False),
            Turn(id="t_tech", text="My app is crashing.", next="t_end", wait_for_response=False),
            Turn(
                id="t_fallback",
                text="Please repeat your support options.",
                next="t_end",
                wait_for_response=False,
            ),
            Turn(id="t_end", text="Thanks.", wait_for_response=False),
        ],
    )

    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(settings, "enable_branching_graph", True)
    monkeypatch.setattr(agent, "_read_cached_turn_wav", AsyncMock(return_value=None))
    monkeypatch.setattr(agent, "classify_branch", AsyncMock(return_value="billing support"))

    synth_calls = {"count": 0}

    class _FakeEvent:
        frame = object()

    class _FakeChunked:
        async def __aenter__(self) -> "_FakeChunked":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def __aiter__(self) -> "_FakeChunked":
            self._yielded = False
            return self

        async def __anext__(self) -> _FakeEvent:
            if self._yielded:
                raise StopAsyncIteration
            self._yielded = True
            return _FakeEvent()

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs) -> _FakeChunked:
            synth_calls["count"] += 1
            return _FakeChunked()

    report_turn_mock = AsyncMock()
    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "report_turn", report_turn_mock)
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(
        agent,
        "_BotListener",
        lambda *args, **kwargs: _SequencedBotListener(*args, responses=["I can help with billing support."], **kwargs),
    )
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    conversation = await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-branching",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
    )

    assert [turn.turn_id for turn in conversation] == ["t1", "t1_bot", "t_billing", "t_end"]
    assert synth_calls["count"] == 3
    agent.classify_branch.assert_awaited_once()

    assert report_turn_mock.await_count == 4
    first_call = report_turn_mock.await_args_list[0]
    assert first_call.kwargs.get("visit") == 1
    assert first_call.kwargs.get("branch_condition_matched") == "billing support"
    assert first_call.kwargs.get("branch_response_snippet") == "I can help with billing support."


@pytest.mark.asyncio
async def test_run_scenario_branching_default_fallback_path(monkeypatch):
    scenario = ScenarioDefinition(
        id="scenario-branching-default",
        name="Scenario Branching Default",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(
                id="t1",
                text="Do you handle billing or technical support?",
                wait_for_response=True,
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[
                        BranchCase(condition="billing support", next="t_billing"),
                        BranchCase(condition="technical support", next="t_tech"),
                    ],
                ),
            ),
            Turn(id="t_billing", text="I need help with my invoice.", next="t_end", wait_for_response=False),
            Turn(id="t_tech", text="My app is crashing.", next="t_end", wait_for_response=False),
            Turn(
                id="t_fallback",
                text="Please repeat your support options.",
                next="t_end",
                wait_for_response=False,
            ),
            Turn(id="t_end", text="Thanks.", wait_for_response=False),
        ],
    )

    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(settings, "enable_branching_graph", True)
    monkeypatch.setattr(agent, "_read_cached_turn_wav", AsyncMock(return_value=None))
    monkeypatch.setattr(agent, "classify_branch", AsyncMock(return_value="default"))

    class _FakeEvent:
        frame = object()

    class _FakeChunked:
        async def __aenter__(self) -> "_FakeChunked":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def __aiter__(self) -> "_FakeChunked":
            self._yielded = False
            return self

        async def __anext__(self) -> _FakeEvent:
            if self._yielded:
                raise StopAsyncIteration
            self._yielded = True
            return _FakeEvent()

    class _FakeTTS:
        def __init__(self, *args, **kwargs) -> None:
            return

        def synthesize(self, *_args, **_kwargs) -> _FakeChunked:
            return _FakeChunked()

    report_turn_mock = AsyncMock()
    monkeypatch.setattr(agent.openai, "TTS", _FakeTTS)
    monkeypatch.setattr(agent, "report_turn", report_turn_mock)
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(
        agent,
        "_BotListener",
        lambda *args, **kwargs: _SequencedBotListener(*args, responses=["unsure"], **kwargs),
    )
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    conversation = await agent.run_scenario(
        _FakeRoom(),
        scenario,
        run_id="run-branching-default",
        tenant_id="tenant-a",
        provider_runtime_context=_provider_runtime_context(),
    )

    assert [turn.turn_id for turn in conversation] == ["t1", "t1_bot", "t_fallback", "t_end"]
    agent.classify_branch.assert_awaited_once()
    first_call = report_turn_mock.await_args_list[0]
    assert first_call.kwargs.get("branch_condition_matched") == "default"


@pytest.mark.asyncio
async def test_run_scenario_records_sip_duration_on_exception(monkeypatch):
    scenario = _scenario_wait_for_response()
    observe_metric = _ObserveMetric()

    monkeypatch.setattr(scenario_runner, "SIP_CALL_DURATION_SECONDS", observe_metric)
    monkeypatch.setattr(settings, "recording_upload_enabled", False)
    monkeypatch.setattr(agent, "_read_cached_turn_wav", AsyncMock(return_value=None))
    monkeypatch.setattr(agent, "report_turn", AsyncMock())
    monkeypatch.setattr(agent, "_wait_for_bot", AsyncMock(return_value=_FakeBotParticipant()))
    monkeypatch.setattr(agent, "_BotListener", _FailingBotListener)
    monkeypatch.setattr(agent.lk_api, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(agent.rtc, "AudioSource", _FakeAudioSource)
    monkeypatch.setattr(agent.rtc, "LocalAudioTrack", _FakeLocalAudioTrack)
    monkeypatch.setattr(agent.rtc, "TrackPublishOptions", _FakeTrackPublishOptions)

    with pytest.raises(RuntimeError, match="simulated listener failure"):
        await agent.run_scenario(
            _FakeRoom(),
            scenario,
            run_id="run-sip-duration-error",
            tenant_id="tenant-a",
            provider_runtime_context=_provider_runtime_context(),
        )

    assert len(observe_metric.values) == 1
    assert observe_metric.values[0] >= 0.0
