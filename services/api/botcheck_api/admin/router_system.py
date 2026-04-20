from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_platform_admin
from ..database import get_db
from .schemas import (
    AdminSystemConfigResponse,
    AdminSystemFeatureFlagsPatchRequest,
    AdminSystemFeatureFlagsResponse,
    AdminSystemHealthResponse,
    AdminSystemQuotaPatchRequest,
    AdminSystemQuotaResponse,
)
from .service_system import (
    build_system_health,
    get_platform_feature_flags,
    get_platform_quota_defaults,
    patch_platform_feature_flags,
    patch_platform_quota_defaults,
    redacted_effective_config,
)

router = APIRouter(prefix="/system")


@router.get("/health", response_model=AdminSystemHealthResponse)
async def get_admin_system_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSystemHealthResponse:
    del user
    return AdminSystemHealthResponse(
        **await build_system_health(db, redis_pool=getattr(request.app.state, "arq_pool", None))
    )


@router.get("/config", response_model=AdminSystemConfigResponse)
async def get_admin_system_config(
    user: UserContext = Depends(require_platform_admin),
) -> AdminSystemConfigResponse:
    del user
    return AdminSystemConfigResponse(config=redacted_effective_config())


@router.patch("/feature-flags", response_model=AdminSystemFeatureFlagsResponse)
async def patch_admin_system_feature_flags(
    body: AdminSystemFeatureFlagsPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSystemFeatureFlagsResponse:
    flags, updated_at = await patch_platform_feature_flags(
        db,
        overrides=body.feature_flags,
        actor_id=user.sub,
        actor_tenant_id=user.tenant_id,
    )
    await db.commit()
    return AdminSystemFeatureFlagsResponse(feature_flags=flags, updated_at=updated_at)


@router.get("/quotas", response_model=AdminSystemQuotaResponse)
async def get_admin_system_quotas(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSystemQuotaResponse:
    del user
    quotas, updated_at = await get_platform_quota_defaults(db)
    return AdminSystemQuotaResponse(quota_defaults=quotas, updated_at=updated_at)


@router.patch("/quotas", response_model=AdminSystemQuotaResponse)
async def patch_admin_system_quotas(
    body: AdminSystemQuotaPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSystemQuotaResponse:
    quotas, updated_at = await patch_platform_quota_defaults(
        db,
        overrides=body.quota_defaults,
        actor_id=user.sub,
        actor_tenant_id=user.tenant_id,
    )
    await db.commit()
    return AdminSystemQuotaResponse(quota_defaults=quotas, updated_at=updated_at)
