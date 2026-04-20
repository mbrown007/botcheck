import asyncio
import hmac
import inspect
import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_scenarios import SpeechCapabilities

from ..admin.platform_settings import effective_platform_feature_flags
from ..admin.service_tenants import merge_tenant_feature_overrides
from ..auth import (
    UserContext,
    get_optional_current_user_any_tenant,
    get_service_caller,
    get_tenant_row,
)
from ..config import settings
from ..database import get_db
from ..metrics import RUN_QUEUE_DEPTH, metrics_response
from ..models import PlatformSettingsRow
from ..runs.provider_state import (
    harness_degraded,
    harness_worker_snapshot,
    observe_provider_circuit_state_gauge,
    provider_degraded,
    read_provider_circuit_snapshots,
    store_provider_circuit_snapshot,
)
from ..stt_provider import build_api_speech_capabilities

logger = logging.getLogger("botcheck.api.health")
router = APIRouter()
_RUN_QUEUE_NAMES = ("arq:judge", "arq:cache", "arq:scheduler", "arq:eval")


def _require_metrics_scrape_token(request: Request) -> None:
    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    expected = settings.metrics_scrape_token.strip()
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing metrics scrape token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _observe_run_queue_depths(redis_pool: object | None) -> None:
    if redis_pool is None:
        for queue_name in _RUN_QUEUE_NAMES:
            RUN_QUEUE_DEPTH.labels(queue=queue_name).set(0)
        return

    zcard_fn = getattr(redis_pool, "zcard", None)
    llen_fn = getattr(redis_pool, "llen", None)
    count_fn = zcard_fn if callable(zcard_fn) else llen_fn if callable(llen_fn) else None
    if count_fn is None:
        for queue_name in _RUN_QUEUE_NAMES:
            RUN_QUEUE_DEPTH.labels(queue=queue_name).set(0)
        return

    try:
        results = [count_fn(q) for q in _RUN_QUEUE_NAMES]
        if any(inspect.isawaitable(r) for r in results):
            results = await asyncio.gather(*results)
        for queue_name, result in zip(_RUN_QUEUE_NAMES, results, strict=True):
            RUN_QUEUE_DEPTH.labels(queue=queue_name).set(int(result or 0))
    except Exception:
        logger.warning("Failed to read ARQ queue depths for /metrics", exc_info=True)
        for queue_name in _RUN_QUEUE_NAMES:
            RUN_QUEUE_DEPTH.labels(queue=queue_name).set(0)


class HealthResponse(BaseModel):
    status: str
    service: str


class ProviderCircuitStateResponse(BaseModel):
    source: Literal["api", "agent", "judge"]
    provider: str
    service: str
    component: str
    state: Literal["open", "half_open", "closed", "unknown"]
    updated_at: datetime | None = None


class FeaturesResponse(BaseModel):
    tts_cache_enabled: bool
    packs_enabled: bool = False
    destinations_enabled: bool = False
    ai_scenarios_enabled: bool = False
    speech_capabilities: SpeechCapabilities = Field(default_factory=SpeechCapabilities)
    provider_degraded: bool = False
    harness_degraded: bool = False
    harness_state: Literal["open", "half_open", "closed", "unknown"] = "unknown"
    provider_circuits: list[ProviderCircuitStateResponse] = Field(default_factory=list)


class ProviderCircuitStateUpsertRequest(BaseModel):
    source: Literal["api", "agent", "judge"]
    provider: str
    service: str
    component: str
    state: Literal["open", "half_open", "closed"]
    observed_at: datetime | None = None


class ProviderCircuitStateUpsertResponse(BaseModel):
    stored: bool


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    return HealthResponse(status="ok", service="botcheck-api")


@router.get("/features", response_model=FeaturesResponse, tags=["health"])
async def features(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[UserContext | None, Depends(get_optional_current_user_any_tenant)],
):
    redis_pool = getattr(request.app.state, "arq_pool", None)
    snapshots = await read_provider_circuit_snapshots(
        redis_pool,
        stale_after_s=settings.provider_circuit_snapshot_stale_s,
    )
    observe_provider_circuit_state_gauge(snapshots)
    harness_snapshot = harness_worker_snapshot(snapshots)
    platform_settings = await db.get(PlatformSettingsRow, "default")
    effective_flags = effective_platform_feature_flags(platform_settings)
    if user is not None:
        tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
        effective_flags = merge_tenant_feature_overrides(
            effective_flags,
            dict(tenant.feature_overrides or {}) if tenant is not None else None,
        )
    return FeaturesResponse(
        tts_cache_enabled=effective_flags["tts_cache_enabled"],
        packs_enabled=effective_flags["feature_packs_enabled"],
        destinations_enabled=effective_flags["feature_destinations_enabled"],
        ai_scenarios_enabled=effective_flags["feature_ai_scenarios_enabled"],
        speech_capabilities=build_api_speech_capabilities(
            feature_tts_provider_openai_enabled=effective_flags["feature_tts_provider_openai_enabled"],
            feature_tts_provider_elevenlabs_enabled=effective_flags["feature_tts_provider_elevenlabs_enabled"],
            feature_stt_provider_deepgram_enabled=effective_flags["feature_stt_provider_deepgram_enabled"],
            feature_stt_provider_azure_enabled=effective_flags["feature_stt_provider_azure_enabled"],
        ),
        provider_degraded=provider_degraded(snapshots),
        harness_degraded=harness_degraded(snapshots),
        harness_state=harness_snapshot.state,
        provider_circuits=[
            ProviderCircuitStateResponse(
                source=snapshot.source,
                provider=snapshot.provider,
                service=snapshot.service,
                component=snapshot.component,
                state=snapshot.state,
                updated_at=snapshot.updated_at,
            )
            for snapshot in snapshots
        ],
    )


@router.post(
    "/internal/provider-circuits/state",
    response_model=ProviderCircuitStateUpsertResponse,
    tags=["health"],
)
async def upsert_provider_circuit_state(
    body: ProviderCircuitStateUpsertRequest,
    request: Request,
    caller: Annotated[str, Depends(get_service_caller)],
):
    if caller == "harness":
        expected_source = "agent"
    elif caller == "judge":
        expected_source = "judge"
    else:
        raise HTTPException(status_code=403, detail="Service caller not allowed")

    if body.source != expected_source:
        raise HTTPException(status_code=403, detail="Source does not match caller identity")

    redis_pool = getattr(request.app.state, "arq_pool", None)
    stored = await store_provider_circuit_snapshot(
        redis_pool,
        source=body.source,
        provider=body.provider,
        service=body.service,
        component=body.component,
        state=body.state,
        observed_at=body.observed_at,
        ttl_s=settings.provider_circuit_snapshot_ttl_s,
    )
    return ProviderCircuitStateUpsertResponse(stored=stored)


@router.get("/metrics", tags=["observability"], include_in_schema=False)
async def metrics(request: Request):
    _require_metrics_scrape_token(request)
    redis_pool = getattr(request.app.state, "arq_pool", None)
    snapshots = await read_provider_circuit_snapshots(
        redis_pool,
        stale_after_s=settings.provider_circuit_snapshot_stale_s,
    )
    observe_provider_circuit_state_gauge(snapshots)
    await _observe_run_queue_depths(redis_pool)
    return metrics_response()
