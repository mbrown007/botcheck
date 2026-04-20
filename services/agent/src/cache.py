from __future__ import annotations

import asyncio
import io
import logging
import wave
from dataclasses import dataclass

import aioboto3
from botocore.exceptions import ClientError
from livekit import rtc

from botcheck_scenarios import ScenarioDefinition, Turn

from .scenario_kind import AI_RUNTIME_TAG

logger = logging.getLogger("botcheck.agent")


@dataclass(frozen=True)
class CachedTurnFetchResult:
    wav_bytes: bytes | None
    outcome: str


def is_s3_missing_object(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def cache_client_configured(*, settings_obj) -> bool:
    return bool(
        settings_obj.tts_cache_enabled
        and settings_obj.s3_access_key
        and settings_obj.s3_secret_key
    )


def inc_cache_fallback(reason: str, *, fallback_total) -> None:
    fallback_total.labels(reason=reason).inc()


def _scenario_kind_for_cache_metrics(*, scenario: ScenarioDefinition) -> str:
    return "ai" if AI_RUNTIME_TAG in scenario.tags else "graph"


def record_cached_turn_fetch_metrics(
    *,
    result: CachedTurnFetchResult,
    scenario_kind: str,
    hits_total,
    misses_total,
    fallback_total,
) -> None:
    if result.outcome == "hit":
        hits_total.labels(scenario_kind=scenario_kind).inc()
    elif result.outcome == "miss":
        misses_total.labels(scenario_kind=scenario_kind).inc()
    elif result.outcome in {"missing_body", "s3_error", "unexpected_error"}:
        inc_cache_fallback(result.outcome, fallback_total=fallback_total)


async def fetch_cached_turn_wav(
    *,
    scenario: ScenarioDefinition,
    turn: Turn,
    tenant_id: str,
    settings_obj,
) -> CachedTurnFetchResult:
    if not cache_client_configured(settings_obj=settings_obj):
        return CachedTurnFetchResult(wav_bytes=None, outcome="disabled")

    key = scenario.turn_cache_key(
        turn,
        tenant_id,
        pcm_format_version=settings_obj.tts_cache_pcm_format_version,
    )
    session = aioboto3.Session(
        aws_access_key_id=settings_obj.s3_access_key,
        aws_secret_access_key=settings_obj.s3_secret_key,
        region_name=settings_obj.s3_region,
    )
    try:
        async with session.client("s3", endpoint_url=settings_obj.s3_endpoint_url) as s3:
            obj = await s3.get_object(Bucket=settings_obj.s3_bucket_prefix, Key=key)
            body = obj.get("Body")
            if body is None:
                logger.warning("TTS cache object missing body for key %s", key)
                return CachedTurnFetchResult(wav_bytes=None, outcome="missing_body")
            audio_bytes = await body.read()
        return CachedTurnFetchResult(wav_bytes=audio_bytes, outcome="hit")
    except ClientError as exc:
        if is_s3_missing_object(exc):
            return CachedTurnFetchResult(wav_bytes=None, outcome="miss")
        logger.warning("TTS cache read error for turn %s — fallback to live TTS", turn.id)
        return CachedTurnFetchResult(wav_bytes=None, outcome="s3_error")
    except Exception:
        logger.warning("TTS cache unexpected error for turn %s — fallback to live TTS", turn.id)
        return CachedTurnFetchResult(wav_bytes=None, outcome="unexpected_error")


async def read_cached_turn_wav(
    *,
    scenario: ScenarioDefinition,
    turn: Turn,
    tenant_id: str,
    settings_obj,
    hits_total,
    misses_total,
    fallback_total,
) -> bytes | None:
    result = await fetch_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id=tenant_id,
        settings_obj=settings_obj,
    )
    record_cached_turn_fetch_metrics(
        result=result,
        scenario_kind=_scenario_kind_for_cache_metrics(scenario=scenario),
        hits_total=hits_total,
        misses_total=misses_total,
        fallback_total=fallback_total,
    )
    return result.wav_bytes


