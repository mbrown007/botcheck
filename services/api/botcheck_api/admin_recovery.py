"""Operator-only auth recovery actions (Phase 6 hardening item 87)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import write_audit_event
from .auth.core import pwd_context
from .models import AuthSessionRow, RecoveryCodeRow, UserRow
from .text_normalization import strip_lower_or_none


@dataclass(frozen=True)
class AdminRecoveryResult:
    tenant_id: str
    user_id: str
    email: str
    recovery_codes_invalidated: int
    sessions_revoked: int


async def _get_user_by_email(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
) -> UserRow | None:
    normalized_email = strip_lower_or_none(email) or ""
    result = await db.execute(
        select(UserRow).where(
            UserRow.tenant_id == tenant_id,
            UserRow.email == normalized_email,
        )
    )
    return result.scalar_one_or_none()


async def _invalidate_recovery_codes(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    now: datetime,
) -> int:
    result = await db.execute(
        update(RecoveryCodeRow)
        .where(
            RecoveryCodeRow.tenant_id == tenant_id,
            RecoveryCodeRow.user_id == user_id,
            RecoveryCodeRow.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    return int(result.rowcount or 0)


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


async def reset_user_2fa(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
    actor_id: str,
    actor_type: str = "operator",
) -> AdminRecoveryResult:
    user = await _get_user_by_email(db, tenant_id=tenant_id, email=email)
    if user is None:
        raise ValueError("User not found")

    now = datetime.now(UTC)
    invalidated = await _invalidate_recovery_codes(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        now=now,
    )
    revoked = await _revoke_sessions(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        now=now,
    )

    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.sessions_invalidated_at = now

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action="auth.admin_reset_2fa",
        resource_type="user",
        resource_id=user.user_id,
        detail={
            "email": user.email,
            "recovery_codes_invalidated": invalidated,
            "sessions_revoked": revoked,
        },
    )
    await db.flush()
    return AdminRecoveryResult(
        tenant_id=tenant_id,
        user_id=user.user_id,
        email=user.email,
        recovery_codes_invalidated=invalidated,
        sessions_revoked=revoked,
    )


async def reset_user_recovery_codes(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
    actor_id: str,
    actor_type: str = "operator",
) -> AdminRecoveryResult:
    user = await _get_user_by_email(db, tenant_id=tenant_id, email=email)
    if user is None:
        raise ValueError("User not found")

    now = datetime.now(UTC)
    invalidated = await _invalidate_recovery_codes(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        now=now,
    )

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action="auth.admin_reset_recovery_codes",
        resource_type="user",
        resource_id=user.user_id,
        detail={
            "email": user.email,
            "recovery_codes_invalidated": invalidated,
        },
    )
    await db.flush()
    return AdminRecoveryResult(
        tenant_id=tenant_id,
        user_id=user.user_id,
        email=user.email,
        recovery_codes_invalidated=invalidated,
        sessions_revoked=0,
    )


async def reset_user_password(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
    new_password: str,
    actor_id: str,
    actor_type: str = "operator",
) -> AdminRecoveryResult:
    user = await _get_user_by_email(db, tenant_id=tenant_id, email=email)
    if user is None:
        raise ValueError("User not found")

    now = datetime.now(UTC)
    revoked = await _revoke_sessions(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        now=now,
    )

    user.password_hash = pwd_context.hash(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.sessions_invalidated_at = now

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action="auth.admin_reset_password",
        resource_type="user",
        resource_id=user.user_id,
        detail={
            "email": user.email,
            "sessions_revoked": revoked,
        },
    )
    await db.flush()
    return AdminRecoveryResult(
        tenant_id=tenant_id,
        user_id=user.user_id,
        email=user.email,
        recovery_codes_invalidated=0,
        sessions_revoked=revoked,
    )
