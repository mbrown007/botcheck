from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import UserContext, require_platform_admin
from ..database import get_db
from ..packs.service_sip_trunks import get_sip_trunk, list_sip_trunks, sync_sip_trunks
from .schemas import (
    AdminSIPTrunkPoolAssignmentCreateRequest,
    AdminSIPTrunkPoolAssignmentPatchRequest,
    AdminSIPTrunkPoolDetailResponse,
    AdminSIPTrunkPoolMemberCreateRequest,
    AdminSIPTrunkPoolMemberResponse,
    AdminSIPTrunkPoolsListResponse,
    AdminSIPTrunkPoolCreateRequest,
    AdminSIPTrunkPoolPatchRequest,
    AdminSIPSyncResponse,
    AdminSIPTrunkDetailResponse,
    AdminSIPTrunksListResponse,
)
from .service_sip_pools import (
    add_admin_sip_pool_member,
    assign_admin_sip_pool_to_tenant,
    create_admin_sip_pool,
    get_admin_sip_pool_record,
    list_admin_sip_pools,
    remove_admin_sip_pool_member,
    revoke_admin_sip_pool_assignment,
    update_admin_sip_pool_assignment,
    update_admin_sip_pool,
)

router = APIRouter(prefix="/sip")


def _trunk_response(row) -> AdminSIPTrunkDetailResponse:
    return AdminSIPTrunkDetailResponse(
        trunk_id=row.trunk_id,
        name=row.name,
        provider_name=row.provider_name,
        address=row.address,
        transport=row.transport,
        numbers=list(row.numbers),
        metadata_json=dict(row.metadata_json or {}),
        is_active=row.is_active,
        last_synced_at=row.last_synced_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pool_response(record) -> AdminSIPTrunkPoolDetailResponse:
    return AdminSIPTrunkPoolDetailResponse(
        trunk_pool_id=record.pool.trunk_pool_id,
        name=record.pool.name,
        provider_name=record.pool.provider_name,
        selection_policy=record.pool.selection_policy,
        is_active=record.pool.is_active,
        members=[
            AdminSIPTrunkPoolMemberResponse(
                trunk_id=member.member.trunk_id,
                name=member.trunk.name if member.trunk is not None else None,
                provider_name=member.trunk.provider_name if member.trunk is not None else None,
                is_active=member.member.is_active,
                priority=member.member.priority,
            )
            for member in record.members
        ],
        assignments=[
            {
                "tenant_id": assignment.tenant_id,
                "tenant_label": assignment.tenant_label,
                "is_default": assignment.is_default,
                "is_active": assignment.is_active,
                "max_channels": assignment.max_channels,
                "reserved_channels": assignment.reserved_channels,
            }
            for assignment in record.assignments
        ],
        created_at=record.pool.created_at,
        updated_at=record.pool.updated_at,
    )


@router.get("/trunks", response_model=AdminSIPTrunksListResponse)
async def list_admin_sip_trunks(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunksListResponse:
    del user
    rows = await list_sip_trunks(db)
    return AdminSIPTrunksListResponse(items=[_trunk_response(row) for row in rows], total=len(rows))


@router.post("/trunks/sync", response_model=AdminSIPSyncResponse)
async def sync_admin_sip_trunks(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPSyncResponse:
    rows = await sync_sip_trunks(db)
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="admin.sip.sync",
        resource_type="sip_trunk_registry",
        resource_id="all",
        detail={"synced_count": len(rows)},
    )
    await db.commit()
    return AdminSIPSyncResponse(
        synced=True,
        total=len(rows),
        active=sum(1 for row in rows if row.is_active),
    )


@router.get("/trunks/{trunk_id}", response_model=AdminSIPTrunkDetailResponse)
async def get_admin_sip_trunk(
    trunk_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkDetailResponse:
    del user
    row = await get_sip_trunk(db, trunk_id=trunk_id)
    if row is None:
        raise HTTPException(status_code=404, detail="SIP trunk not found")
    return _trunk_response(row)


@router.get("/pools", response_model=AdminSIPTrunkPoolsListResponse)
async def list_admin_sip_pools_route(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolsListResponse:
    del user
    records = await list_admin_sip_pools(db)
    return AdminSIPTrunkPoolsListResponse(items=[_pool_response(record) for record in records], total=len(records))


@router.post("/pools", response_model=AdminSIPTrunkPoolDetailResponse, status_code=201)
async def create_admin_sip_pool_route(
    body: AdminSIPTrunkPoolCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await create_admin_sip_pool(
            db,
            name=body.name,
            provider_name=body.provider_name,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.patch("/pools/{trunk_pool_id}", response_model=AdminSIPTrunkPoolDetailResponse)
async def patch_admin_sip_pool_route(
    trunk_pool_id: str,
    body: AdminSIPTrunkPoolPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await update_admin_sip_pool(
            db,
            trunk_pool_id=trunk_pool_id,
            name=body.name if "name" in body.model_fields_set else None,
            is_active=body.is_active if "is_active" in body.model_fields_set else None,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.post("/pools/{trunk_pool_id}/members", response_model=AdminSIPTrunkPoolDetailResponse)
async def add_admin_sip_pool_member_route(
    trunk_pool_id: str,
    body: AdminSIPTrunkPoolMemberCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await add_admin_sip_pool_member(
            db,
            trunk_pool_id=trunk_pool_id,
            trunk_id=body.trunk_id,
            priority=body.priority,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.delete("/pools/{trunk_pool_id}/members/{trunk_id}", response_model=AdminSIPTrunkPoolDetailResponse)
async def remove_admin_sip_pool_member_route(
    trunk_pool_id: str,
    trunk_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await remove_admin_sip_pool_member(
            db,
            trunk_pool_id=trunk_pool_id,
            trunk_id=trunk_id,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.post("/pools/{trunk_pool_id}/assign", response_model=AdminSIPTrunkPoolDetailResponse)
async def assign_admin_sip_pool_route(
    trunk_pool_id: str,
    body: AdminSIPTrunkPoolAssignmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await assign_admin_sip_pool_to_tenant(
            db,
            trunk_pool_id=trunk_pool_id,
            tenant_id=body.tenant_id,
            tenant_label=body.tenant_label,
            is_default=body.is_default,
            max_channels=body.max_channels,
            reserved_channels=body.reserved_channels,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.patch("/pools/{trunk_pool_id}/assign/{tenant_id}", response_model=AdminSIPTrunkPoolDetailResponse)
async def patch_admin_sip_pool_assignment_route(
    trunk_pool_id: str,
    tenant_id: str,
    body: AdminSIPTrunkPoolAssignmentPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await update_admin_sip_pool_assignment(
            db,
            trunk_pool_id=trunk_pool_id,
            tenant_id=tenant_id,
            tenant_label=body.tenant_label,
            is_default=body.is_default,
            is_active=body.is_active,
            max_channels=body.max_channels,
            reserved_channels=body.reserved_channels,
            set_tenant_label="tenant_label" in body.model_fields_set,
            set_is_default="is_default" in body.model_fields_set,
            set_is_active="is_active" in body.model_fields_set,
            set_max_channels="max_channels" in body.model_fields_set,
            set_reserved_channels="reserved_channels" in body.model_fields_set,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)


@router.delete("/pools/{trunk_pool_id}/assign/{tenant_id}", response_model=AdminSIPTrunkPoolDetailResponse)
async def revoke_admin_sip_pool_route(
    trunk_pool_id: str,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminSIPTrunkPoolDetailResponse:
    try:
        record = await revoke_admin_sip_pool_assignment(
            db,
            trunk_pool_id=trunk_pool_id,
            tenant_id=tenant_id,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return _pool_response(record)
