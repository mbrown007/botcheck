from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_viewer
from ..database import get_db
from ..models import AuditLogRow

router = APIRouter()


class AuditEventResponse(BaseModel):
    event_id: str
    tenant_id: str
    actor_id: str
    actor_type: str
    action: str
    resource_type: str
    resource_id: str
    detail: dict
    created_at: datetime


@router.get("/", response_model=list[AuditEventResponse])
async def list_audit_events(
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    query = (
        select(AuditLogRow)
        .where(AuditLogRow.tenant_id == user.tenant_id)
        .order_by(AuditLogRow.created_at.desc())
        .limit(limit)
    )
    if action:
        query = query.where(AuditLogRow.action == action)
    if resource_type:
        query = query.where(AuditLogRow.resource_type == resource_type)
    if actor_id:
        query = query.where(AuditLogRow.actor_id == actor_id)
    if from_ts:
        query = query.where(AuditLogRow.created_at >= from_ts)
    if to_ts:
        query = query.where(AuditLogRow.created_at <= to_ts)

    rows = (await db.execute(query)).scalars().all()
    return [
        AuditEventResponse(
            event_id=row.event_id,
            tenant_id=row.tenant_id,
            actor_id=row.actor_id,
            actor_type=row.actor_type,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            detail=row.detail or {},
            created_at=row.created_at,
        )
        for row in rows
    ]
