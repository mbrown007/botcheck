from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from secrets import token_urlsafe
from typing import Protocol, Sequence
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet, InvalidToken
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config import settings
from ..database import get_db
from ..models import AuthSessionRow, TenantRow, UserRow
from ..text_normalization import strip_lower_or_none

bearer = HTTPBearer(auto_error=False)
# Argon2id primary scheme (H-2 hardening, item 79).
# pbkdf2_sha256 is retained as a deprecated fallback so existing hashes remain
# verifiable; passlib will automatically rehash on the next successful login.
pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    deprecated=["pbkdf2_sha256"],
    argon2__time_cost=2,
    argon2__memory_cost=65536,  # 64 MiB
    argon2__parallelism=2,
)


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    EDITOR = "editor"
    ADMIN = "admin"
    SYSTEM_ADMIN = "system_admin"


_ROLE_RANK: dict[str, int] = {
    Role.VIEWER.value: 0,
    Role.OPERATOR.value: 1,
    Role.EDITOR.value: 2,
    Role.ADMIN.value: 3,
    Role.SYSTEM_ADMIN.value: 4,
}


@dataclass(frozen=True)
class UserContext:
    sub: str
    tenant_id: str
    role: str
    amr: tuple[str, ...] = field(default_factory=lambda: ("pwd",))
    token_iat: int | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class TotpChallengeClaims:
    sub: str
    tenant_id: str
    role: str


class AuthProvider(Protocol):
    """Auth provider contract used by API auth flows.

    Local auth implements this now; OIDC can provide a drop-in adapter later.
    """

    def authenticate(self, email: str, password: str) -> UserContext | None: ...

    def verify_password_hash(self, password: str, password_hash: str) -> bool: ...

    def issue_token(
        self,
        user: UserContext,
        *,
        amr: Sequence[str] | None = None,
        session_id: str | None = None,
    ) -> str: ...

    def verify_token(self, token: str) -> UserContext: ...


def _auth_error(detail: str = "Invalid or missing token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _normalise_email(email: str) -> str:
    return strip_lower_or_none(email) or ""


class LocalAuthProvider:
    """Local password + JWT provider used in Phase 6."""

    def authenticate(self, email: str, password: str) -> UserContext | None:
        if not settings.local_auth_enabled:
            return None
        if _normalise_email(email) != _normalise_email(settings.local_auth_email):
            return None
        if not _verify_local_password(password):
            return None
        return UserContext(
            sub=settings.local_auth_email,
            tenant_id=settings.tenant_id,
            role="admin",
            amr=("pwd",),
        )

    def verify_password_hash(self, password: str, password_hash: str) -> bool:
        try:
            return pwd_context.verify(password, password_hash)
        except Exception:
            return False

    def issue_token(
        self,
        user: UserContext,
        *,
        amr: Sequence[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        now = datetime.now(UTC)
        exp = now + timedelta(seconds=settings.local_auth_token_ttl_s)
        payload = {
            "sub": user.sub,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "iss": settings.auth_issuer,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "amr": list(amr or ["pwd"]),
        }
        if session_id:
            payload["sid"] = session_id
        return jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.auth_algorithm,
        )

    def verify_token(self, token: str) -> UserContext:
        # Dev fallback while OIDC is being integrated.
        if (not settings.is_production) and token == settings.dev_user_token:
            return UserContext(
                sub="dev-user",
                tenant_id=settings.tenant_id,
                role="system_admin",
                amr=("pwd", "dev_token"),
                token_iat=int(datetime.now(UTC).timestamp()),
            )

        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.auth_algorithm],
                issuer=settings.auth_issuer,
            )
        except JWTError as exc:
            raise _auth_error("Invalid token") from exc

        sub = str(payload.get("sub") or "")
        tenant_id = str(payload.get("tenant_id") or "")
        role = str(payload.get("role") or "viewer")
        token_iat_raw = payload.get("iat")
        token_iat: int | None
        if isinstance(token_iat_raw, int):
            token_iat = token_iat_raw
        elif isinstance(token_iat_raw, float):
            token_iat = int(token_iat_raw)
        else:
            token_iat = None
        session_id_raw = payload.get("sid")
        session_id = str(session_id_raw) if session_id_raw else None
        amr_raw = payload.get("amr")
        amr: tuple[str, ...]
        if isinstance(amr_raw, str):
            amr = (amr_raw,)
        elif isinstance(amr_raw, list):
            amr = tuple(str(item) for item in amr_raw if str(item))
        else:
            amr = ("pwd",)
        if not sub or not tenant_id:
            raise _auth_error("Token missing required claims")
        return UserContext(
            sub=sub,
            tenant_id=tenant_id,
            role=role,
            amr=amr,
            token_iat=token_iat,
            session_id=session_id,
        )


