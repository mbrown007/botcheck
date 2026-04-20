from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_recovery import reset_user_2fa, reset_user_password
from ..audit import write_audit_event
from ..auth import Role, normalize_role_value
from ..auth.core import pwd_context
from ..models import AuthSessionRow, UserRow
from ..text_normalization import strip_lower_or_none
from .query_users import (
    count_active_sessions_for_user,
    count_active_sessions_for_users,
    count_users_for_tenant,
    get_user_for_tenant,
    get_user_for_tenant_email,
    list_users_for_tenant,
)


@dataclass(frozen=True)
class AdminUserRecord:
    row: UserRow
    active_session_count: int


@dataclass(frozen=True)
class AdminUserPage:
    items: list[AdminUserRecord]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class AdminUserActionResult:
    user_id: str
    revoked_sessions: int = 0


@dataclass(frozen=True)
class AdminUserReset2FAResult:
    user_id: str
    revoked_sessions: int
    recovery_codes_invalidated: int


def _normalize_email(email: str) -> str:
    return strip_lower_or_none(email) or ""


def _validate_assignable_role(role: str | Role) -> str:
    normalized = normalize_role_value(role)
    if normalized == Role.SYSTEM_ADMIN.value:
        raise ValueError("system_admin cannot be assigned from tenant-scoped admin routes")
    return normalized


async def _revoke_sessions(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    now: datetime,
) -> int:
    result = await db.execute(
        update(AuthSessionRow)
        .where(
            AuthSessionRow.tenant_id == tenant_id,
            AuthSessionRow.user_id == user_id,
            AuthSessionRow.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return int(result.rowcount or 0)


async def list_users_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    limit: int,
    offset: int,
) -> AdminUserPage:
    total = await count_users_for_tenant(db, tenant_id=tenant_id)
    rows = await list_users_for_tenant(
        db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    if not rows:
        return AdminUserPage(items=[], total=total, limit=limit, offset=offset)

    counts = await count_active_sessions_for_users(
        db,
        tenant_id=tenant_id,
        user_ids=[row.user_id for row in rows],
        now=datetime.now(UTC),
    )
    return AdminUserPage(
        items=[
            AdminUserRecord(row=row, active_session_count=counts.get(row.user_id, 0))
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_user_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> AdminUserRecord | None:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        return None
    active_session_count = await count_active_sessions_for_user(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    return AdminUserRecord(row=row, active_session_count=active_session_count)


async def create_user_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
    role: str | Role,
    password: str,
    is_active: bool,
    actor_id: str,
) -> AdminUserRecord:
    normalized_email = _normalize_email(email)
    normalized_role = _validate_assignable_role(role)

    existing_user = await get_user_for_tenant_email(
        db,
        tenant_id=tenant_id,
        email=normalized_email,
    )
    if existing_user is not None:
        raise ValueError("User with that email already exists")

    row = UserRow(
        user_id=f"user_{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        email=normalized_email,
        role=normalized_role,
        password_hash=pwd_context.hash(password),
        is_active=is_active,
    )
    db.add(row)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.user.create",
        resource_type="user",
        resource_id=row.user_id,
        detail={"email": row.email, "role": row.role, "is_active": row.is_active},
    )
    return AdminUserRecord(row=row, active_session_count=0)


async def update_user_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    actor_id: str,
    email: str | None = None,
    role: str | Role | None = None,
) -> AdminUserRecord:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")

    detail: dict[str, object] = {}
    now = datetime.now(UTC)

    if email is not None:
        normalized_email = _normalize_email(email)
        if normalized_email != row.email:
            existing_user = await get_user_for_tenant_email(
                db,
                tenant_id=tenant_id,
                email=normalized_email,
                exclude_user_id=user_id,
            )
            if existing_user is not None:
                raise ValueError("User with that email already exists")
            detail["from_email"] = row.email
            detail["to_email"] = normalized_email
            row.email = normalized_email

    revoked_sessions = 0
    if role is not None:
        normalized_role = _validate_assignable_role(role)
        if normalized_role != row.role:
            detail["from_role"] = row.role
            detail["to_role"] = normalized_role
            row.role = normalized_role
            row.sessions_invalidated_at = now
            revoked_sessions = await _revoke_sessions(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                now=now,
            )
            detail["revoked_sessions"] = revoked_sessions

    if not detail:
        return AdminUserRecord(
            row=row,
            active_session_count=await count_active_sessions_for_user(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
            ),
        )

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.user.update",
        resource_type="user",
        resource_id=row.user_id,
        detail=detail,
    )
    return AdminUserRecord(
        row=row,
        active_session_count=await count_active_sessions_for_user(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
        ),
    )


async def lock_user_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    actor_id: str,
) -> AdminUserActionResult:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")

    now = datetime.now(UTC)
    revoked_sessions = await _revoke_sessions(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        now=now,
    )
    row.is_active = False
    row.sessions_invalidated_at = now
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.user.lock",
        resource_type="user",
        resource_id=row.user_id,
        detail={"revoked_sessions": revoked_sessions},
    )
    return AdminUserActionResult(user_id=row.user_id, revoked_sessions=revoked_sessions)


async def unlock_user_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    actor_id: str,
) -> AdminUserActionResult:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")

    row.is_active = True
    row.failed_login_attempts = 0
    row.locked_until = None
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.user.unlock",
        resource_type="user",
        resource_id=row.user_id,
        detail={},
    )
    return AdminUserActionResult(user_id=row.user_id)


async def revoke_user_sessions_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    actor_id: str,
) -> AdminUserActionResult:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")

    now = datetime.now(UTC)
    revoked_sessions = await _revoke_sessions(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        now=now,
    )
    row.sessions_invalidated_at = now
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.user.sessions_revoked",
        resource_type="user",
        resource_id=row.user_id,
        detail={"revoked_sessions": revoked_sessions},
    )
    return AdminUserActionResult(user_id=row.user_id, revoked_sessions=revoked_sessions)


async def reset_user_password_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    new_password: str,
    actor_id: str,
) -> AdminUserActionResult:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")
    result = await reset_user_password(
        db,
        tenant_id=tenant_id,
        email=row.email,
        new_password=new_password,
        actor_id=actor_id,
        actor_type="user",
    )
    return AdminUserActionResult(user_id=row.user_id, revoked_sessions=result.sessions_revoked)


async def reset_user_2fa_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    actor_id: str,
) -> AdminUserReset2FAResult:
    row = await get_user_for_tenant(db, tenant_id=tenant_id, user_id=user_id)
    if row is None:
        raise LookupError("User not found")
    result = await reset_user_2fa(
        db,
        tenant_id=tenant_id,
        email=row.email,
        actor_id=actor_id,
        actor_type="user",
    )
    return AdminUserReset2FAResult(
        user_id=row.user_id,
        revoked_sessions=result.sessions_revoked,
        recovery_codes_invalidated=result.recovery_codes_invalidated,
    )
