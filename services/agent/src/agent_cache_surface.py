from __future__ import annotations

from botocore.exceptions import ClientError
from livekit import rtc

from botcheck_scenarios import ScenarioDefinition, Turn

from . import cache as _cache

CachedTurnFetchResult = _cache.CachedTurnFetchResult
TurnAudioCachePrefetcher = _cache.TurnAudioCachePrefetcher


def is_s3_missing_object(exc: ClientError) -> bool:
    return _cache.is_s3_missing_object(exc)


def cache_client_configured(*, settings_obj) -> bool:
    return _cache.cache_client_configured(settings_obj=settings_obj)


def inc_cache_fallback(reason: str, *, fallback_total) -> None:
    _cache.inc_cache_fallback(reason, fallback_total=fallback_total)


def record_cached_turn_fetch_metrics(
    *,
    result: CachedTurnFetchResult,
    scenario_kind: str,
    hits_total,
    misses_total,
    fallback_total,
) -> None:
    _cache.record_cached_turn_fetch_metrics(
        result=result,
        scenario_kind=scenario_kind,
        hits_total=hits_total,
        misses_total=misses_total,
        fallback_total=fallback_total,
    )


async def fetch_cached_turn_wav(
    *,
    scenario: ScenarioDefinition,
    turn: Turn,
    tenant_id: str,
    settings_obj,
) -> CachedTurnFetchResult:
    return await _cache.fetch_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id=tenant_id,
        settings_obj=settings_obj,
    )


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
    return await _cache.read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id=tenant_id,
        settings_obj=settings_obj,
        hits_total=hits_total,
        misses_total=misses_total,
        fallback_total=fallback_total,
    )


def iter_wav_audio_frames(
    wav_bytes: bytes,
    *,
    frame_ms: int = 20,
) -> list[rtc.AudioFrame]:
    return _cache.iter_wav_audio_frames(wav_bytes, frame_ms=frame_ms)


async def publish_cached_wav(audio_source: rtc.AudioSource, wav_bytes: bytes) -> None:
    await _cache.publish_cached_wav(audio_source, wav_bytes)
