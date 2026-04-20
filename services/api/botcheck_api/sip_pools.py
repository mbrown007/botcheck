from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import UserContext, require_editor, require_operator
from .database import get_db
from .models import TenantTrunkPoolRow, TrunkPoolMemberRow, TrunkPoolRow

router = APIRouter()


class TenantSIPPoolResponse(BaseModel):
    trunk_pool_id: str
    pool_name: str
    provider_name: str
    tenant_label: str
    is_default: bool
    is_active: bool
    max_channels: int | None = None
    reserved_channels: int | None = None
    member_count: int


class TenantSIPPoolsListResponse(BaseModel):
    items: list[TenantSIPPoolResponse]
    total: int


class TenantSIPPoolPatchRequest(BaseModel):
    tenant_label: str | None = Field(default=None, min_length=1, max_length=255)
    is_default: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "TenantSIPPoolPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "is_default" in self.model_fields_set and self.is_default is None:
            raise ValueError("is_default must be true or false, not null")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active must be true or false, not null")
        return self


async def _list_tenant_pool_rows(db: AsyncSession, *, tenant_id: str) -> list[TenantSIPPoolResponse]:
    rows = (
        await db.execute(
            select(TenantTrunkPoolRow, TrunkPoolRow, func.count(TrunkPoolMemberRow.trunk_pool_member_id))
            .join(TrunkPoolRow, TrunkPoolRow.trunk_pool_id == TenantTrunkPoolRow.trunk_pool_id)
            .outerjoin(
                TrunkPoolMemberRow,
                TrunkPoolMemberRow.trunk_pool_id == TenantTrunkPoolRow.trunk_pool_id,
            )
            .where(TenantTrunkPoolRow.tenant_id == tenant_id)
            .group_by(TenantTrunkPoolRow.tenant_trunk_pool_id, TrunkPoolRow.trunk_pool_id)
            .order_by(TenantTrunkPoolRow.is_default.desc(), TenantTrunkPoolRow.tenant_label.asc())
        )
    ).all()
    return [
        TenantSIPPoolResponse(
            trunk_pool_id=pool.trunk_pool_id,
            pool_name=pool.name,
            provider_name=pool.provider_name,
            tenant_label=tenant_pool.tenant_label or "",
            is_default=tenant_pool.is_default,
            is_active=tenant_pool.is_active,
            max_channels=tenant_pool.max_channels,
            reserved_channels=tenant_pool.reserved_channels,
            member_count=int(member_count or 0),
        )
        for tenant_pool, pool, member_count in rows
    ]


@router.get("/pools", response_model=TenantSIPPoolsListResponse)
async def list_tenant_sip_pools(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_operator),
) -> TenantSIPPoolsListResponse:
    items = await _list_tenant_pool_rows(db, tenant_id=user.tenant_id)
    return TenantSIPPoolsListResponse(items=items, total=len(items))


@router.patch("/pools/{trunk_pool_id}", response_model=TenantSIPPoolResponse)
async def patch_tenant_sip_pool(
    trunk_pool_id: str,
    body: TenantSIPPoolPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
) -> TenantSIPPoolResponse:
    result = await db.execute(
        select(TenantTrunkPoolRow).where(
            TenantTrunkPoolRow.tenant_id == user.tenant_id,
            TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant SIP pool not found")
    if "tenant_label" in body.model_fields_set and body.tenant_label is not None:
        row.tenant_label = body.tenant_label.strip()
    if "is_active" in body.model_fields_set and body.is_active is not None:
        row.is_active = body.is_active
    if "is_default" in body.model_fields_set and body.is_default is not None:
        if body.is_default:
            others = await db.execute(
                select(TenantTrunkPoolRow).where(
                    TenantTrunkPoolRow.tenant_id == user.tenant_id,
                    TenantTrunkPoolRow.trunk_pool_id != trunk_pool_id,
                )
            )
            for other in others.scalars().all():
                other.is_default = False
        row.is_default = body.is_default
    await db.commit()
    rows = await _list_tenant_pool_rows(db, tenant_id=user.tenant_id)
    for item in rows:
        if item.trunk_pool_id == trunk_pool_id:
            return item
    raise HTTPException(status_code=404, detail="Tenant SIP pool not found")