_auth_provider: AuthProvider = LocalAuthProvider()


def get_auth_provider() -> AuthProvider:
    return _auth_provider


def set_auth_provider_for_tests(provider: AuthProvider | None) -> None:
    """Allow unit tests to inject a fake provider contract implementation."""
    global _auth_provider
    _auth_provider = provider or LocalAuthProvider()


def _totp_fernet() -> Fernet:
    configured = settings.auth_totp_encryption_key.strip()
    if configured:
        key = configured.encode()
    else:
        # Dev fallback derived from SECRET_KEY. Production should provide
        # AUTH_TOTP_ENCRYPTION_KEY explicitly.
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_totp_secret(secret: str) -> str:
    return _totp_fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(secret_encrypted: str) -> str:
    try:
        return _totp_fernet().decrypt(secret_encrypted.encode()).decode()
    except InvalidToken as exc:
        raise _auth_error("Invalid TOTP secret payload") from exc


def user_context_from_row(user: UserRow, *, amr: Sequence[str] | None = None) -> UserContext:
    return UserContext(
        sub=user.user_id,
        tenant_id=user.tenant_id,
        role=user.role,
        amr=tuple(amr or ("pwd",)),
    )


def _verify_local_password(password: str) -> bool:
    stored_hash = settings.local_auth_password_hash.strip()
    if stored_hash:
        return get_auth_provider().verify_password_hash(password, stored_hash)

    # Dev fallback while hashed bootstrap users are phased in.
    if settings.is_production:
        return False
    expected = settings.local_auth_password
    return bool(expected) and password == expected


def authenticate_local_user(email: str, password: str) -> UserContext | None:
    return get_auth_provider().authenticate(email, password)


def issue_user_token(
    user: UserContext,
    *,
    amr: Sequence[str] | None = None,
    session_id: str | None = None,
) -> str:
    return get_auth_provider().issue_token(
        user,
        amr=amr,
        session_id=session_id,
    )


def hash_refresh_token_secret(secret: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        secret.encode(),
        hashlib.sha256,
    ).hexdigest()


def build_refresh_token_pair() -> tuple[str, str, str]:
    session_id = f"sess_{uuid4().hex}"
    refresh_secret = token_urlsafe(48)
    refresh_token = f"{session_id}.{refresh_secret}"
    return session_id, refresh_secret, refresh_token


def parse_refresh_token(token: str) -> tuple[str, str] | None:
    raw = token.strip()
    if not raw or "." not in raw:
        return None
    session_id, refresh_secret = raw.split(".", 1)
    if not session_id or not refresh_secret:
        return None
    return session_id, refresh_secret


def issue_totp_challenge_token(user: UserContext) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=settings.auth_totp_challenge_ttl_s)
    payload = {
        "sub": user.sub,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "iss": settings.auth_issuer,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "auth_step": "totp_challenge",
        "amr": ["pwd"],
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )


def decode_totp_challenge_token(token: str) -> TotpChallengeClaims:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.auth_algorithm],
            issuer=settings.auth_issuer,
        )
    except JWTError as exc:
        raise _auth_error("Invalid challenge token") from exc

    if payload.get("auth_step") != "totp_challenge":
        raise _auth_error("Invalid challenge token")

    sub = str(payload.get("sub") or "")
    tenant_id = str(payload.get("tenant_id") or "")
    role = str(payload.get("role") or "viewer")
    if not sub or not tenant_id:
        raise _auth_error("Challenge token missing required claims")
    return TotpChallengeClaims(sub=sub, tenant_id=tenant_id, role=role)


def _decode_user_token(token: str) -> UserContext:
    return get_auth_provider().verify_token(token)


