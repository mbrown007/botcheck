from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.auth.core import pwd_context
from botcheck_api.config import settings
from botcheck_api.models import AuditLogRow, AuthSessionRow, RecoveryCodeRow, UserRow


def _admin_headers(role: str = "admin") -> dict[str, str]:
    token = issue_user_token(
        UserContext(
            sub="user_test_admin",
            tenant_id=settings.tenant_id,
            role=role,
            amr=("pwd",),
        )
    )
    return {"Authorization": f"Bearer {token}"}


def _user_payload(
    *,
    email: str = "operator@example.com",
    role: str = "operator",
    password: str = "StrongPassword123!",
    is_active: bool = True,
) -> dict[str, object]:
    return {
        "email": email,
        "role": role,
        "password": password,
        "is_active": is_active,
    }


async def _get_user_by_email(email: str) -> UserRow:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await session.execute(
            select(UserRow).where(
                UserRow.tenant_id == settings.tenant_id,
                UserRow.email == email,
            )
        )
        return result.scalar_one()


async def _seed_auth_artifacts(
    *,
    user_id: str,
    recovery_codes: int = 0,
    sessions: int = 0,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    now = datetime.now(UTC)
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        assert user is not None
        user.totp_enabled = True
        user.totp_secret_encrypted = "encrypted-seed"
        user.failed_login_attempts = 2
        user.locked_until = now + timedelta(minutes=5)
        for idx in range(recovery_codes):
            session.add(
                RecoveryCodeRow(
                    code_id=f"rc_{uuid4().hex}",
                    tenant_id=settings.tenant_id,
                    user_id=user_id,
                    batch_id=f"batch_{idx}",
                    code_hash=f"hash-{idx}",
                    consumed_at=None,
                )
            )
        for idx in range(sessions):
            session.add(
                AuthSessionRow(
                    session_id=f"sess_{uuid4().hex}",
                    tenant_id=settings.tenant_id,
                    user_id=user_id,
                    refresh_token_hash=f"refresh-{idx}",
                    amr=["pwd"],
                    issued_at=now,
                    expires_at=now + timedelta(hours=8),
                    revoked_at=None,
                )
            )
        await session.commit()


async def test_admin_users_list_requires_admin(client):
    resp = await client.get("/admin/users/", headers=_admin_headers("viewer"))
    assert resp.status_code == 403


async def test_admin_users_create_list_and_detail(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["email"] == "operator@example.com"
    assert created["role"] == "operator"
    assert created["active_session_count"] == 0
    user_id = created["user_id"]

    list_resp = await client.get("/admin/users/", headers=_admin_headers())
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 2
    assert any(item["user_id"] == user_id for item in listed["items"])

    detail_resp = await client.get(f"/admin/users/{user_id}", headers=_admin_headers())
    assert detail_resp.status_code == 200
    assert detail_resp.json()["email"] == "operator@example.com"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        audit = (
            await session.execute(
                select(AuditLogRow).where(
                    AuditLogRow.tenant_id == settings.tenant_id,
                    AuditLogRow.action == "admin.user.create",
                    AuditLogRow.resource_id == user_id,
                )
            )
        ).scalar_one()
        assert audit.actor_id == "user_test_admin"
        assert audit.detail["role"] == "operator"


async def test_admin_users_patch_role_revokes_sessions(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(email="patch@example.com", role="viewer"),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["user_id"]
    await _seed_auth_artifacts(user_id=user_id, sessions=2)

    patch_resp = await client.patch(
        f"/admin/users/{user_id}",
        json={"role": "editor"},
        headers=_admin_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "editor"
    assert patch_resp.json()["active_session_count"] == 0

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        assert user is not None
        assert user.role == "editor"
        assert user.sessions_invalidated_at is not None
        active_sessions = (
            await session.execute(
                select(AuthSessionRow).where(
                    AuthSessionRow.tenant_id == settings.tenant_id,
                    AuthSessionRow.user_id == user_id,
                    AuthSessionRow.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        assert active_sessions == []


async def test_admin_users_lock_and_unlock_manage_account_state(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(email="lock@example.com"),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["user_id"]
    await _seed_auth_artifacts(user_id=user_id, sessions=1)

    lock_resp = await client.post(f"/admin/users/{user_id}/lock", headers=_admin_headers())
    assert lock_resp.status_code == 200
    assert lock_resp.json()["revoked_sessions"] == 1

    unlock_resp = await client.post(f"/admin/users/{user_id}/unlock", headers=_admin_headers())
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["user_id"] == user_id

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        assert user is not None
        assert user.is_active is True
        assert user.failed_login_attempts == 0
        assert user.locked_until is None


async def test_admin_users_reset_password_revokes_sessions_and_updates_hash(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(email="password@example.com", password="OriginalPass123!"),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["user_id"]
    await _seed_auth_artifacts(user_id=user_id, sessions=2)

    reset_resp = await client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"password": "NewPassword456!"},
        headers=_admin_headers(),
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["revoked_sessions"] == 2

    user = await _get_user_by_email("password@example.com")
    assert pwd_context.verify("NewPassword456!", user.password_hash)
    assert user.sessions_invalidated_at is not None


async def test_admin_users_reset_2fa_revokes_sessions_and_codes(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(email="totp@example.com"),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["user_id"]
    await _seed_auth_artifacts(user_id=user_id, recovery_codes=2, sessions=2)

    reset_resp = await client.post(
        f"/admin/users/{user_id}/reset-2fa",
        headers=_admin_headers(),
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["revoked_sessions"] == 2
    assert reset_resp.json()["recovery_codes_invalidated"] == 2

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        assert user is not None
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None


async def test_admin_users_revoke_sessions_endpoint_invalidates_sessions(client):
    create_resp = await client.post(
        "/admin/users/",
        json=_user_payload(email="sessions@example.com"),
        headers=_admin_headers(),
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["user_id"]
    await _seed_auth_artifacts(user_id=user_id, sessions=3)

    revoke_resp = await client.delete(
        f"/admin/users/{user_id}/sessions",
        headers=_admin_headers(),
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked_sessions"] == 3

    user = await _get_user_by_email("sessions@example.com")
    assert user.sessions_invalidated_at is not None
