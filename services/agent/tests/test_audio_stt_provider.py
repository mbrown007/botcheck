from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livekit.agents.stt import SpeechEventType
from src.audio import BotListener


class _FakeParticipant:
    pass


class _FakeStream:
    def __init__(self) -> None:
        self.ended = False

    def end_input(self) -> None:
        self.ended = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeSttClient:
    def __init__(self) -> None:
        self._stream = _FakeStream()

    def stream(self) -> _FakeStream:
        return self._stream


class _FakeProvider:
    provider_id = "deepgram"
    model_label = "nova-2-phonecall"

    def __init__(self) -> None:
        self.calls: list[int | None] = []

    def create_stt(self, *, plugin_module=None, endpointing_ms: int | None = None):
        del plugin_module
        self.calls.append(endpointing_ms)
        return _FakeSttClient()


def _listener_with_timing_origin() -> BotListener:
    listener = BotListener(
        _FakeParticipant(),
        _FakeProvider(),
        object(),
        endpointing_ms=1200,
    )
    listener._stream_started_monotonic = 100.0
    listener._timing_origin_stream_s = 1.0
    return listener


@pytest.mark.asyncio
async def test_bot_listener_rebuilds_stt_via_provider_boundary() -> None:
    provider = _FakeProvider()
    listener = BotListener(
        _FakeParticipant(),
        provider,
        object(),
        endpointing_ms=1200,
    )

    await listener.swap_stt(400)

    assert provider.calls == [1200, 400]


@pytest.mark.asyncio
async def test_bot_listener_publishes_stt_circuit_states(monkeypatch) -> None:
    provider = _FakeProvider()
    published: list[dict[str, str]] = []

    async def _publish(**kwargs) -> None:
        published.append({key: str(value) for key, value in kwargs.items() if key != "observed_at"})

    class _Bridge:
        def mark_closed(self, *, reason: str) -> None:
            del reason
            asyncio.create_task(
                _publish(
                    source="agent",
                    provider="deepgram",
                    service="stt",
                    component="agent_live_stt",
                    state="closed",
                )
            )

        def mark_open(self, *, reason: str) -> None:
            del reason
            asyncio.create_task(
                _publish(
                    source="agent",
                    provider="deepgram",
                    service="stt",
                    component="agent_live_stt",
                    state="open",
                )
            )

    listener = BotListener(
        _FakeParticipant(),
        provider,
        object(),
        endpointing_ms=1200,
        stt_circuit_bridge=_Bridge(),
    )

    class _EmptyAudioStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    monkeypatch.setattr(
        "src.audio.rtc.AudioStream.from_participant",
        lambda **kwargs: _EmptyAudioStream(),
    )

    class _BadClient:
        def stream(self):
            raise RuntimeError("stream down")

    listener._stt = _BadClient()
    with pytest.raises(RuntimeError, match="stream down"):
        await listener.start()

    await asyncio.sleep(0)
    assert published[-1] == {
        "source": "agent",
        "provider": "deepgram",
        "service": "stt",
        "component": "agent_live_stt",
        "state": "open",
    }


def test_bot_listener_normalizes_utterance_relative_transcript_timing() -> None:
    listener = _listener_with_timing_origin()

    start_ms, end_ms = listener._resolve_utterance_timing_ms(
        segment_start_s=0.0,
        segment_end_s=0.32,
        listen_started_monotonic=114.0,
        listen_finished_monotonic=114.4,
    )

    assert start_ms == 13000
    assert end_ms == 13320


def test_bot_listener_preserves_absolute_stream_transcript_timing() -> None:
    listener = _listener_with_timing_origin()

    start_ms, end_ms = listener._resolve_utterance_timing_ms(
        segment_start_s=14.05,
        segment_end_s=14.42,
        listen_started_monotonic=114.0,
        listen_finished_monotonic=114.5,
    )

    assert start_ms == 13050
    assert end_ms == 13420


@pytest.mark.asyncio
async def test_bot_listener_emits_preview_events_without_changing_final_transcript() -> None:
    provider = _FakeProvider()
    listener = BotListener(
        _FakeParticipant(),
        provider,
        object(),
        endpointing_ms=1200,
    )
    previews: list[tuple[str, str]] = []

    class _PreviewStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not hasattr(self, "_events"):
                self._events = iter(
                    [
                        SimpleNamespace(
                            type=SpeechEventType.INTERIM_TRANSCRIPT,
                            alternatives=[
                                SimpleNamespace(text="Hello", start_time=0.0, end_time=0.2)
                            ],
                        ),
                        SimpleNamespace(
                            type=SpeechEventType.FINAL_TRANSCRIPT,
                            alternatives=[
                                SimpleNamespace(
                                    text="Hello there",
                                    start_time=0.0,
                                    end_time=0.4,
                                )
                            ],
                        ),
                    ]
                )
            try:
                return next(self._events)
            except StopIteration:
                raise StopAsyncIteration from None

    listener._stt_stream = _PreviewStream()
    listener._capture_enabled = True
    listener._preview_callback = lambda text, event_type: previews.append((event_type, text))

    consume_task = listener._start_consume_task()
    await consume_task

    segment = await listener._transcript_q.get()
    assert previews == [("interim", "Hello"), ("final", "Hello there")]
    assert segment.text == "Hello there"


