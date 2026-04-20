from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Role, UserContext, get_current_user_any_tenant
from ..database import get_db
from .schemas import AdminAuditEventDetailResponse, AdminAuditEventsListResponse
from .service_audit import get_audit_event_admin, list_audit_events_admin

router = APIRouter(prefix="/audit")


async def _require_admin_audit_reader(
    user: UserContext = Depends(get_current_user_any_tenant),
) -> UserContext:
    if user.role not in {Role.ADMIN.value, Role.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return user


def _event_response(row) -> AdminAuditEventDetailResponse:
    return AdminAuditEventDetailResponse(
        event_id=row.event_id,
        tenant_id=row.tenant_id,
        actor_id=row.actor_id,
        actor_type=row.actor_type,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        detail=dict(row.detail or {}),
        created_at=row.created_at,
    )


@router.get("/", response_model=AdminAuditEventsListResponse)
async def list_admin_audit_events(
    tenant_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(_require_admin_audit_reader),
) -> AdminAuditEventsListResponse:
    page = await list_audit_events_admin(
        db,
        user=user,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return AdminAuditEventsListResponse(
        items=[_event_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{event_id}", response_model=AdminAuditEventDetailResponse)
async def get_admin_audit_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(_require_admin_audit_reader),
) -> AdminAuditEventDetailResponse:
    row = await get_audit_event_admin(db, user=user, event_id=event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return _event_response(row)
