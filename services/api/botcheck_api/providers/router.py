from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, get_service_caller, require_viewer
from ..database import get_db
from .schemas import (
    ProviderAvailableListResponse,
    ProviderAvailabilitySummaryResponse,
    ProviderRuntimeBindingResponse,
    ProviderRuntimeContextRequest,
    ProviderRuntimeContextResponse,
    ProviderUsageWriteRequest,
    ProviderUsageWriteResponse,
)
from .service import build_provider_runtime_context, list_available_providers_for_tenant
from .usage_service import observe_provider_usage_write_failure, record_provider_usage

router = APIRouter()
logger = logging.getLogger("botcheck.api.providers")


@router.get("/available", response_model=ProviderAvailableListResponse)
async def list_available_providers(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
) -> ProviderAvailableListResponse:
    items = await list_available_providers_for_tenant(db, tenant_id=user.tenant_id)
    return ProviderAvailableListResponse(
        items=[ProviderAvailabilitySummaryResponse(**item) for item in items]
    )


@router.post("/internal/runtime-context", response_model=ProviderRuntimeContextResponse)
async def get_provider_runtime_context(
    body: ProviderRuntimeContextRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
) -> ProviderRuntimeContextResponse:
    if caller not in {"harness", "judge"}:
        raise HTTPException(status_code=403, detail="Only harness or judge may fetch provider runtime context")
    payload = await build_provider_runtime_context(
        db,
        tenant_id=body.tenant_id,
        runtime_scope=body.runtime_scope,
        tts_voice=body.tts_voice,
        stt_provider=body.stt_provider,
        stt_model=body.stt_model,
        provider_bindings=[binding.model_dump(mode="python") for binding in body.provider_bindings],
    )
    logger.info(
        "provider_runtime_context_fetched",
        extra={
            "caller": caller,
            "tenant_id": body.tenant_id,
            "runtime_scope": body.runtime_scope,
            "tts_requested": bool(body.tts_voice),
            "stt_requested": bool(body.stt_provider or body.stt_model),
            "provider_binding_count": len(body.provider_bindings),
        },
    )
    return ProviderRuntimeContextResponse(
        tenant_id=str(payload["tenant_id"]),
        runtime_scope=body.runtime_scope,
        feature_flags=dict(payload["feature_flags"]),
        tts=(
            ProviderRuntimeBindingResponse(**payload["tts"])
            if isinstance(payload.get("tts"), dict)
            else None
        ),
        stt=(
            ProviderRuntimeBindingResponse(**payload["stt"])
            if isinstance(payload.get("stt"), dict)
            else None
        ),
        providers=[
            ProviderRuntimeBindingResponse(**item)
            for item in list(payload.get("providers") or [])
            if isinstance(item, dict)
        ],
    )


@router.post("/internal/usage", response_model=ProviderUsageWriteResponse)
async def record_internal_provider_usage(
    body: ProviderUsageWriteRequest,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
) -> ProviderUsageWriteResponse:
    expected_runtime_scope = {
        "harness": "agent",
        "judge": "judge",
    }.get(caller)
    if expected_runtime_scope is None:
        raise HTTPException(status_code=403, detail="Service caller not allowed")
    if body.runtime_scope != expected_runtime_scope:
        raise HTTPException(status_code=403, detail="Runtime scope does not match caller identity")
    try:
        ledger_id = await record_provider_usage(
            db,
            tenant_id=body.tenant_id,
            provider_id=body.provider_id,
            usage_key=body.usage_key,
            runtime_scope=body.runtime_scope,
            capability=body.capability,
            run_id=body.run_id,
            eval_run_id=body.eval_run_id,
            input_tokens=body.input_tokens,
            output_tokens=body.output_tokens,
            audio_seconds=body.audio_seconds,
            characters=body.characters,
            sip_minutes=body.sip_minutes,
            request_count=body.request_count,
            source=caller,
        )
    except Exception:
        observe_provider_usage_write_failure(
            runtime_scope=body.runtime_scope,
            capability=body.capability,
            source=caller,
        )
        logger.warning(
            "provider.usage.write_failed",
            extra={
                "caller": caller,
                "tenant_id": body.tenant_id,
                "provider_id": body.provider_id,
                "usage_key": body.usage_key,
                "runtime_scope": body.runtime_scope,
                "capability": body.capability,
            },
            exc_info=True,
        )
        return ProviderUsageWriteResponse(stored=False, ledger_id=None)
    return ProviderUsageWriteResponse(stored=True, ledger_id=ledger_id)
