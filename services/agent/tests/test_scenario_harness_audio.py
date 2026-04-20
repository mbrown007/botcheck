from __future__ import annotations

import asyncio
from itertools import chain, repeat
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from botcheck_scenarios import CircuitOpenError

from src.scenario_harness_audio import play_harness_turn_audio


def _turn(text: str = "hello"):
    return SimpleNamespace(
        kind="harness_prompt",
        content=SimpleNamespace(text=text, silence_s=None, audio_file=None, dtmf=None),
    )


def _scenario():
    return SimpleNamespace(config=SimpleNamespace(tts_voice="alloy"))


class _FakeMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def observe(self, value: float) -> None:
        self.calls.append((dict(self._labels), value))


@pytest.mark.asyncio
async def test_play_harness_turn_audio_uses_cache_hit_path(monkeypatch) -> None:
    latency_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_harness_audio.TTS_PLAYBACK_LATENCY_SECONDS", latency_metric)
    read_cached = AsyncMock(return_value=b"WAV")
    publish_cached = AsyncMock()
    tts = SimpleNamespace(synthesize=AsyncMock())
    audio_source = SimpleNamespace(capture_frame=AsyncMock())
    monotonic_values = iter((10.0, 10.15))

    result = await play_harness_turn_audio(
        turn_number=1,
        turn_def=_turn("cached"),
        scenario=_scenario(),
        tenant_id="tenant-a",
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=read_cached,
        publish_cached_wav_fn=publish_cached,
        logger_obj=SimpleNamespace(info=Mock()),
        monotonic_fn=lambda: next(monotonic_values),
    )

    assert result.completed is True
    assert result.cancelled is False
    read_cached.assert_awaited_once()
    publish_cached.assert_awaited_once_with(audio_source, b"WAV")
    tts.synthesize.assert_not_called()
    assert latency_metric.calls[0][0]["source"] == "cache"
    assert latency_metric.calls[0][0]["scenario_kind"] == "graph"
    assert round(latency_metric.calls[0][1], 3) == 0.15


