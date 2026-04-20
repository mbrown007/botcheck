"""ARQ worker for Phase 7 TTS cache warming/purging."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import aioboto3
import httpx
from arq import cron
from arq.connections import RedisSettings as ArqRedisSettings
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from botcheck_scenarios import (
    CircuitOpenError,
    CircuitTransition,
    ScenarioDefinition,
)

from .. import metrics as judge_metrics
from ..config import settings
from ..provider_runtime_context import RuntimeSettingsOverlay, build_settings_overrides
from ..telemetry import instrument_httpx, setup_tracing
from ..tts_provider import (
    get_cache_warm_tts_circuit_breaker,
    resolve_cache_warm_tts_provider,
)

logger = logging.getLogger("botcheck.judge.cache")


class WarmCachePayload(BaseModel):
    scenario_id: str
    tenant_id: str
    scenario_version_hash: str
    scenario_payload: dict[str, Any]


class PurgeCachePayload(BaseModel):
    scenario_id: str
    tenant_id: str
    turn_ids: list[str] = Field(default_factory=list)


def _api_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.judge_secret}"}


async def _fetch_provider_runtime_context(
    *,
    tenant_id: str,
    tts_voice: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
        timeout=5.0,
    ) as http:
        resp = await http.post(
            "/providers/internal/runtime-context",
            json={
                "tenant_id": tenant_id,
                "runtime_scope": "judge",
                "tts_voice": tts_voice,
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def _post_provider_circuit_state(
    provider: str,
    state: str,
    observed_at: datetime,
) -> None:
    if state not in {"open", "half_open", "closed"}:
        return
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
        timeout=5.0,
    ) as http:
        resp = await http.post(
            "/internal/provider-circuits/state",
            json={
                "source": "judge",
                "provider": provider,
                "service": "tts",
                "component": "judge_cache_warm",
                "state": state,
                "observed_at": observed_at.isoformat(),
            },
        )
        resp.raise_for_status()


def _manifest_key(*, tenant_id: str, scenario_id: str) -> str:
    tenant_prefix = (tenant_id or "default").strip() or "default"
    return f"{tenant_prefix}/tts-cache/{scenario_id}/manifest.json"


def _is_manifest_key(key: str) -> bool:
    parts = key.split("/")
    return (
        len(parts) == 4
        and parts[1] == "tts-cache"
        and parts[3] == "manifest.json"
    )


def _is_tts_cache_key(key: str) -> bool:
    parts = key.split("/")
    return len(parts) >= 3 and parts[1] == "tts-cache"


def _is_missing_object_error(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _record_cache_tts_transition(*, provider: str, transition: CircuitTransition) -> None:
    judge_metrics.PROVIDER_CIRCUIT_TRANSITIONS_TOTAL.labels(
        provider=provider,
        service="tts",
        component="judge_cache_warm",
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
    ).inc()
    judge_metrics.set_provider_circuit_state(
        source="judge",
        provider=provider,
        service="tts",
        component="judge_cache_warm",
        state=transition.to_state.value,
    )
    logger.warning(
        "provider_circuit_transition provider=%s service=tts component=judge_cache_warm from=%s to=%s reason=%s",
        provider,
        transition.from_state.value,
        transition.to_state.value,
        transition.reason,
    )


def _record_cache_tts_reject(*, provider: str, state_obj) -> None:
    judge_metrics.PROVIDER_CIRCUIT_REJECTIONS_TOTAL.labels(
        provider=provider,
        service="tts",
        component="judge_cache_warm",
    ).inc()
    judge_metrics.set_provider_circuit_state(
        source="judge",
        provider=provider,
        service="tts",
        component="judge_cache_warm",
        state=str(getattr(state_obj, "value", state_obj)),
    )
    logger.warning(
        "provider_circuit_rejected provider=%s service=tts component=judge_cache_warm",
        provider,
    )


def _derive_cache_status(*, total: int, cached: int, skipped: int, failed: int) -> str:
    if total <= 0:
        return "warm"
    if failed == 0 and (cached + skipped) == total:
        return "warm"
    if (cached + skipped) == 0:
        return "cold"
    return "partial"


async def _synthesize_to_wav(
    *,
    text: str,
    tts_voice: str,
    settings_obj=settings,
    publish_state_fn: Callable[[str, str, datetime], Awaitable[None]] | None = None,
) -> bytes:
    tts_provider = resolve_cache_warm_tts_provider(tts_voice, settings_obj=settings_obj)
    breaker = get_cache_warm_tts_circuit_breaker(tts_provider.provider_id)
    judge_metrics.set_provider_circuit_state(
        source="judge",
        provider=tts_provider.provider_id,
        service="tts",
        component="judge_cache_warm",
        state="unknown",
    )

    async def _request() -> bytes:
        return await tts_provider.synthesize_wav(
            text=text,
            timeout_s=settings.tts_cache_request_timeout_s,
            response_format="wav",
        )

    def _publish_state(state: str) -> None:
        if publish_state_fn is None:
            return
        task = asyncio.create_task(
            publish_state_fn(tts_provider.provider_id, state, datetime.now(UTC))
        )

        def _on_done(done: asyncio.Task[None]) -> None:
            try:
                done.result()
            except Exception:
                logger.warning(
                    "provider_circuit_snapshot_publish_failed source=judge provider=%s service=tts component=judge_cache_warm",
                    tts_provider.provider_id,
                    exc_info=True,
                )

        task.add_done_callback(_on_done)

    def _on_transition(transition: CircuitTransition) -> None:
        _record_cache_tts_transition(
            provider=tts_provider.provider_id,
            transition=transition,
        )
        _publish_state(transition.to_state.value)

    def _on_reject(state: object) -> None:
        _record_cache_tts_reject(
            provider=tts_provider.provider_id,
            state_obj=state,
        )
        _publish_state(str(getattr(state, "value", state)).strip().lower())

    try:
        audio = await breaker.call(
            _request,
            on_transition=_on_transition,
            on_reject=_on_reject,
        )
    except CircuitOpenError as exc:
        judge_metrics.PROVIDER_API_CALLS_TOTAL.labels(
            provider=tts_provider.provider_id,
            service="tts",
            model=tts_provider.model_label,
            outcome="circuit_open",
        ).inc()
        raise RuntimeError("TTS cache warm circuit is open") from exc
    except Exception:
        judge_metrics.PROVIDER_API_CALLS_TOTAL.labels(
            provider=tts_provider.provider_id,
            service="tts",
            model=tts_provider.model_label,
            outcome="error",
        ).inc()
        raise

    judge_metrics.PROVIDER_API_CALLS_TOTAL.labels(
        provider=tts_provider.provider_id,
        service="tts",
        model=tts_provider.model_label,
        outcome="success",
    ).inc()
    return audio


def _is_retryable_cache_warm_exc(exc: Exception) -> bool:
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError))


async def _synthesize_to_wav_with_retry(
    *,
    turn_id: str,
    text: str,
    tts_voice: str,
    settings_obj=settings,
) -> bytes:
    max_attempts = max(1, int(settings.tts_cache_turn_max_attempts))
    backoff_s = max(0.0, float(settings.tts_cache_turn_retry_backoff_s))
    attempt = 0
    while True:
        attempt += 1
        try:
            return await _synthesize_to_wav(
                text=text,
                tts_voice=tts_voice,
                settings_obj=settings_obj,
                publish_state_fn=_post_provider_circuit_state,
            )
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable_cache_warm_exc(exc):
                raise
            logger.warning(
                "TTS cache warm retrying for turn %s (attempt %s/%s)",
                turn_id,
                attempt + 1,
                max_attempts,
                exc_info=True,
            )
            await asyncio.sleep(backoff_s)


async def _sync_cache_status(
    *,
    scenario_id: str,
    tenant_id: str,
    scenario_version_hash: str,
    cache_status: str,
    cached_turns: int,
    skipped_turns: int,
    failed_turns: int,
    manifest_s3_key: str,
) -> bool:
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
    ) as http:
        resp = await http.post(
            f"/scenarios/{scenario_id}/cache/sync",
            json={
                "tenant_id": tenant_id,
                "scenario_version_hash": scenario_version_hash,
                "cache_status": cache_status,
                "cached_turns": cached_turns,
                "skipped_turns": skipped_turns,
                "failed_turns": failed_turns,
                "manifest_s3_key": manifest_s3_key,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    return bool(payload.get("applied"))


async def warm_tts_cache(ctx: dict, *, payload: dict) -> dict:
    if not settings.tts_cache_enabled:
        return {"disabled": True}

    warm_payload = WarmCachePayload.model_validate(payload)
    scenario = ScenarioDefinition.model_validate(warm_payload.scenario_payload)
    if scenario.id != warm_payload.scenario_id:
        raise ValueError("scenario_id mismatch between payload and scenario_payload")
    try:
        runtime_context = await _fetch_provider_runtime_context(
            tenant_id=warm_payload.tenant_id,
            tts_voice=scenario.config.tts_voice,
        )
    except Exception:
        logger.warning(
            "provider_runtime_context_fetch_failed tenant_id=%s scenario_id=%s",
            warm_payload.tenant_id,
            warm_payload.scenario_id,
            exc_info=True,
        )
        runtime_context = None
    runtime_settings = RuntimeSettingsOverlay(
        base_settings=settings,
        overrides=build_settings_overrides(runtime_context),
    )

    started = time.monotonic()
    _warm_outcome = "error"
    try:

        cacheable_turns = [
            turn
            for turn in scenario.turns
            if turn.kind == "harness_prompt" and bool(turn.content.text)
        ]

        cached = 0
        skipped = 0
        failed = 0
        turn_states: list[dict[str, Any]] = []

        session = aioboto3.Session(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
            for turn in cacheable_turns:
                key = scenario.turn_cache_key(turn, warm_payload.tenant_id)
                try:
                    await s3.head_object(Bucket=settings.s3_bucket_prefix, Key=key)
                    skipped += 1
                    turn_states.append({"turn_id": turn.id, "status": "skipped", "key": key})
                    continue
                except ClientError as exc:
                    if not _is_missing_object_error(exc):
                        logger.warning(
                            "head_object failed for %s (non-missing error): %s",
                            key,
                            exc,
                        )
                        # Fall through and attempt synthesis despite head errors.
                try:
                    audio_bytes = await _synthesize_to_wav_with_retry(
                        turn_id=turn.id,
                        text=turn.content.text or "",
                        tts_voice=scenario.config.tts_voice,
                        settings_obj=runtime_settings,
                    )
                    await s3.put_object(
                        Bucket=settings.s3_bucket_prefix,
                        Key=key,
                        Body=audio_bytes,
                        ContentType="audio/wav",
                    )
                    cached += 1
                    turn_states.append({"turn_id": turn.id, "status": "cached", "key": key})
                except Exception:
                    logger.exception("TTS cache warm failed for turn %s", turn.id)
                    failed += 1
                    turn_states.append(
                        {
                            "turn_id": turn.id,
                            "status": "failed",
                            "key": key,
                        }
                    )

            status = _derive_cache_status(
                total=len(cacheable_turns),
                cached=cached,
                skipped=skipped,
                failed=failed,
            )
            manifest_key = _manifest_key(
                tenant_id=warm_payload.tenant_id,
                scenario_id=warm_payload.scenario_id,
            )
            manifest = {
                "scenario_id": warm_payload.scenario_id,
                "scenario_version_hash": warm_payload.scenario_version_hash,
                "cache_status": status,
                "cached": cached,
                "skipped": skipped,
                "failed": failed,
                "total_harness_turns": len(cacheable_turns),
                "updated_at": datetime.now(UTC).isoformat(),
                "turn_states": turn_states,
            }
            await s3.put_object(
                Bucket=settings.s3_bucket_prefix,
                Key=manifest_key,
                Body=json.dumps(manifest).encode(),
                ContentType="application/json",
            )

        status_applied = False
        try:
            status_applied = await _sync_cache_status(
                scenario_id=warm_payload.scenario_id,
                tenant_id=warm_payload.tenant_id,
                scenario_version_hash=warm_payload.scenario_version_hash,
                cache_status=status,
                cached_turns=cached,
                skipped_turns=skipped,
                failed_turns=failed,
                manifest_s3_key=manifest_key,
            )
        except Exception:
            logger.exception(
                "Failed to sync cache status for scenario %s", warm_payload.scenario_id
            )

        _warm_outcome = status
        return {
            "scenario_id": warm_payload.scenario_id,
            "scenario_version_hash": warm_payload.scenario_version_hash,
            "cache_status": status,
            "cached": cached,
            "skipped": skipped,
            "failed": failed,
            "total_harness_turns": len(cacheable_turns),
            "manifest_s3_key": manifest_key,
            "status_applied": status_applied,
        }
    finally:
        judge_metrics.TTS_CACHE_WARM_LATENCY_SECONDS.labels(outcome=_warm_outcome).observe(
            time.monotonic() - started
        )


async def purge_tts_cache(ctx: dict, *, payload: dict) -> dict:
    purge_payload = PurgeCachePayload.model_validate(payload)
    deleted = 0
    errors = 0

    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
        for turn_id in purge_payload.turn_ids:
            prefix = f"{purge_payload.tenant_id}/tts-cache/{turn_id}/"
            try:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=settings.s3_bucket_prefix,
                    Prefix=prefix,
                ):
                    keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                    if not keys:
                        continue
                    await s3.delete_objects(
                        Bucket=settings.s3_bucket_prefix,
                        Delete={"Objects": keys},
                    )
                    deleted += len(keys)
            except Exception:
                errors += 1
                logger.warning(
                    "Failed to purge cache objects for turn %s (prefix=%s)",
                    turn_id,
                    prefix,
                    exc_info=True,
                )

        try:
            await s3.delete_object(
                Bucket=settings.s3_bucket_prefix,
                Key=_manifest_key(
                    tenant_id=purge_payload.tenant_id,
                    scenario_id=purge_payload.scenario_id,
                ),
            )
        except Exception:
            logger.debug("Manifest delete failed during purge", exc_info=True)

    return {
        "scenario_id": purge_payload.scenario_id,
        "tenant_id": purge_payload.tenant_id,
        "deleted": deleted,
        "errors": errors,
    }


async def gc_tts_cache(ctx: dict) -> dict:
    if not settings.tts_cache_enabled:
        return {"disabled": True, "reason": "tts_cache_disabled"}
    if not settings.tts_cache_gc_enabled:
        return {"disabled": True, "reason": "gc_disabled"}

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.tts_cache_max_age_days)
    tenant_limit_bytes = int(settings.tts_cache_tenant_max_gb * 1024 * 1024 * 1024)

    deleted = 0
    errors = 0
    deleted_by_reason: dict[str, int] = {"age": 0, "ceiling": 0}

    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
        # TODO(phase7-multitenant): this scans the full bucket and filters cache
        # keys client-side. For shared multi-tenant deployments, enumerate
        # tenant prefixes and paginate each "{tenant_id}/tts-cache/" prefix.
        paginator = s3.get_paginator("list_objects_v2")
        cache_objects: list[dict[str, Any]] = []
        async for page in paginator.paginate(Bucket=settings.s3_bucket_prefix, Prefix=""):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if not key or not _is_tts_cache_key(key):
                    continue
                cache_objects.append(
                    {
                        "Key": key,
                        "Size": int(obj.get("Size", 0) or 0),
                        "LastModified": obj.get("LastModified"),
                    }
                )

        remaining: list[dict[str, Any]] = []
        for obj in cache_objects:
            key = str(obj["Key"])
            if _is_manifest_key(key):
                continue
            last_modified = obj.get("LastModified")
            if not isinstance(last_modified, datetime):
                remaining.append(obj)
                continue
            if last_modified.astimezone(UTC) < cutoff:
                try:
                    await s3.delete_object(Bucket=settings.s3_bucket_prefix, Key=key)
                    deleted += 1
                    deleted_by_reason["age"] += 1
                except Exception:
                    errors += 1
                    logger.warning("TTS cache GC age-delete failed for key=%s", key, exc_info=True)
                continue
            remaining.append(obj)

        if tenant_limit_bytes > 0:
            by_tenant: dict[str, list[dict[str, Any]]] = {}
            for obj in remaining:
                tenant = str(obj["Key"]).split("/", 1)[0] or "default"
                by_tenant.setdefault(tenant, []).append(obj)

            for tenant, objs in by_tenant.items():
                total_bytes = sum(int(item.get("Size", 0) or 0) for item in objs)
                if total_bytes <= tenant_limit_bytes:
                    continue
                candidates = sorted(
                    objs,
                    key=lambda item: (
                        item.get("LastModified") or datetime.min.replace(tzinfo=UTC)
                    ),
                )
                for item in candidates:
                    if total_bytes <= tenant_limit_bytes:
                        break
                    key = str(item["Key"])
                    size = int(item.get("Size", 0) or 0)
                    try:
                        await s3.delete_object(Bucket=settings.s3_bucket_prefix, Key=key)
                        deleted += 1
                        deleted_by_reason["ceiling"] += 1
                        total_bytes = max(0, total_bytes - size)
                    except Exception:
                        errors += 1
                        logger.warning(
                            "TTS cache GC ceiling-delete failed for tenant=%s key=%s",
                            tenant,
                            key,
                            exc_info=True,
                        )

    return {
        "deleted": deleted,
        "errors": errors,
        "deleted_by_reason": deleted_by_reason,
        "max_age_days": settings.tts_cache_max_age_days,
        "tenant_max_gb": settings.tts_cache_tenant_max_gb,
    }


async def on_startup(ctx: dict) -> None:
    setup_tracing("botcheck-cache-worker")
    instrument_httpx()


def _redis_settings() -> ArqRedisSettings:
    p = urlparse(settings.redis_url)
    return ArqRedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int(p.path.lstrip("/") or 0),
    )


class WorkerSettings:
    functions = [warm_tts_cache, purge_tts_cache, gc_tts_cache]
    cron_jobs = [cron(gc_tts_cache, hour={2}, minute={0})]
    on_startup = on_startup
    redis_settings = _redis_settings()
    queue_name = "arq:cache"
    max_jobs = settings.tts_cache_max_jobs
    job_timeout = 600
