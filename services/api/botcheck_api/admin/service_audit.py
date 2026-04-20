from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Role, UserContext
from ..models import AuditLogRow


@dataclass(frozen=True)
class AuditEventPage:
    items: list[AuditLogRow]
    total: int
    limit: int
    offset: int


def _scoped_tenant_id(user: UserContext, requested_tenant_id: str | None) -> str | None:
    if user.role == Role.SYSTEM_ADMIN.value:
        return requested_tenant_id.strip() if requested_tenant_id else None
    if requested_tenant_id is not None and requested_tenant_id.strip() != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    return user.tenant_id


async def list_audit_events_admin(
    db: AsyncSession,
    *,
    user: UserContext,
    tenant_id: str | None,
    actor_id: str | None,
    action: str | None,
    resource_type: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    limit: int,
    offset: int,
) -> AuditEventPage:
    scoped_tenant_id = _scoped_tenant_id(user, tenant_id)

    stmt = select(AuditLogRow)
    count_stmt = select(func.count(AuditLogRow.event_id))

    if scoped_tenant_id is not None:
        stmt = stmt.where(AuditLogRow.tenant_id == scoped_tenant_id)
        count_stmt = count_stmt.where(AuditLogRow.tenant_id == scoped_tenant_id)
    if actor_id:
        stmt = stmt.where(AuditLogRow.actor_id == actor_id)
        count_stmt = count_stmt.where(AuditLogRow.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLogRow.action == action)
        count_stmt = count_stmt.where(AuditLogRow.action == action)
    if resource_type:
        stmt = stmt.where(AuditLogRow.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLogRow.resource_type == resource_type)
    if from_ts is not None:
        stmt = stmt.where(AuditLogRow.created_at >= from_ts)
        count_stmt = count_stmt.where(AuditLogRow.created_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditLogRow.created_at <= to_ts)
        count_stmt = count_stmt.where(AuditLogRow.created_at <= to_ts)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = (
        await db.execute(
            stmt.order_by(AuditLogRow.created_at.desc(), AuditLogRow.event_id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return AuditEventPage(items=list(rows), total=total, limit=limit, offset=offset)


async def get_audit_event_admin(
    db: AsyncSession,
    *,
    user: UserContext,
    event_id: str,
) -> AuditLogRow | None:
    row = await db.get(AuditLogRow, event_id)
    if row is None:
        return None
    scoped_tenant_id = _scoped_tenant_id(user, None)
    if scoped_tenant_id is not None and row.tenant_id != scoped_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    return row