class TurnAudioCachePrefetcher:
    def __init__(
        self,
        *,
        scenario: ScenarioDefinition,
        tenant_id: str,
        settings_obj,
        hits_total,
        misses_total,
        fallback_total,
        logger_obj=None,
        max_concurrency: int = 4,
    ) -> None:
        self._scenario = scenario
        self._tenant_id = tenant_id
        self._settings = settings_obj
        self._hits_total = hits_total
        self._misses_total = misses_total
        self._fallback_total = fallback_total
        self._logger = logger_obj
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._tasks: dict[str, asyncio.Task[CachedTurnFetchResult]] = {}
        self._results: dict[str, CachedTurnFetchResult] = {}
        self._started = False

    def start(self) -> None:
        if self._started or not cache_client_configured(settings_obj=self._settings):
            return
        self._started = True
        for turn in self._cacheable_turns():
            if turn.id in self._tasks:
                continue
            self._tasks[turn.id] = asyncio.create_task(
                self._prefetch_turn(turn),
                name=f"tts-cache-prefetch:{turn.id}",
            )

    async def get(self, *, turn: Turn) -> bytes | None:
        result = await self._resolve_turn(turn)
        record_cached_turn_fetch_metrics(
            result=result,
            scenario_kind=_scenario_kind_for_cache_metrics(scenario=self._scenario),
            hits_total=self._hits_total,
            misses_total=self._misses_total,
            fallback_total=self._fallback_total,
        )
        return result.wav_bytes

    def cancel(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()

    def _cacheable_turns(self) -> tuple[Turn, ...]:
        return tuple(
            turn
            for turn in self._scenario.turns
            if turn.kind == "harness_prompt" and bool((turn.content.text or "").strip())
        )

    async def _prefetch_turn(self, turn: Turn) -> CachedTurnFetchResult:
        async with self._semaphore:
            result = await fetch_cached_turn_wav(
                scenario=self._scenario,
                turn=turn,
                tenant_id=self._tenant_id,
                settings_obj=self._settings,
            )
            self._results[turn.id] = result
            return result

    async def _resolve_turn(self, turn: Turn) -> CachedTurnFetchResult:
        cached = self._results.get(turn.id)
        if cached is not None:
            return cached

        task = self._tasks.get(turn.id)
        if task is not None:
            try:
                result = await task
            except Exception:
                if self._logger is not None:
                    self._logger.warning(
                        "TTS cache prefetch failed for turn %s — falling back to live lookup",
                        turn.id,
                        exc_info=True,
                    )
                result = CachedTurnFetchResult(
                    wav_bytes=None,
                    outcome="unexpected_error",
                )
            self._results[turn.id] = result
            return result

        result = await fetch_cached_turn_wav(
            scenario=self._scenario,
            turn=turn,
            tenant_id=self._tenant_id,
            settings_obj=self._settings,
        )
        self._results[turn.id] = result
        return result


def iter_wav_audio_frames(
    wav_bytes: bytes,
    *,
    frame_ms: int = 20,
) -> list[rtc.AudioFrame]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        if sample_width != 2:
            raise ValueError(f"Unsupported WAV sample width: {sample_width * 8} bits")
        pcm = wav_file.readframes(wav_file.getnframes())

    bytes_per_sample = sample_width * channels
    frame_samples = max(1, int(sample_rate * (frame_ms / 1000)))
    frame_size = frame_samples * bytes_per_sample
    frames: list[rtc.AudioFrame] = []

    for idx in range(0, len(pcm), frame_size):
        chunk = pcm[idx : idx + frame_size]
        samples_per_channel = len(chunk) // bytes_per_sample
        if samples_per_channel <= 0:
            continue
        frames.append(
            rtc.AudioFrame(
                data=chunk,
                sample_rate=sample_rate,
                num_channels=channels,
                samples_per_channel=samples_per_channel,
            )
        )
    return frames


async def publish_cached_wav(audio_source: rtc.AudioSource, wav_bytes: bytes) -> None:
    for frame in iter_wav_audio_frames(wav_bytes):
        await audio_source.capture_frame(frame)
