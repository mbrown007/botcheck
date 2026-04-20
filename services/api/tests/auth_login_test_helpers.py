from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import encrypt_totp_secret
from botcheck_api.config import settings
from botcheck_api.models import AuthSessionRow, RecoveryCodeRow, TenantRow, UserRow

from factories import make_login_payload


async def _configure_totp_for_seed_user(secret: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(UserRow).where(
                UserRow.tenant_id == settings.tenant_id,
                UserRow.email == settings.local_auth_email,
            )
        )
        user = result.scalar_one()
        user.totp_enabled = True
        user.totp_secret_encrypted = encrypt_totp_secret(secret)
        await session.commit()

async def _get_seed_user() -> UserRow:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(UserRow).where(
                UserRow.tenant_id == settings.tenant_id,
                UserRow.email == settings.local_auth_email,
            )
        )
        return result.scalar_one()

async def _active_recovery_rows() -> list[RecoveryCodeRow]:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(RecoveryCodeRow).where(
                RecoveryCodeRow.tenant_id == settings.tenant_id,
                RecoveryCodeRow.user_id == "user_test_admin",
                RecoveryCodeRow.consumed_at.is_(None),
            )
        )
        return list(result.scalars().all())

async def _active_auth_sessions_for_seed_user() -> list[AuthSessionRow]:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(AuthSessionRow).where(
                AuthSessionRow.tenant_id == settings.tenant_id,
                AuthSessionRow.user_id == "user_test_admin",
                AuthSessionRow.revoked_at.is_(None),
            )
        )
        return list(result.scalars().all())

async def _login_headers_for_seed_user(client) -> dict[str, str]:
    login_resp = await client.post(
        "/auth/login",
        json=make_login_payload(),
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()
    token = payload.get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


async def _set_seed_tenant_state(
    *,
    suspended: bool | None = None,
    deleted: bool | None = None,
    display_name: str | None = None,
) -> TenantRow:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(TenantRow).where(TenantRow.tenant_id == settings.tenant_id)
        )
        tenant = result.scalar_one()
        if suspended is not None:
            tenant.suspended_at = datetime.now(UTC) if suspended else None
        if deleted is not None:
            tenant.deleted_at = datetime.now(UTC) if deleted else None
        if display_name is not None:
            tenant.display_name = display_name
        await session.commit()
        return tenant
