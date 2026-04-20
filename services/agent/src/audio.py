from __future__ import annotations

import asyncio
import logging
import time
import wave
from dataclasses import dataclass
from inspect import isawaitable
from pathlib import Path
from typing import Any, Callable

from livekit import rtc
from livekit.agents.stt import SpeechEventType

from botcheck_scenarios import STTProvider

from .config import settings
from .media_engine import AgentSttCircuitBridge

logger = logging.getLogger("botcheck.agent")

RELATIVE_TRANSCRIPT_TIMING_TOLERANCE_S = 0.75


@dataclass
class TranscriptSegment:
    text: str
    start_time_s: float
    end_time_s: float


PreviewTranscriptCallback = Callable[[str, str], Any]


class BotAudioRecorder:
    """Capture bot-leg and harness-leg PCM frames and persist a stereo WAV artifact."""

    def __init__(self, *, enabled: bool, sample_rate: int = 16000, channels: int = 1) -> None:
        self.enabled = enabled
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = 2  # 16-bit PCM
        self._pcm = bytearray()
        self._harness_pcm = bytearray()
        # Resample harness TTS (24 kHz) down to the recording rate (16 kHz).
        self._harness_resampler: rtc.AudioResampler | None = (
            rtc.AudioResampler(input_rate=24000, output_rate=sample_rate, num_channels=channels)
            if enabled
            else None
        )
        self._frames_seen = 0
        self._frames_recorded = 0
        self._frames_dropped = 0
        self._frame_errors = 0
        self._timing_origin_monotonic: float | None = None

    @staticmethod
    def _extract_pcm_bytes(frame: rtc.AudioFrame) -> bytes:
        raw = getattr(frame, "data", None)
        if raw is not None:
            if isinstance(raw, memoryview):
                return raw.tobytes()
            tobytes = getattr(raw, "tobytes", None)
            if callable(tobytes):
                return tobytes()
            return bytes(raw)

        # Fallback path for SDK/runtime variants that expose only WAV bytes.
        wav_payload = frame.to_wav_bytes()
        if wav_payload[:4] == b"RIFF" and len(wav_payload) > 44:
            return wav_payload[44:]
        return wav_payload

    def capture_frame(self, frame: rtc.AudioFrame) -> None:
        if not self.enabled:
            return
        self._frames_seen += 1
        try:
            chunk = self._extract_pcm_bytes(frame)
        except Exception:
            self._frame_errors += 1
            logger.warning("Failed to serialize audio frame for recording", exc_info=True)
            return
        if chunk:
            self._pcm.extend(chunk)
            self._frames_recorded += 1
        else:
            self._frames_dropped += 1

    def mark_timing_origin(self, origin_monotonic: float | None = None) -> None:
        self._timing_origin_monotonic = origin_monotonic

    def _pad_harness_to_elapsed_ms(self, elapsed_ms: int) -> None:
        target_bytes = max(
            0,
            int((elapsed_ms / 1000.0) * self._sample_rate) * self._channels * self._sample_width,
        )
        if len(self._harness_pcm) < target_bytes:
            self._harness_pcm.extend(b"\x00" * (target_bytes - len(self._harness_pcm)))

    def capture_harness_frame(self, frame: rtc.AudioFrame, *, elapsed_ms: int | None = None) -> None:
        """Resample a 24 kHz harness TTS frame to the recording rate and buffer it."""
        if not self.enabled or self._harness_resampler is None:
            return
        if elapsed_ms is None and self._timing_origin_monotonic is not None:
            elapsed_ms = max(0, int((time.monotonic() - self._timing_origin_monotonic) * 1000))
        if elapsed_ms is not None:
            self._pad_harness_to_elapsed_ms(elapsed_ms)
        try:
            for resampled in self._harness_resampler.push(frame):
                chunk = self._extract_pcm_bytes(resampled)
                if chunk:
                    self._harness_pcm.extend(chunk)
        except Exception:
            logger.warning("Failed to resample harness audio frame for recording", exc_info=True)

    @property
    def duration_ms(self) -> int:
        if not self._pcm:
            return 0
        denom = self._sample_rate * self._channels * self._sample_width
        return int((len(self._pcm) / denom) * 1000)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "frames_seen": self._frames_seen,
            "frames_recorded": self._frames_recorded,
            "frames_dropped": self._frames_dropped,
            "frame_errors": self._frame_errors,
            "pcm_bytes": len(self._pcm),
            "harness_pcm_bytes": len(self._harness_pcm),
            "duration_ms": self.duration_ms,
        }

    def reset(self) -> None:
        """Reset buffered PCM so recording timeline can align with conversation time zero."""
        self._pcm.clear()
        self._harness_pcm.clear()
        self._frames_seen = 0
        self._frames_recorded = 0
        self._frames_dropped = 0
        self._frame_errors = 0
        self._timing_origin_monotonic = None

    async def write_wav(self, run_id: str) -> Path | None:
        if not self.enabled:
            return None
        if not self._pcm and not self._harness_pcm:
            logger.info("Run %s: no audio captured for recording (%s)", run_id, self.stats)
            return None

        out_path = Path(settings.recording_tmp_dir) / f"{run_id}.wav"
        has_both = bool(self._pcm) and bool(self._harness_pcm)
        bot_pcm = bytes(self._pcm)
        harness_pcm = bytes(self._harness_pcm)
        sample_rate = self._sample_rate
        sample_width = self._sample_width

        def _write() -> None:
            import array as _array

            out_path.parent.mkdir(parents=True, exist_ok=True)
            if has_both:
                # Stereo WAV: L = harness caller, R = bot.
                # Pad the shorter leg with silence so both tracks stay in sync.
                max_samples = max(len(bot_pcm), len(harness_pcm) + 1) // 2
                h_pad = harness_pcm + b"\x00" * max(0, max_samples * 2 - len(harness_pcm))
                b_pad = bot_pcm + b"\x00" * max(0, max_samples * 2 - len(bot_pcm))
                h_arr = _array.array("h", h_pad)
                b_arr = _array.array("h", b_pad)
                stereo = _array.array("h", [0] * (max_samples * 2))
                stereo[0::2] = h_arr  # L
                stereo[1::2] = b_arr  # R
                with wave.open(str(out_path), "wb") as wav_file:
                    wav_file.setnchannels(2)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(stereo.tobytes())
            else:
                pcm = bot_pcm or harness_pcm
                with wave.open(str(out_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(pcm)

        await asyncio.to_thread(_write)
        logger.info("Run %s: recording written stereo=%s (%s)", run_id, has_both, self.stats)
        return out_path


class RecordingAudioSource:
    """
    Thin proxy around rtc.AudioSource that taps every harness frame into the recorder.

    All calls to capture_frame() are forwarded to the real audio source *and* the
    PCM is resampled (24 kHz → 16 kHz) and buffered in BotAudioRecorder._harness_pcm.
    This catches both live-TTS frames (scenario_harness_audio.py) and cached-WAV
    frames (cache.py:publish_cached_wav) in a single place.
    """

    def __init__(self, source: rtc.AudioSource, recorder: "BotAudioRecorder") -> None:
        self._source = source
        self._recorder = recorder

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        await self._source.capture_frame(frame)
        self._recorder.capture_harness_frame(frame)


class BotListener:
    """
    Pipes the bot's audio track directly into the configured streaming STT session.

    Avoids Silero VAD entirely — Silero VAD is unreliable with chunked TTS audio
    (e.g. OpenAI TTS) because inter-chunk silence triggers premature END_OF_SPEECH.
    Provider-native endpointing (endpointing_ms for Deepgram in this slice) handles
    utterance boundaries instead.

    A single STT stream is kept open for the whole run. listen() toggles capture
    windows and consumes FINAL_TRANSCRIPT segments from an internal queue.

    Per-turn endpointing_ms overrides are supported via swap_stt(): the feed task
    keeps running (audio frames are queued in the audio_stream) while only the
    current STT stream is replaced.
    """

    def __init__(
        self,
        participant: rtc.RemoteParticipant,
        stt_provider: STTProvider,
        stt_plugin_module: Any,
        on_audio_frame: Callable[[rtc.AudioFrame], None] | None = None,
        *,
        endpointing_ms: int = 2000,
        stt_circuit_bridge: AgentSttCircuitBridge | None = None,
    ) -> None:
        self._participant = participant
        self.provider_id = str(getattr(stt_provider, "provider_id", "deepgram")).strip().lower() or "deepgram"
        self.model_label = str(getattr(stt_provider, "model_label", "base")).strip() or "base"
        self._stt_provider = stt_provider
        self._stt_plugin_module = stt_plugin_module
        self._stt_circuit_bridge = stt_circuit_bridge
        self._on_audio_frame = on_audio_frame
        self._current_endpointing_ms = endpointing_ms
        self._capture_enabled = False
        self._transcript_q: asyncio.Queue[TranscriptSegment] = asyncio.Queue()
        self._stream_started_monotonic: float | None = None
        self._timing_origin_stream_s: float = 0.0
        self._last_utterance_timing_ms: tuple[int, int] | None = None
        self._audio_stream = None
        self._stt_stream = None
        self._feed_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._consume_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._preview_callback: PreviewTranscriptCallback | None = None
        self._stt = self._make_stt(endpointing_ms)

    def _mark_provider_open(self, *, reason: str) -> None:
        if self._stt_circuit_bridge is not None:
            self._stt_circuit_bridge.mark_open(reason=reason)

    def _mark_provider_closed(self, *, reason: str) -> None:
        if self._stt_circuit_bridge is not None:
            self._stt_circuit_bridge.mark_closed(reason=reason)

    def _make_stt(self, endpointing_ms: int):
        try:
            return self._stt_provider.create_stt(
                plugin_module=self._stt_plugin_module,
                endpointing_ms=endpointing_ms,
            )
        except Exception as exc:
            self._mark_provider_open(reason=f"create_failed:{type(exc).__name__}")
            raise

    def _start_consume_task(self) -> "asyncio.Task[None]":
        """Spawn a consume task for the current self._stt_stream."""
        stt_stream = self._stt_stream

        async def _consume() -> None:
            if stt_stream is None:
                return
            async for event in stt_stream:
                if event.type not in {
                    SpeechEventType.FINAL_TRANSCRIPT,
                    getattr(SpeechEventType, "INTERIM_TRANSCRIPT", None),
                }:
                    continue
                if not event.alternatives:
                    continue
                alt = event.alternatives[0]
                text = alt.text
                if text:
                    # Asyncio-safety: both _consume and listen() run on the same
                    # single-threaded event loop, so there is no concurrent write.
                    # We take a local snapshot of _preview_callback here so that
                    # any in-flight callback invocation (suspended at the await
                    # below) uses the value that was current when it started, even
                    # if listen() clears _preview_callback in its finally block
                    # before the await completes.
                    preview_callback = self._preview_callback if self._capture_enabled else None
                    if preview_callback is not None:
                        event_type = (
                            "final"
                            if event.type == SpeechEventType.FINAL_TRANSCRIPT
                            else "interim"
                        )
                        try:
                            callback_result = preview_callback(text, event_type)
                            if isawaitable(callback_result):
                                await callback_result
                        except Exception:
                            logger.warning("Failed to handle transcript preview event", exc_info=True)
                if text and event.type == SpeechEventType.FINAL_TRANSCRIPT:
                    await self._transcript_q.put(
                        TranscriptSegment(
                            text=text,
                            start_time_s=float(getattr(alt, "start_time", 0.0) or 0.0),
                            end_time_s=float(getattr(alt, "end_time", 0.0) or 0.0),
                        )
                    )

        return asyncio.create_task(_consume())

    async def start(self) -> None:
        self._stream_started_monotonic = asyncio.get_event_loop().time()
        self._audio_stream = rtc.AudioStream.from_participant(
            participant=self._participant,
            track_source=rtc.TrackSource.SOURCE_MICROPHONE,
            sample_rate=16000,
            num_channels=1,
        )
        try:
            self._stt_stream = self._stt.stream()
        except Exception as exc:
            self._mark_provider_open(reason=f"stream_start_failed:{type(exc).__name__}")
            raise

        async def _feed() -> None:
            async for frame_event in self._audio_stream:
                if self._on_audio_frame is not None:
                    self._on_audio_frame(frame_event.frame)
                if not self._capture_enabled or self._stt_stream is None:
                    continue
                try:
                    self._stt_stream.push_frame(frame_event.frame)
                except Exception:
                    # A single failed push (e.g. during STT stream swap) is not
                    # fatal — skip the frame and continue rather than killing the feed.
                    logger.debug("Skipped audio frame push during STT stream transition")

        self._feed_task = asyncio.create_task(_feed())
        self._consume_task = self._start_consume_task()
        self._mark_provider_closed(reason="session_started")

    def mark_timing_origin(self) -> None:
        if self._stream_started_monotonic is None:
            self._timing_origin_stream_s = 0.0
            return
        now = asyncio.get_event_loop().time()
        self._timing_origin_stream_s = max(0.0, now - self._stream_started_monotonic)

    def last_utterance_timing_ms(self) -> tuple[int, int] | None:
        return self._last_utterance_timing_ms

    def _resolve_utterance_timing_ms(
        self,
        *,
        segment_start_s: float,
        segment_end_s: float,
        listen_started_monotonic: float,
        listen_finished_monotonic: float,
    ) -> tuple[int, int]:
        segment_start_s = max(0.0, float(segment_start_s))
        segment_end_s = max(segment_start_s, float(segment_end_s))
        absolute_start_ms = max(
            0,
            int(round((segment_start_s - self._timing_origin_stream_s) * 1000)),
        )
        absolute_end_ms = max(
            absolute_start_ms,
            int(round((segment_end_s - self._timing_origin_stream_s) * 1000)),
        )

        if self._stream_started_monotonic is None:
            return absolute_start_ms, absolute_end_ms

        call_started_monotonic = self._stream_started_monotonic + self._timing_origin_stream_s
        listen_started_ms = max(
            0,
            int(round((listen_started_monotonic - call_started_monotonic) * 1000)),
        )
        relative_start_ms = max(
            listen_started_ms,
            listen_started_ms + int(round(segment_start_s * 1000)),
        )
        relative_end_ms = max(
            relative_start_ms,
            listen_started_ms + int(round(segment_end_s * 1000)),
        )

        listen_elapsed_s = max(0.0, listen_finished_monotonic - listen_started_monotonic)
        if segment_end_s <= listen_elapsed_s + RELATIVE_TRANSCRIPT_TIMING_TOLERANCE_S:
            logger.debug(
                "Normalizing transcript timing as utterance-relative start=%.3fs end=%.3fs elapsed=%.3fs",
                segment_start_s,
                segment_end_s,
                listen_elapsed_s,
            )
            return relative_start_ms, relative_end_ms
        return absolute_start_ms, absolute_end_ms

    async def swap_stt(self, endpointing_ms: int) -> None:
        """Replace the active STT stream with a new one using a different
        endpointing_ms. Used when a turn overrides the scenario-level setting.

        The feed task keeps running; only the STT stream and consume task are swapped.
        Setting self._stt_stream = None before the await causes _feed to skip pushes
        during the transition window (asyncio single-threaded, so this is race-free
        between the two non-await assignments).
        """
        if endpointing_ms == self._current_endpointing_ms:
            return

        old_stream = self._stt_stream
        # Nulling before the await prevents _feed from pushing to a closing stream.
        self._stt_stream = None

        # Cancel consume task — its async-for is bound to the old stream reference.
        if self._consume_task is not None:
            self._consume_task.cancel()
            await asyncio.gather(self._consume_task, return_exceptions=True)

        if old_stream is not None:
            try:
                old_stream.end_input()
            except Exception:
                pass

        self._stt = self._make_stt(endpointing_ms)
        try:
            self._stt_stream = self._stt.stream()
        except Exception as exc:
            self._mark_provider_open(reason=f"stream_swap_failed:{type(exc).__name__}")
            raise
        self._current_endpointing_ms = endpointing_ms
        self._clear_transcript_queue()
        self._consume_task = self._start_consume_task()
        self._mark_provider_closed(reason="stream_swapped")
        logger.debug("STT stream swapped to endpointing_ms=%d", endpointing_ms)

    def _clear_transcript_queue(self) -> None:
        while True:
            try:
                self._transcript_q.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def drain(self, duration_s: float = 2.0) -> None:
        """Discard audio for duration_s seconds (e.g. discard bot's initial greeting)."""
        self._capture_enabled = False
        self._clear_transcript_queue()
        await asyncio.sleep(duration_s)
        self._clear_transcript_queue()

    async def listen(
        self,
        timeout_s: float,
        merge_window_s: float = 1.5,
        stt_endpointing_ms: int | None = None,
        listen_for_s: float | None = None,
        preview_callback: PreviewTranscriptCallback | None = None,
    ) -> str:
        """
        Capture one bot utterance using the persistent Deepgram stream and
        return the accumulated transcript once the sentence is complete.

        Deepgram fires FINAL_TRANSCRIPT whenever endpointing_ms of silence
        passes. OpenAI TTS delivers audio in chunks with inter-chunk gaps that
        can exceed that threshold, so a single bot response may produce several
        FINAL_TRANSCRIPT events. This method collects all of them, restarting
        a merge_window_s timer on each arrival. When the timer expires without
        a new segment, the sentence is considered complete.

        A small grace window is applied after timeout_s to capture trailing
        transcripts that arrive just after the deadline.

        If stt_endpointing_ms differs from the current stream's setting, the STT
        stream is swapped before capture begins.
        """
        if listen_for_s is None and stt_endpointing_ms is not None:
            try:
                await self.swap_stt(stt_endpointing_ms)
            except Exception as exc:
                self._mark_provider_open(reason=f"listen_swap_failed:{type(exc).__name__}")
                raise
        self._clear_transcript_queue()
        self._last_utterance_timing_ms = None
        self._preview_callback = preview_callback
        self._capture_enabled = True

        segments: list[str] = []
        segment_start_s: float | None = None
        segment_end_s: float | None = None
        loop = asyncio.get_event_loop()
        listen_started_monotonic = loop.time()
        try:
            if listen_for_s is not None:
                # Fixed-duration capture: wait the full window, then drain whatever
                # the STT pipeline has queued.  A short grace period after the sleep
                # lets in-flight Deepgram events (typically <200 ms) land before the
                # drain so trailing speech is not silently discarded.
                await asyncio.sleep(listen_for_s)
                await asyncio.sleep(0.15)
                while True:
                    try:
                        segment = self._transcript_q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    text = segment.text
                    if not text:
                        continue
                    segments.append(text)
                    if segment_start_s is None:
                        segment_start_s = segment.start_time_s
                    segment_end_s = max(segment_end_s or 0.0, segment.end_time_s)
            else:
                hard_deadline = loop.time() + timeout_s + 0.75
                merge_deadline: float | None = None
                while True:
                    now = loop.time()
                    if merge_deadline is not None and now >= merge_deadline:
                        break
                    if merge_deadline is None and now >= hard_deadline:
                        break

                    if merge_deadline is None:
                        timeout = max(0.0, hard_deadline - now)
                    else:
                        timeout = max(0.0, merge_deadline - now)
                    if timeout <= 0:
                        continue

                    try:
                        segment = await asyncio.wait_for(self._transcript_q.get(), timeout=timeout)
                    except asyncio.TimeoutError:
                        continue

                    text = segment.text
                    if not text:
                        continue
                    segments.append(text)
                    if segment_start_s is None:
                        segment_start_s = segment.start_time_s
                    segment_end_s = max(segment_end_s or 0.0, segment.end_time_s)
                    merge_deadline = loop.time() + merge_window_s
        finally:
            self._capture_enabled = False
            self._preview_callback = None

        if not segments:
            return "(timeout)"
        if segment_start_s is not None and segment_end_s is not None:
            start_ms, end_ms = self._resolve_utterance_timing_ms(
                segment_start_s=segment_start_s,
                segment_end_s=segment_end_s,
                listen_started_monotonic=listen_started_monotonic,
                listen_finished_monotonic=loop.time(),
            )
            self._last_utterance_timing_ms = (start_ms, end_ms)
        return " ".join(segments)

    async def stop(self) -> None:
        self._capture_enabled = False
        if self._stt_stream is not None:
            try:
                self._stt_stream.end_input()
            except Exception:
                logger.debug("Deepgram stream already closed")
        if self._feed_task:
            self._feed_task.cancel()
        if self._consume_task:
            self._consume_task.cancel()
        await asyncio.gather(
            *(t for t in (self._feed_task, self._consume_task) if t is not None),
            return_exceptions=True,
        )


async def wait_for_bot(
    room: rtc.Room,
    *,
    timeout_s: float = 60.0,
) -> rtc.RemoteParticipant:
    for participant in room.remote_participants.values():
        return participant

    joined: asyncio.Future[rtc.RemoteParticipant] = asyncio.get_event_loop().create_future()

    @room.on("participant_connected")
    def _cb(participant: rtc.RemoteParticipant) -> None:
        if not joined.done():
            joined.set_result(participant)

    return await asyncio.wait_for(joined, timeout=timeout_s)