@pytest.mark.asyncio
async def test_bot_listener_listen_for_s_uses_fixed_duration_capture(monkeypatch) -> None:
    listener = BotListener.__new__(BotListener)
    listener._transcript_q = asyncio.Queue()
    listener._last_utterance_timing_ms = None
    listener._preview_callback = None
    listener._capture_enabled = False
    listener._timing_origin_stream_s = 0.0
    listener._stream_started_monotonic = None
    listener._current_endpointing_ms = 1200

    swap_stt = AsyncMock()
    listener.swap_stt = swap_stt

    sleep_calls: list[float] = []

    async def _fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)
        if len(sleep_calls) == 1:
            # Simulate a transcript segment arriving during the fixed window.
            await listener._transcript_q.put(
                SimpleNamespace(text="Hello there", start_time_s=0.0, end_time_s=0.4)
            )

    monkeypatch.setattr("src.audio.asyncio.sleep", _fake_sleep)

    transcript = await listener.listen(
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=800,
        listen_for_s=2.5,
    )

    assert transcript == "Hello there"
    assert sleep_calls[0] == 2.5          # fixed window
    assert sleep_calls[1] == pytest.approx(0.15)  # grace period for late STT events
    swap_stt.assert_not_awaited()
    assert listener.last_utterance_timing_ms() == (0, 400)
    assert listener._capture_enabled is False


# ── T1: raising preview callback does not abort the consume loop ──────────────

@pytest.mark.asyncio
async def test_bot_listener_raising_preview_callback_does_not_abort_consume_loop() -> None:
    """A callback that raises must not prevent the final transcript from reaching the queue."""
    listener = BotListener.__new__(BotListener)
    listener._transcript_q = asyncio.Queue()
    listener._preview_callback = None

    def _bad_callback(text: str, event_type: str) -> None:
        raise RuntimeError("boom")

    class _Stream:
        def __aiter__(self):
            return self

        _events = iter([
            SimpleNamespace(
                type=getattr(SpeechEventType, "INTERIM_TRANSCRIPT", SpeechEventType.FINAL_TRANSCRIPT),
                alternatives=[SimpleNamespace(text="interim text", start_time=0.0, end_time=0.1)],
            ),
            SimpleNamespace(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[SimpleNamespace(text="final text", start_time=0.0, end_time=0.3)],
            ),
        ])

        async def __anext__(self):
            try:
                return next(self._events)
            except StopIteration:
                raise StopAsyncIteration from None

    listener._stt_stream = _Stream()
    listener._capture_enabled = True
    listener._preview_callback = _bad_callback

    consume_task = listener._start_consume_task()
    await consume_task

    segment = await listener._transcript_q.get()
    assert segment.text == "final text"


# ── T2: preview_callback=None does not leak interim events to the queue ───────

@pytest.mark.asyncio
async def test_bot_listener_no_callback_interim_does_not_reach_queue() -> None:
    """With no callback, an interim event must not put anything in _transcript_q."""
    listener = BotListener.__new__(BotListener)
    listener._transcript_q = asyncio.Queue()
    listener._preview_callback = None

    class _Stream:
        def __aiter__(self):
            return self

        _events = iter([
            SimpleNamespace(
                type=getattr(SpeechEventType, "INTERIM_TRANSCRIPT", SpeechEventType.FINAL_TRANSCRIPT),
                alternatives=[SimpleNamespace(text="interim only", start_time=0.0, end_time=0.1)],
            ),
            SimpleNamespace(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[SimpleNamespace(text="final only", start_time=0.0, end_time=0.2)],
            ),
        ])

        async def __anext__(self):
            try:
                return next(self._events)
            except StopIteration:
                raise StopAsyncIteration from None

    listener._stt_stream = _Stream()
    listener._capture_enabled = True
    # preview_callback is None — interim should never land in the queue

    consume_task = listener._start_consume_task()
    await consume_task

    assert listener._transcript_q.qsize() == 1
    segment = await listener._transcript_q.get()
    assert segment.text == "final only"


# ── T3: capture_enabled=False suppresses preview even when callback is set ────

@pytest.mark.asyncio
async def test_bot_listener_capture_disabled_suppresses_preview_callback() -> None:
    """When _capture_enabled is False (e.g. during drain), no preview callback fires."""
    listener = BotListener.__new__(BotListener)
    listener._transcript_q = asyncio.Queue()

    fired: list[str] = []

    class _Stream:
        def __aiter__(self):
            return self

        _events = iter([
            SimpleNamespace(
                type=getattr(SpeechEventType, "INTERIM_TRANSCRIPT", SpeechEventType.FINAL_TRANSCRIPT),
                alternatives=[SimpleNamespace(text="preview text", start_time=0.0, end_time=0.1)],
            ),
        ])

        async def __anext__(self):
            try:
                return next(self._events)
            except StopIteration:
                raise StopAsyncIteration from None

    listener._stt_stream = _Stream()
    listener._capture_enabled = False  # disabled — simulate drain state
    listener._preview_callback = lambda text, event_type: fired.append(text)

    consume_task = listener._start_consume_task()
    await consume_task

    assert fired == [], "Preview callback must not fire when _capture_enabled is False"
