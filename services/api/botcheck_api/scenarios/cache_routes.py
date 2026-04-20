from __future__ import annotations

from datetime import UTC, datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..audit import write_audit_event
from ..auth import UserContext, get_service_caller, require_editor, require_viewer
from ..auth.security import check_login_rate_limit
from ..config import settings
from ..database import get_db
from ..exceptions import ApiProblem, JOB_QUEUE_UNAVAILABLE, PREVIEW_RATE_LIMITED
from ..retention import download_artifact_bytes, upload_artifact_bytes
from .schemas import (
    ScenarioCacheRebuildResponse,
    ScenarioCacheStateResponse,
    ScenarioCacheSyncRequest,
    ScenarioCacheSyncResponse,
    ScenarioCacheTurnState,
)
from .store_service import (
    get_scenario,
    queue_scenario_cache_rebuild,
    reconcile_scenario_cache_status,
    sync_scenario_cache_status,
)
from .service import (
    inspect_scenario_tts_cache,
    is_s3_not_found_error,
    preview_rate_limit_key,
    require_preview_role,
    require_tts_cache_enabled,
    synthesize_preview_wav,
)

router = APIRouter()
logger = logging.getLogger("botcheck.api.scenarios.cache")


@router.post(
    "/{scenario_id}/cache/rebuild",
    response_model=ScenarioCacheRebuildResponse,
    status_code=202,
)
async def rebuild_scenario_cache(
    scenario_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    require_tts_cache_enabled()

    queued = await queue_scenario_cache_rebuild(db, scenario_id, user.tenant_id)
    if queued is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    arq_pool = getattr(request.app.state, "arq_cache_pool", None)
    if arq_pool is None:
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Cache queue unavailable",
        )

    try:
        await arq_pool.enqueue_job(
            "warm_tts_cache",
            payload={
                "scenario_id": queued.scenario_id,
                "tenant_id": queued.tenant_id,
                "scenario_version_hash": queued.version_hash,
                "scenario_payload": queued.scenario_payload,
            },
            _queue_name="arq:cache",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Failed to enqueue cache rebuild") from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="scenario.cache_rebuild",
        resource_type="scenario",
        resource_id=scenario_id,
        detail={"version_hash": queued.version_hash},
    )
    await db.commit()
    return ScenarioCacheRebuildResponse(
        scenario_id=scenario_id,
        cache_status="warming",
        queue="arq:cache",
        enqueued=True,
    )


@router.get(
    "/{scenario_id}/cache/state",
    response_model=ScenarioCacheStateResponse,
)
async def get_scenario_cache_state(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    require_tts_cache_enabled()

    scenario_data = await get_scenario(db, scenario_id, user.tenant_id)
    if scenario_data is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario, version_hash = scenario_data
    inspection = await inspect_scenario_tts_cache(
        settings,
        scenario=scenario,
        tenant_id=user.tenant_id,
    )
    cache_status = inspection.cache_status
    await reconcile_scenario_cache_status(
        db,
        scenario_id=scenario_id,
        tenant_id=user.tenant_id,
        cache_status=cache_status,
    )
    turn_states = [
        ScenarioCacheTurnState(
            turn_id=str(row["turn_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            key=(str(row["key"]) if row["key"] else None),
        )
        for row in inspection.turn_states
    ]

    return ScenarioCacheStateResponse(
        scenario_id=scenario_id,
        scenario_version_hash=version_hash,
        cache_status=cache_status,  # type: ignore[arg-type]
        cached_turns=inspection.cached_turns,
        skipped_turns=0,
        failed_turns=inspection.failed_turns,
        total_harness_turns=inspection.total_harness_turns,
        updated_at=datetime.now(UTC).isoformat(),
        bucket_name=settings.s3_bucket_prefix,
        turn_states=turn_states,
    )


@router.get("/{scenario_id}/turns/{turn_id}/audio")
async def preview_turn_audio(
    scenario_id: str,
    turn_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    require_tts_cache_enabled()
    require_preview_role(user)

    allowed, retry_after = check_login_rate_limit(
        key=preview_rate_limit_key(user, request),
        max_attempts=settings.tts_preview_rate_limit_attempts,
        window_s=settings.tts_preview_rate_limit_window_s,
    )
    if not allowed:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="rate_limited").inc()
        raise ApiProblem(
            status=429,
            error_code=PREVIEW_RATE_LIMITED,
            detail="Audio preview rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    scenario_data = await get_scenario(db, scenario_id, user.tenant_id)
    if scenario_data is None:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario, _ = scenario_data

    turn = next((item for item in scenario.turns if item.id == turn_id), None)
    if turn is None:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise HTTPException(status_code=404, detail="Turn not found")
    if turn.kind != "harness_prompt" or not turn.content.text:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise HTTPException(
            status_code=422,
            detail="Audio preview requires a harness turn with text",
        )

    cache_key = scenario.turn_cache_key(
        turn,
        user.tenant_id,
        pcm_format_version=settings.tts_cache_pcm_format_version,
    )

    try:
        cached_bytes, content_type = await download_artifact_bytes(settings, key=cache_key)
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="hit").inc()
        return Response(content=cached_bytes, media_type=content_type or "audio/wav")
    except Exception as exc:
        if not is_s3_not_found_error(exc):
            api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
            raise HTTPException(status_code=503, detail="Preview cache unavailable") from exc

    try:
        audio_bytes = await synthesize_preview_wav(
            db,
            tenant_id=user.tenant_id,
            text=turn.content.text,
            tts_voice=scenario.config.tts_voice,
            provider_state_pool=getattr(request.app.state, "arq_pool", None),
        )
    except (ApiProblem, HTTPException):
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise
    except Exception as exc:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise HTTPException(status_code=503, detail="TTS preview synthesis failed") from exc

    try:
        await upload_artifact_bytes(
            settings,
            key=cache_key,
            body=audio_bytes,
            content_type="audio/wav",
        )
    except Exception:
        logger.warning(
            "Failed to persist JIT preview audio for scenario=%s turn=%s",
            scenario_id,
            turn_id,
            exc_info=True,
        )

    api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="miss").inc()
    return Response(content=audio_bytes, media_type="audio/wav")


@router.post(
    "/{scenario_id}/cache/sync",
    response_model=ScenarioCacheSyncResponse,
)
async def sync_scenario_cache(
    scenario_id: str,
    body: ScenarioCacheSyncRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    require_tts_cache_enabled()

    if caller != "judge":
        raise HTTPException(status_code=403, detail="Only judge may sync scenario cache status")

    result = await sync_scenario_cache_status(
        db,
        scenario_id=scenario_id,
        tenant_id=body.tenant_id,
        scenario_version_hash=body.scenario_version_hash,
        cache_status=body.cache_status,
    )
    if result.found and result.applied:
        await write_audit_event(
            db,
            tenant_id=body.tenant_id,
            actor_id="judge",
            actor_type="service",
            action="scenario.cache_sync",
            resource_type="scenario",
            resource_id=scenario_id,
            detail={
                "cache_status": body.cache_status,
                "scenario_version_hash": body.scenario_version_hash,
                "cached_turns": body.cached_turns,
                "skipped_turns": body.skipped_turns,
                "failed_turns": body.failed_turns,
                "manifest_s3_key": body.manifest_s3_key,
            },
        )
    await db.commit()
    return ScenarioCacheSyncResponse(
        scenario_id=scenario_id,
        applied=result.applied,
        cache_status=result.cache_status,
        reason=result.reason,
    )
