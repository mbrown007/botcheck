from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from botcheck_scenarios import CircuitOpenError
from livekit.agents import APIConnectOptions

from .config import settings
from .metrics import (
    PROVIDER_API_CALLS_TOTAL,
    TTS_CHARACTERS_TOTAL,
    TTS_FIRST_BYTE_LATENCY_SECONDS,
    TTS_LIVE_FAILURES_TOTAL,
    TTS_PLAYBACK_CANCELLATIONS_TOTAL,
    TTS_PLAYBACK_LATENCY_SECONDS,
    TTS_STREAM_DURATION_SECONDS,
)


@dataclass(frozen=True)
class HarnessPlaybackResult:
    completed: bool
    cancelled: bool
    source: str


class _PlaybackCancelled(Exception):
    def __init__(self, *, source: str, reason: str) -> None:
        super().__init__(f"playback cancelled ({source}:{reason})")
        self.source = source
        self.reason = reason


async def play_harness_turn_audio(
    *,
    turn_number: int,
    turn_def,
    scenario,
    tenant_id: str,
    audio_source,
    tts,
    read_cached_turn_wav_fn,
    publish_cached_wav_fn,
    tts_live_circuit_breaker=None,
    tts_circuit_bridge=None,
    logger_obj=None,
    monotonic_fn=time.monotonic,
    synthesis_timeout_s: float | None = None,
    scenario_kind: str = "graph",
    cancel_event: asyncio.Event | None = None,
) -> HarnessPlaybackResult:
    prompt_text = turn_def.content.text or ""
    if not prompt_text:
        return HarnessPlaybackResult(completed=True, cancelled=False, source="none")

    if logger_obj is not None:
        logger_obj.info("Turn %d [harness]: %s", turn_number, prompt_text[:80])

    provider_label = str(getattr(tts, "provider_id", "openai")).strip().lower() or "openai"
    model_label = str(getattr(tts, "model_label", scenario.config.tts_voice)).strip() or (
        scenario.config.tts_voice
    )

    def _record_cancellation(*, source: str, reason: str) -> None:
        TTS_PLAYBACK_CANCELLATIONS_TOTAL.labels(
            provider=("cache" if source == "cache" else provider_label),
            model=model_label,
            source=source,
            reason=reason,
            scenario_kind=scenario_kind,
        ).inc()

    def _raise_if_cancelled(*, source: str, reason: str) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _PlaybackCancelled(source=source, reason=reason)

    cached_wav = await read_cached_turn_wav_fn(
        scenario=scenario,
        turn=turn_def,
        tenant_id=tenant_id,
    )
    if cached_wav is not None:
        try:
            _raise_if_cancelled(source="cache", reason="pre_start")
            playback_started = monotonic_fn()
            await publish_cached_wav_fn(audio_source, cached_wav)
            # Check after the atomic publish in case cancel_event was set during playback.
            _raise_if_cancelled(source="cache", reason="in_flight")
            TTS_PLAYBACK_LATENCY_SECONDS.labels(
                provider="cache",
                model=scenario.config.tts_voice,
                source="cache",
                scenario_kind=scenario_kind,
            ).observe(max(0.0, monotonic_fn() - playback_started))
            return HarnessPlaybackResult(completed=True, cancelled=False, source="cache")
        except _PlaybackCancelled as exc:
            if logger_obj is not None:
                logger_obj.info(
                    "Skipped cached playback for turn %d (%s)",
                    turn_number,
                    exc.reason,
                )
            _record_cancellation(source=exc.source, reason=exc.reason)
            return HarnessPlaybackResult(completed=False, cancelled=True, source=exc.source)
        except asyncio.CancelledError:
            _record_cancellation(source="cache", reason="task_cancelled")
            raise

    if logger_obj is not None:
        logger_obj.debug(
            "TTS cache miss for turn %d — falling back to live TTS", turn_number
        )

    async def _synthesize_and_publish() -> None:
        request_started = monotonic_fn()
        first_frame_at: float | None = None
        conn_options = APIConnectOptions(max_retry=0, timeout=effective_timeout)
        _raise_if_cancelled(source="live", reason="pre_start")
        async with tts.synthesize(prompt_text, conn_options=conn_options) as chunked:
            async for event in chunked:
                _raise_if_cancelled(source="live", reason="in_flight")
                if first_frame_at is None:
                    first_frame_at = monotonic_fn()
                await audio_source.capture_frame(event.frame)
        if first_frame_at is not None:
            stream_finished = monotonic_fn()
            TTS_FIRST_BYTE_LATENCY_SECONDS.labels(
                provider=provider_label,
                model=model_label,
                scenario_kind=scenario_kind,
            ).observe(max(0.0, first_frame_at - request_started))
            TTS_STREAM_DURATION_SECONDS.labels(
                provider=provider_label,
                model=model_label,
                scenario_kind=scenario_kind,
            ).observe(max(0.0, stream_finished - first_frame_at))

    effective_timeout = (
        synthesis_timeout_s
        if synthesis_timeout_s is not None
        else settings.tts_live_synthesis_timeout_s
    )

    async def _run() -> None:
        if tts_live_circuit_breaker is None:
            await _synthesize_and_publish()
        else:
            await tts_live_circuit_breaker.call(
                _synthesize_and_publish,
                on_transition=tts_circuit_bridge.on_transition if tts_circuit_bridge else None,
                on_reject=tts_circuit_bridge.on_reject if tts_circuit_bridge else None,
            )

    try:
        playback_started = monotonic_fn()
        await asyncio.wait_for(_run(), timeout=effective_timeout)

        TTS_CHARACTERS_TOTAL.labels(
            provider=provider_label,
            model=model_label,
            scenario_kind=scenario_kind,
        ).inc(len(prompt_text))
        TTS_PLAYBACK_LATENCY_SECONDS.labels(
            provider=provider_label,
            model=model_label,
            source="live",
            scenario_kind=scenario_kind,
        ).observe(max(0.0, monotonic_fn() - playback_started))
        PROVIDER_API_CALLS_TOTAL.labels(
            provider=provider_label, service="tts", model=model_label, outcome="success"
        ).inc()
        return HarnessPlaybackResult(completed=True, cancelled=False, source="live")

    except _PlaybackCancelled as exc:
        if logger_obj is not None:
            logger_obj.info(
                "Cancelled live TTS playback for turn %d (%s)",
                turn_number,
                exc.reason,
            )
        _record_cancellation(source=exc.source, reason=exc.reason)
        return HarnessPlaybackResult(completed=False, cancelled=True, source=exc.source)

    except asyncio.CancelledError:
        _record_cancellation(source="live", reason="task_cancelled")
        raise

    except asyncio.TimeoutError:
        elapsed = monotonic_fn() - playback_started
        if logger_obj is not None:
            logger_obj.error(
                "TTS synthesis timed out after %.1fs for turn %d (limit=%.0fs model=%s)",
                elapsed,
                turn_number,
                effective_timeout,
                model_label,
            )
        TTS_LIVE_FAILURES_TOTAL.labels(
            provider=provider_label,
            model=model_label,
            reason="timeout",
            scenario_kind=scenario_kind,
        ).inc()
        PROVIDER_API_CALLS_TOTAL.labels(
            provider=provider_label, service="tts", model=model_label, outcome="timeout"
        ).inc()
        raise RuntimeError(
            f"TTS synthesis timed out after {effective_timeout:.0f}s (turn {turn_number})"
        ) from None

    except CircuitOpenError as exc:
        TTS_LIVE_FAILURES_TOTAL.labels(
            provider=provider_label,
            model=model_label,
            reason="circuit_open",
            scenario_kind=scenario_kind,
        ).inc()
        PROVIDER_API_CALLS_TOTAL.labels(
            provider=provider_label, service="tts", model=model_label, outcome="circuit_open"
        ).inc()
        raise RuntimeError("Live TTS circuit is open") from exc

    except Exception:
        elapsed = monotonic_fn() - playback_started
        if logger_obj is not None:
            logger_obj.error(
                "TTS synthesis error after %.1fs for turn %d (model=%s)",
                elapsed,
                turn_number,
                model_label,
                exc_info=True,
            )
        TTS_LIVE_FAILURES_TOTAL.labels(
            provider=provider_label,
            model=model_label,
            reason="error",
            scenario_kind=scenario_kind,
        ).inc()
        PROVIDER_API_CALLS_TOTAL.labels(
            provider=provider_label, service="tts", model=model_label, outcome="error"
        ).inc()
        raise
