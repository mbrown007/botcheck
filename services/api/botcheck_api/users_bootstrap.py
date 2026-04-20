"""Bootstrap DB-backed local users from users.yaml."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Role, encrypt_totp_secret, normalize_role_value, pwd_context
from .config import settings
from .models import UserRow
from .text_normalization import strip_lower_or_none

logger = logging.getLogger("botcheck.api.users_bootstrap")


@dataclass(frozen=True)
class BootstrapUser:
    email: str
    tenant_id: str
    role: str
    password_hash: str
    is_active: bool
    totp_enabled: bool
    totp_secret_plain: str | None


def _normalise_email(email: str) -> str:
    return strip_lower_or_none(email) or ""


def _load_yaml_bootstrap_users(path: Path) -> list[BootstrapUser]:
    if not path.exists():
        return []

    raw = yaml.safe_load(path.read_text()) or {}
    items = raw.get("users") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []

    out: list[BootstrapUser] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        email = _normalise_email(str(item.get("email") or ""))
        password_hash = str(item.get("password_hash") or "").strip()
        if not email or not password_hash:
            continue
        out.append(
            BootstrapUser(
                email=email,
                tenant_id=str(item.get("tenant_id") or settings.tenant_id),
                role=normalize_role_value(item.get("role")),
                password_hash=password_hash,
                is_active=bool(item.get("is_active", True)),
                totp_enabled=bool(item.get("totp_enabled", False)),
                totp_secret_plain=(
                    str(item.get("totp_secret") or "").strip() or None
                ),
            )
        )
    return out


def _fallback_bootstrap_user() -> BootstrapUser | None:
    if not settings.local_auth_enabled:
        return None
    email = _normalise_email(settings.local_auth_email)
    if not email:
        return None
    stored_hash = settings.local_auth_password_hash.strip()
    if not stored_hash:
        if not settings.local_auth_password.strip():
            return None
        stored_hash = pwd_context.hash(settings.local_auth_password)
    return BootstrapUser(
        email=email,
        tenant_id=settings.tenant_id,
        role=Role.ADMIN.value,
        password_hash=stored_hash,
        is_active=True,
        totp_enabled=False,
        totp_secret_plain=None,
    )


def load_bootstrap_users() -> list[BootstrapUser]:
    if not settings.users_bootstrap_enabled:
        return []

    path = Path(settings.users_bootstrap_path)
    users = _load_yaml_bootstrap_users(path)
    if users:
        return users

    fallback = _fallback_bootstrap_user()
    return [fallback] if fallback else []


async def _get_user_for_tenant_email(
    db: AsyncSession,
    *,
    tenant_id: str,
    email: str,
) -> UserRow | None:
    result = await db.execute(
        select(UserRow).where(
            UserRow.tenant_id == tenant_id,
            UserRow.email == email,
        )
    )
    return result.scalar_one_or_none()


async def bootstrap_users(db: AsyncSession) -> dict[str, int]:
    users = load_bootstrap_users()
    if not users:
        return {"created": 0, "updated": 0, "skipped": 0}

    created = 0
    updated = 0
    skipped = 0
    for item in users:
        existing = await _get_user_for_tenant_email(
            db,
            tenant_id=item.tenant_id,
            email=item.email,
        )
        totp_secret_encrypted: str | None = None
        if item.totp_secret_plain:
            totp_secret_encrypted = encrypt_totp_secret(item.totp_secret_plain)

        if existing is None:
            db.add(
                UserRow(
                    user_id=f"user_{uuid4().hex}",
                    tenant_id=item.tenant_id,
                    email=item.email,
                    role=item.role,
                    password_hash=item.password_hash,
                    is_active=item.is_active,
                    totp_enabled=item.totp_enabled,
                    totp_secret_encrypted=totp_secret_encrypted,
                )
            )
            created += 1
            continue

        changed = False
        if existing.role != item.role:
            existing.role = item.role
            changed = True
        if existing.password_hash != item.password_hash:
            existing.password_hash = item.password_hash
            changed = True
        if existing.is_active != item.is_active:
            existing.is_active = item.is_active
            changed = True
        if existing.totp_enabled != item.totp_enabled:
            existing.totp_enabled = item.totp_enabled
            changed = True
        if totp_secret_encrypted and existing.totp_secret_encrypted != totp_secret_encrypted:
            existing.totp_secret_encrypted = totp_secret_encrypted
            changed = True

        if changed:
            updated += 1
        else:
            skipped += 1

    await db.flush()
    logger.info(
        "users bootstrap complete",
        extra={"users_created": created, "updated": updated, "skipped": skipped},
    )
    return {"created": created, "updated": updated, "skipped": skipped}
