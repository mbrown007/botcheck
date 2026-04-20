"""Immutable audit-log write helper.

Transactional rule:
- Call `write_audit_event()` in the same `AsyncSession` that applies state mutations
- Call it before `db.commit()` finalizes the transaction
- Never defer audit writes to `BackgroundTasks` or external async jobs
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLogRow


async def write_audit_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    actor_type: str = "user",
    detail: dict | None = None,
) -> None:
    row = AuditLogRow(
        event_id=f"audit_{uuid4().hex}",
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
    )
    db.add(row)
    await db.flush()
