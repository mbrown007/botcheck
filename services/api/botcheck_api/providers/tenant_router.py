from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_operator
from ..database import get_db
from .schemas import (
    TenantProviderQuotaListResponse,
    TenantProviderQuotaSummaryResponse,
    TenantProviderUsageListResponse,
    TenantProviderUsageSummaryResponse,
)
from .usage_service import (
    list_tenant_provider_quota_summary,
    list_tenant_provider_usage_summary,
)

router = APIRouter(prefix="/me/providers")


@router.get("/usage", response_model=TenantProviderUsageListResponse)
async def get_tenant_provider_usage(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
) -> TenantProviderUsageListResponse:
    window_start, window_end, items = await list_tenant_provider_usage_summary(
        db,
        tenant_id=user.tenant_id,
    )
    return TenantProviderUsageListResponse(
        window_start=window_start,
        window_end=window_end,
        items=[TenantProviderUsageSummaryResponse(**item) for item in items],
    )


@router.get("/quota", response_model=TenantProviderQuotaListResponse)
async def get_tenant_provider_quota(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
) -> TenantProviderQuotaListResponse:
    window_start, window_end, items = await list_tenant_provider_quota_summary(
        db,
        tenant_id=user.tenant_id,
    )
    return TenantProviderQuotaListResponse(
        window_start=window_start,
        window_end=window_end,
        items=[TenantProviderQuotaSummaryResponse(**item) for item in items],
    )