async def _load_active_user(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> UserRow | None:
    result = await db.execute(
        select(UserRow).where(
            UserRow.tenant_id == tenant_id,
            UserRow.user_id == user_id,
            UserRow.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_row(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> TenantRow | None:
    result = await db.execute(
        select(TenantRow).where(TenantRow.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


def tenant_display_name(
    tenant: TenantRow | None,
    *,
    tenant_id: str,
) -> str:
    if tenant is not None:
        candidate = tenant.display_name.strip()
        if candidate:
            return candidate
    return tenant_id


async def require_active_tenant_context(
    db: AsyncSession | None,
    *,
    tenant_id: str,
    enforce_instance_tenant: bool = True,
) -> TenantRow | None:
    if enforce_instance_tenant and tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    if db is None:
        return None

    tenant = await get_tenant_row(db, tenant_id=tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not provisioned")
    if tenant.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant deleted")
    if tenant.suspended_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant suspended")
    return tenant


async def _validate_user_token_against_db(
    db: AsyncSession,
    user: UserContext,
) -> UserContext:
    if "dev_token" in user.amr:
        return user
    row = await _load_active_user(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None:
        raise _auth_error("Invalid token")
    if row.sessions_invalidated_at:
        invalidated_at = row.sessions_invalidated_at
        if invalidated_at.tzinfo is None:
            invalidated_at = invalidated_at.replace(tzinfo=UTC)
        revoked_at_ts = int(invalidated_at.timestamp())
        if user.token_iat is None or user.token_iat <= revoked_at_ts:
            raise _auth_error("Session revoked")
    return user


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    if creds is None or not creds.credentials:
        raise _auth_error("Missing bearer token")
    decoded = _decode_user_token(creds.credentials)
    # Preserve 403 semantics from require_tenant_match for mismatched-tenant JWTs.
    if "dev_token" not in decoded.amr and decoded.tenant_id != settings.tenant_id:
        return decoded
    await require_active_tenant_context(
        db,
        tenant_id=decoded.tenant_id,
        enforce_instance_tenant=True,
    )
    return await _validate_user_token_against_db(db, decoded)


async def _get_current_user_any_tenant(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    if creds is None or not creds.credentials:
        raise _auth_error("Missing bearer token")
    decoded = _decode_user_token(creds.credentials)
    await require_active_tenant_context(
        db,
        tenant_id=decoded.tenant_id,
        enforce_instance_tenant=False,
    )
    return await _validate_user_token_against_db(db, decoded)


async def get_current_user_any_tenant(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    return await _get_current_user_any_tenant(creds=creds, db=db)


async def get_optional_current_user_any_tenant(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> UserContext | None:
    if creds is None or not creds.credentials:
        return None
    token = creds.credentials
    if token in {settings.harness_secret, settings.judge_secret, settings.scheduler_secret}:
        return None
    decoded = _decode_user_token(token)
    await require_active_tenant_context(
        db,
        tenant_id=decoded.tenant_id,
        enforce_instance_tenant=not settings.shared_instance_mode,
    )
    return await _validate_user_token_against_db(db, decoded)


def _role_rank(role: str | Role) -> int:
    candidate = (
        role.value if isinstance(role, Role) else strip_lower_or_none(str(role)) or ""
    )
    return _ROLE_RANK.get(candidate, -1)


def normalize_role_value(role: str | Role | None, *, default: Role = Role.VIEWER) -> str:
    candidate = (
        role.value
        if isinstance(role, Role)
        else strip_lower_or_none(None if role is None else str(role))
    ) or ""
    if candidate in _ROLE_RANK:
        return candidate
    return default.value


def _require_minimum_role(
    user: UserContext,
    minimum: Role,
    *,
    enforce_instance_tenant: bool = True,
) -> UserContext:
    if enforce_instance_tenant and user.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    if _role_rank(user.role) < _role_rank(minimum):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return user


def require_role(minimum: Role):
    async def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        return _require_minimum_role(user, minimum)

    return dependency


require_viewer = require_role(Role.VIEWER)
require_operator = require_role(Role.OPERATOR)
require_editor = require_role(Role.EDITOR)
require_admin = require_role(Role.ADMIN)


async def require_platform_admin(
    user: UserContext = Depends(_get_current_user_any_tenant),
) -> UserContext:
    return _require_minimum_role(
        user,
        Role.SYSTEM_ADMIN,
        enforce_instance_tenant=False,
    )


async def require_tenant_match(
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """
    FastAPI dependency: verifies the authenticated user belongs to the configured
    tenant. Raises 403 if the tenant_id does not match.

    TODO(phase-2): Replace instance-tenant check with DB-backed tenant registry lookup.
    """
    if user.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    return user


async def require_any_valid_token(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Accept any valid token — user JWT or internal service secret.

    Used for read endpoints that must be accessible to both UI users and
    internal services (harness, judge) without exposing the full user context.
    """
    if creds is None or not creds.credentials:
        raise _auth_error("Missing bearer token")
    token = creds.credentials
    # Service secrets — fast O(1) check
    if token in {settings.harness_secret, settings.judge_secret, settings.scheduler_secret}:
        return
    # User JWT (also covers dev_user_token via _decode_user_token)
    decoded = _decode_user_token(token)  # raises HTTPException on invalid
    if "dev_token" not in decoded.amr and decoded.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    await require_active_tenant_context(
        db,
        tenant_id=decoded.tenant_id,
        enforce_instance_tenant=True,
    )
    await _validate_user_token_against_db(db, decoded)


async def get_service_caller(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if creds is None or not creds.credentials:
        raise _auth_error("Missing service token")
    token = creds.credentials
    if token == settings.harness_secret:
        return "harness"
    if token == settings.judge_secret:
        return "judge"
    if token == settings.scheduler_secret:
        return "scheduler"
    raise _auth_error("Invalid service token")