@pytest.mark.asyncio
async def test_play_harness_turn_audio_raises_when_circuit_open() -> None:
    class _OpenBreaker:
        async def call(self, operation, **kwargs):
            raise CircuitOpenError("live-tts")

    with pytest.raises(RuntimeError, match="Live TTS circuit is open"):
        await play_harness_turn_audio(
            turn_number=3,
            turn_def=_turn("live"),
            scenario=_scenario(),
            tenant_id="tenant-a",
            audio_source=SimpleNamespace(capture_frame=AsyncMock()),
            tts=SimpleNamespace(synthesize=AsyncMock()),
            read_cached_turn_wav_fn=AsyncMock(return_value=None),
            publish_cached_wav_fn=AsyncMock(),
            tts_live_circuit_breaker=_OpenBreaker(),
            tts_circuit_bridge=SimpleNamespace(on_transition=Mock(), on_reject=Mock()),
            logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
            synthesis_timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_play_harness_turn_audio_records_live_tts_latency(monkeypatch) -> None:
    latency_metric = _FakeMetric()
    first_byte_metric = _FakeMetric()
    stream_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_harness_audio.TTS_PLAYBACK_LATENCY_SECONDS", latency_metric)
    monkeypatch.setattr("src.scenario_harness_audio.TTS_FIRST_BYTE_LATENCY_SECONDS", first_byte_metric)
    monkeypatch.setattr("src.scenario_harness_audio.TTS_STREAM_DURATION_SECONDS", stream_metric)
    read_cached = AsyncMock(return_value=None)
    publish_cached = AsyncMock()
    audio_source = SimpleNamespace(capture_frame=AsyncMock())
    monotonic_values = chain((20.0, 20.05, 20.15, 20.45, 20.55), repeat(20.55))

    class _FakeChunked:
        def __init__(self) -> None:
            self._done = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return SimpleNamespace(frame=object())

    tts = SimpleNamespace(synthesize=Mock(return_value=_FakeChunked()))

    await play_harness_turn_audio(
        turn_number=1,
        turn_def=_turn("live"),
        scenario=_scenario(),
        tenant_id="tenant-a",
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=read_cached,
        publish_cached_wav_fn=publish_cached,
        logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
        monotonic_fn=lambda: next(monotonic_values),
        synthesis_timeout_s=5.0,
    )

    assert tts.synthesize.called
    assert latency_metric.calls[0][0]["source"] == "live"
    assert latency_metric.calls[0][0]["provider"] == "openai"
    assert latency_metric.calls[0][0]["scenario_kind"] == "graph"
    assert round(latency_metric.calls[0][1], 3) == 0.55
    assert first_byte_metric.calls[0][0]["scenario_kind"] == "graph"
    assert round(first_byte_metric.calls[0][1], 3) == 0.1
    assert stream_metric.calls[0][0]["scenario_kind"] == "graph"
    assert round(stream_metric.calls[0][1], 3) == 0.3


@pytest.mark.asyncio
async def test_play_harness_turn_audio_disables_livekit_tts_retries() -> None:
    class _FakeChunked:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    synthesize = Mock(return_value=_FakeChunked())
    tts = SimpleNamespace(synthesize=synthesize)

    await play_harness_turn_audio(
        turn_number=1,
        turn_def=_turn("live"),
        scenario=_scenario(),
        tenant_id="tenant-a",
        audio_source=SimpleNamespace(capture_frame=AsyncMock()),
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
        synthesis_timeout_s=7.5,
    )

    _, kwargs = synthesize.call_args
    conn_options = kwargs["conn_options"]
    assert conn_options.max_retry == 0
    assert conn_options.timeout == 7.5


class _FakeCounter:
    def __init__(self) -> None:
        self.incs: list[dict[str, str]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.incs.append(dict(self._labels))


@pytest.mark.asyncio
async def test_play_harness_turn_audio_skips_cached_publish_when_pre_cancelled(monkeypatch) -> None:
    cancellations = _FakeCounter()
    monkeypatch.setattr(
        "src.scenario_harness_audio.TTS_PLAYBACK_CANCELLATIONS_TOTAL",
        cancellations,
    )
    cancel_event = asyncio.Event()
    cancel_event.set()
    publish_cached = AsyncMock()

    result = await play_harness_turn_audio(
        turn_number=1,
        turn_def=_turn("cached"),
        scenario=_scenario(),
        tenant_id="tenant-a",
        audio_source=SimpleNamespace(capture_frame=AsyncMock()),
        tts=SimpleNamespace(synthesize=Mock()),
        read_cached_turn_wav_fn=AsyncMock(return_value=b"WAV"),
        publish_cached_wav_fn=publish_cached,
        logger_obj=SimpleNamespace(info=Mock()),
        cancel_event=cancel_event,
    )

    assert result.completed is False
    assert result.cancelled is True
    assert result.source == "cache"
    publish_cached.assert_not_awaited()
    assert cancellations.incs == [
        {
            "provider": "cache",
            "model": "alloy",
            "source": "cache",
            "reason": "pre_start",
            "scenario_kind": "graph",
        }
    ]


@pytest.mark.asyncio
async def test_timeout_fires_within_deadline(monkeypatch) -> None:
    """TTS mock hangs; asyncio.wait_for cancels it; RuntimeError('timed out') is raised."""

    class _HangingChunked:
        async def __aenter__(self):
            await asyncio.sleep(999)
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    failures_counter = _FakeCounter()
    api_calls_counter = _FakeCounter()
    monkeypatch.setattr("src.scenario_harness_audio.TTS_LIVE_FAILURES_TOTAL", failures_counter)
    monkeypatch.setattr("src.scenario_harness_audio.PROVIDER_API_CALLS_TOTAL", api_calls_counter)

    logger = SimpleNamespace(info=Mock(), debug=Mock(), error=Mock())

    with pytest.raises(RuntimeError, match="timed out"):
        await play_harness_turn_audio(
            turn_number=2,
            turn_def=_turn("live text"),
            scenario=_scenario(),
            tenant_id="tenant-a",
            audio_source=SimpleNamespace(capture_frame=AsyncMock()),
            tts=SimpleNamespace(synthesize=Mock(return_value=_HangingChunked())),
            read_cached_turn_wav_fn=AsyncMock(return_value=None),
            publish_cached_wav_fn=AsyncMock(),
            logger_obj=logger,
            synthesis_timeout_s=0.1,
        )

    assert any(d.get("reason") == "timeout" for d in failures_counter.incs)
    assert any(d.get("scenario_kind") == "graph" for d in failures_counter.incs)
    assert any(d.get("outcome") == "timeout" for d in api_calls_counter.incs)
    logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_circuit_open_increments_metric(monkeypatch) -> None:
    """CircuitOpenError increments TTS_LIVE_FAILURES_TOTAL{reason='circuit_open'}."""

    class _OpenBreaker:
        async def call(self, operation, **kwargs):
            raise CircuitOpenError("live-tts")

    failures_counter = _FakeCounter()
    api_calls_counter = _FakeCounter()
    monkeypatch.setattr("src.scenario_harness_audio.TTS_LIVE_FAILURES_TOTAL", failures_counter)
    monkeypatch.setattr("src.scenario_harness_audio.PROVIDER_API_CALLS_TOTAL", api_calls_counter)

    with pytest.raises(RuntimeError, match="circuit is open"):
        await play_harness_turn_audio(
            turn_number=3,
            turn_def=_turn("live"),
            scenario=_scenario(),
            tenant_id="tenant-a",
            audio_source=SimpleNamespace(capture_frame=AsyncMock()),
            tts=SimpleNamespace(synthesize=AsyncMock()),
            read_cached_turn_wav_fn=AsyncMock(return_value=None),
            publish_cached_wav_fn=AsyncMock(),
            tts_live_circuit_breaker=_OpenBreaker(),
            tts_circuit_bridge=SimpleNamespace(on_transition=Mock(), on_reject=Mock()),
            logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
            synthesis_timeout_s=5.0,
        )

    assert any(d.get("reason") == "circuit_open" for d in failures_counter.incs)
    assert any(d.get("scenario_kind") == "graph" for d in failures_counter.incs)
    assert any(d.get("outcome") == "circuit_open" for d in api_calls_counter.incs)


@pytest.mark.asyncio
async def test_cache_hit_skips_live_tts(monkeypatch) -> None:
    """When cache returns bytes, publish_cached_wav_fn is called and tts.synthesize is never invoked."""
    latency_metric = _FakeMetric()
    monkeypatch.setattr("src.scenario_harness_audio.TTS_PLAYBACK_LATENCY_SECONDS", latency_metric)

    publish_cached = AsyncMock()
    tts = SimpleNamespace(synthesize=Mock())
    audio_source = SimpleNamespace(capture_frame=AsyncMock())
    monotonic_values = iter((5.0, 5.2))

    await play_harness_turn_audio(
        turn_number=1,
        turn_def=_turn("cached text"),
        scenario=_scenario(),
        tenant_id="tenant-b",
        audio_source=audio_source,
        tts=tts,
        read_cached_turn_wav_fn=AsyncMock(return_value=b"\x00\x01WAV"),
        publish_cached_wav_fn=publish_cached,
        logger_obj=SimpleNamespace(info=Mock()),
        monotonic_fn=lambda: next(monotonic_values),
    )

    publish_cached.assert_awaited_once_with(audio_source, b"\x00\x01WAV")
    tts.synthesize.assert_not_called()
    assert latency_metric.calls[0][0]["source"] == "cache"
    assert latency_metric.calls[0][0]["scenario_kind"] == "graph"


@pytest.mark.asyncio
async def test_play_harness_turn_audio_cancels_live_playback_in_flight(monkeypatch) -> None:
    cancellations = _FakeCounter()
    api_calls_counter = _FakeCounter()
    characters_counter = _FakeCounter()
    monkeypatch.setattr(
        "src.scenario_harness_audio.TTS_PLAYBACK_CANCELLATIONS_TOTAL",
        cancellations,
    )
    monkeypatch.setattr("src.scenario_harness_audio.PROVIDER_API_CALLS_TOTAL", api_calls_counter)
    monkeypatch.setattr("src.scenario_harness_audio.TTS_CHARACTERS_TOTAL", characters_counter)
    cancel_event = asyncio.Event()

    class _FakeChunked:
        def __init__(self) -> None:
            self._index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= 2:
                raise StopAsyncIteration
            self._index += 1
            return SimpleNamespace(frame=object())

    async def _capture_frame(_frame) -> None:
        cancel_event.set()

    result = await play_harness_turn_audio(
        turn_number=2,
        turn_def=_turn("live"),
        scenario=_scenario(),
        tenant_id="tenant-a",
        audio_source=SimpleNamespace(capture_frame=AsyncMock(side_effect=_capture_frame)),
        tts=SimpleNamespace(synthesize=Mock(return_value=_FakeChunked())),
        read_cached_turn_wav_fn=AsyncMock(return_value=None),
        publish_cached_wav_fn=AsyncMock(),
        logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
        synthesis_timeout_s=5.0,
        cancel_event=cancel_event,
    )

    assert result.completed is False
    assert result.cancelled is True
    assert result.source == "live"
    assert cancellations.incs == [
        {
            "provider": "openai",
            "model": "alloy",
            "source": "live",
            "reason": "in_flight",
            "scenario_kind": "graph",
        }
    ]
    assert api_calls_counter.incs == []
    assert characters_counter.incs == []


@pytest.mark.asyncio
async def test_play_harness_turn_audio_records_task_cancellation_cached_path(monkeypatch) -> None:
    cancellations = _FakeCounter()
    monkeypatch.setattr(
        "src.scenario_harness_audio.TTS_PLAYBACK_CANCELLATIONS_TOTAL",
        cancellations,
    )

    async def _slow_publish(source, data) -> None:
        await asyncio.sleep(999)

    task = asyncio.create_task(
        play_harness_turn_audio(
            turn_number=5,
            turn_def=_turn("cached"),
            scenario=_scenario(),
            tenant_id="tenant-a",
            audio_source=SimpleNamespace(capture_frame=AsyncMock()),
            tts=SimpleNamespace(synthesize=Mock()),
            read_cached_turn_wav_fn=AsyncMock(return_value=b"WAV"),
            publish_cached_wav_fn=_slow_publish,
            logger_obj=SimpleNamespace(info=Mock()),
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancellations.incs == [
        {
            "provider": "cache",
            "model": "alloy",
            "source": "cache",
            "reason": "task_cancelled",
            "scenario_kind": "graph",
        }
    ]


@pytest.mark.asyncio
async def test_play_harness_turn_audio_records_task_cancellation(monkeypatch) -> None:
    cancellations = _FakeCounter()
    monkeypatch.setattr(
        "src.scenario_harness_audio.TTS_PLAYBACK_CANCELLATIONS_TOTAL",
        cancellations,
    )

    class _HangingChunked:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(999)
            raise StopAsyncIteration

    task = asyncio.create_task(
        play_harness_turn_audio(
            turn_number=4,
            turn_def=_turn("live"),
            scenario=_scenario(),
            tenant_id="tenant-a",
            audio_source=SimpleNamespace(capture_frame=AsyncMock()),
            tts=SimpleNamespace(synthesize=Mock(return_value=_HangingChunked())),
            read_cached_turn_wav_fn=AsyncMock(return_value=None),
            publish_cached_wav_fn=AsyncMock(),
            logger_obj=SimpleNamespace(info=Mock(), debug=Mock()),
            synthesis_timeout_s=5.0,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancellations.incs == [
        {
            "provider": "openai",
            "model": "alloy",
            "source": "live",
            "reason": "task_cancelled",
            "scenario_kind": "graph",
        }
    ]
