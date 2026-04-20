from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuthSessionRow, UserRow


async def get_user_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> UserRow | None:
    """Return the user row matching ``tenant_id`` + ``user_id``, or ``None``."""
    result = await db.execute(
        select(UserRow).where(
            UserRow.tenant_id == tenant_id,
            UserRow.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_user_for_tenant_email(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
    exclude_user_id: str | None = None,
) -> UserRow | None:
    """Return the user row matching ``tenant_id`` + ``email``, or ``None``.

    Pass ``exclude_user_id`` to skip a specific user (e.g. when checking for
    email uniqueness during an update, to exclude the user being updated).
    """
    stmt = select(UserRow).where(
        UserRow.tenant_id == tenant_id,
        UserRow.email == email,
    )
    if exclude_user_id is not None:
        stmt = stmt.where(UserRow.user_id != exclude_user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def count_users_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    active_only: bool = False,
) -> int:
    """Return the number of users for ``tenant_id``.

    Set ``active_only=True`` to count only users whose ``is_active`` flag is
    ``True``.
    """
    stmt = select(func.count(UserRow.user_id)).where(UserRow.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(UserRow.is_active.is_(True))
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_users_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    limit: int,
    offset: int,
) -> list[UserRow]:
    """Return a page of user rows for ``tenant_id``, ordered by creation date descending."""
    result = await db.execute(
        select(UserRow)
        .where(UserRow.tenant_id == tenant_id)
        .order_by(UserRow.created_at.desc(), UserRow.user_id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_active_sessions_for_user(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    now: datetime | None = None,
) -> int:
    """Return the number of active (non-revoked, non-expired) sessions for a single user.

    ``now`` defaults to the current UTC time; pass an explicit value in tests to
    control the reference clock.
    """
    observed_now = now or datetime.now(UTC)
    result = await db.execute(
        select(func.count(AuthSessionRow.session_id)).where(
            AuthSessionRow.tenant_id == tenant_id,
            AuthSessionRow.user_id == user_id,
            AuthSessionRow.revoked_at.is_(None),
            AuthSessionRow.expires_at > observed_now,
        )
    )
    return int(result.scalar_one() or 0)


async def count_active_sessions_for_users(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_ids: list[str],
    now: datetime | None = None,
) -> dict[str, int]:
    """Return a mapping of ``{user_id: active_session_count}`` for multiple users.

    Only users with at least one active session appear in the result dict.
    Callers must use ``.get(user_id, 0)`` to handle users with no active
    sessions (GROUP BY omits zero-count rows).

    ``now`` defaults to the current UTC time; pass an explicit value in tests to
    control the reference clock.
    """
    if not user_ids:
        return {}
    observed_now = now or datetime.now(UTC)
    result = await db.execute(
        select(
            AuthSessionRow.user_id,
            func.count(AuthSessionRow.session_id),
        )
        .where(
            AuthSessionRow.tenant_id == tenant_id,
            AuthSessionRow.user_id.in_(user_ids),
            AuthSessionRow.revoked_at.is_(None),
            AuthSessionRow.expires_at > observed_now,
        )
        .group_by(AuthSessionRow.user_id)
    )
    return {str(user_id): int(count) for user_id, count in result.all()}

