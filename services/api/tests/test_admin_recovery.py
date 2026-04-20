from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from botcheck_api import database
from botcheck_api.admin_recovery import reset_user_2fa, reset_user_recovery_codes
from botcheck_api.config import settings
from botcheck_api.models import AuditLogRow, AuthSessionRow, RecoveryCodeRow, UserRow


async def _seed_user_with_auth_artifacts(
    *,
    recovery_codes: int,
    sessions: int,
) -> UserRow:
    factory = database.AsyncSessionLocal
    assert factory is not None
    now = datetime.now(UTC)
    async with factory() as session:
        result = await session.execute(
            select(UserRow).where(
                UserRow.tenant_id == settings.tenant_id,
                UserRow.email == settings.local_auth_email,
            )
        )
        user = result.scalar_one()
        user.totp_enabled = True
        user.totp_secret_encrypted = "encrypted-seed"
        user.failed_login_attempts = 3
        user.locked_until = now + timedelta(minutes=10)
        user.sessions_invalidated_at = None

        for idx in range(recovery_codes):
            session.add(
                RecoveryCodeRow(
                    code_id=f"rc_{uuid4().hex}",
                    tenant_id=user.tenant_id,
                    user_id=user.user_id,
                    batch_id=f"batch_{idx}",
                    code_hash=f"hash-{idx}",
                    consumed_at=None,
                )
            )
        for idx in range(sessions):
            session.add(
                AuthSessionRow(
                    session_id=f"sess_{uuid4().hex}",
                    tenant_id=user.tenant_id,
                    user_id=user.user_id,
                    refresh_token_hash=f"refresh-{idx}",
                    amr=["pwd", "totp"],
                    issued_at=now,
                    expires_at=now + timedelta(hours=8),
                    revoked_at=None,
                )
            )
        await session.commit()
        return user


class TestAdminRecovery:
    async def test_reset_user_2fa_disables_totp_and_revokes_state(self):
        seeded = await _seed_user_with_auth_artifacts(recovery_codes=2, sessions=2)
        factory = database.AsyncSessionLocal
        assert factory is not None

        async with factory() as session:
            result = await reset_user_2fa(
                session,
                tenant_id=settings.tenant_id,
                email=settings.local_auth_email,
                actor_id="operator:cli",
            )
            await session.commit()

        assert result.user_id == seeded.user_id
        assert result.recovery_codes_invalidated == 2
        assert result.sessions_revoked == 2

        async with factory() as session:
            user = (
                await session.execute(
                    select(UserRow).where(
                        UserRow.tenant_id == settings.tenant_id,
                        UserRow.user_id == seeded.user_id,
                    )
                )
            ).scalar_one()
            assert user.totp_enabled is False
            assert user.totp_secret_encrypted is None
            assert user.failed_login_attempts == 0
            assert user.locked_until is None
            assert user.sessions_invalidated_at is not None

            active_codes = (
                await session.execute(
                    select(RecoveryCodeRow).where(
                        RecoveryCodeRow.tenant_id == settings.tenant_id,
                        RecoveryCodeRow.user_id == seeded.user_id,
                        RecoveryCodeRow.consumed_at.is_(None),
                    )
                )
            ).scalars().all()
            assert active_codes == []

            active_sessions = (
                await session.execute(
                    select(AuthSessionRow).where(
                        AuthSessionRow.tenant_id == settings.tenant_id,
                        AuthSessionRow.user_id == seeded.user_id,
                        AuthSessionRow.revoked_at.is_(None),
                    )
                )
            ).scalars().all()
            assert active_sessions == []

            audit = (
                await session.execute(
                    select(AuditLogRow).where(
                        AuditLogRow.tenant_id == settings.tenant_id,
                        AuditLogRow.action == "auth.admin_reset_2fa",
                        AuditLogRow.resource_id == seeded.user_id,
                    )
                )
            ).scalar_one()
            assert audit.actor_type == "operator"
            assert audit.actor_id == "operator:cli"
            assert audit.detail.get("recovery_codes_invalidated") == 2
            assert audit.detail.get("sessions_revoked") == 2

    async def test_reset_user_recovery_codes_invalidates_codes_only(self):
        seeded = await _seed_user_with_auth_artifacts(recovery_codes=3, sessions=1)
        factory = database.AsyncSessionLocal
        assert factory is not None

        async with factory() as session:
            result = await reset_user_recovery_codes(
                session,
                tenant_id=settings.tenant_id,
                email=settings.local_auth_email,
                actor_id="operator:cli",
            )
            await session.commit()

        assert result.user_id == seeded.user_id
        assert result.recovery_codes_invalidated == 3
        assert result.sessions_revoked == 0

        async with factory() as session:
            user = (
                await session.execute(
                    select(UserRow).where(
                        UserRow.tenant_id == settings.tenant_id,
                        UserRow.user_id == seeded.user_id,
                    )
                )
            ).scalar_one()
            assert user.totp_enabled is True
            assert user.totp_secret_encrypted == "encrypted-seed"

            active_sessions = (
                await session.execute(
                    select(AuthSessionRow).where(
                        AuthSessionRow.tenant_id == settings.tenant_id,
                        AuthSessionRow.user_id == seeded.user_id,
                        AuthSessionRow.revoked_at.is_(None),
                    )
                )
            ).scalars().all()
            assert len(active_sessions) == 1

            audit = (
                await session.execute(
                    select(AuditLogRow).where(
                        AuditLogRow.tenant_id == settings.tenant_id,
                        AuditLogRow.action == "auth.admin_reset_recovery_codes",
                        AuditLogRow.resource_id == seeded.user_id,
                    )
                )
            ).scalar_one()
            assert audit.actor_type == "operator"
            assert audit.actor_id == "operator:cli"
            assert audit.detail.get("recovery_codes_invalidated") == 3

    async def test_reset_user_2fa_raises_for_unknown_user(self):
        factory = database.AsyncSessionLocal
        assert factory is not None
        async with factory() as session:
            with pytest.raises(ValueError, match="User not found"):
                await reset_user_2fa(
                    session,
                    tenant_id=settings.tenant_id,
                    email="missing@botcheck.local",
                    actor_id="operator:cli",
                )
