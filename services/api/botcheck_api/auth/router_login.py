"""
Auth login routes: POST /auth/login, POST /auth/login/totp.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import (
    decode_totp_challenge_token,
    get_auth_provider,
    issue_totp_challenge_token,
    issue_user_token,
    require_active_tenant_context,
    tenant_display_name,
    user_context_from_row,
)
from ..auth.security import check_login_rate_limit, consume_totp_counter_once
from ..config import settings
from ..database import get_db
from ..models import UserRow
from ..text_normalization import strip_lower_or_none
from ..auth.totp import resolve_totp_counter
from .router_sessions import create_auth_session, get_user_by_id, invalid_credentials, client_ip
from .router_totp import _consume_recovery_code, _count_active_recovery_codes

router = APIRouter(prefix="/auth")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str = Field(min_length=5)
    password: str = Field(min_length=1)
    tenant_id: str | None = None


class LoginResponse(BaseModel):
    requires_totp: bool = False
    challenge_token: str | None = None
    challenge_expires_in_s: int | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    expires_in_s: int | None = None
    refresh_expires_in_s: int | None = None
    tenant_id: str
    tenant_name: str
    role: str


class TotpLoginRequest(BaseModel):
    challenge_token: str = Field(min_length=16)
    code: str = Field(min_length=6, max_length=16)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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


def _is_user_locked(user: UserRow) -> bool:
    if not user.locked_until:
        return False
    lu = user.locked_until
    if lu.tzinfo is None:
        lu = lu.replace(tzinfo=UTC)
    return lu > datetime.now(UTC)


def _login_rate_limit_key(tenant_id: str, email: str, client_ip: str) -> str:
    return f"{tenant_id}:{strip_lower_or_none(email) or ''}:{client_ip}"


def _apply_lockout_if_needed(user: UserRow) -> bool:
    threshold = settings.local_auth_lockout_failed_attempts
    if threshold <= 0:
        return False
    if user.failed_login_attempts < threshold:
        return False
    user.locked_until = datetime.now(UTC) + timedelta(
        seconds=settings.local_auth_lockout_duration_s
    )
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    if not settings.local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local auth is disabled",
        )

    requested_tenant = (body.tenant_id or settings.tenant_id).strip()
    if requested_tenant != settings.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    tenant = await require_active_tenant_context(
        db,
        tenant_id=requested_tenant,
        enforce_instance_tenant=True,
    )

    client_ip_ = client_ip(request)
    normalized_email = strip_lower_or_none(body.email) or ""
    allowed, retry_after_s = check_login_rate_limit(
        key=_login_rate_limit_key(requested_tenant, normalized_email, client_ip_),
        max_attempts=settings.local_auth_rate_limit_attempts,
        window_s=settings.local_auth_rate_limit_window_s,
    )
    if not allowed:
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=f"ip:{client_ip_}",
            actor_type="anonymous",
            action="auth.login_rate_limited",
            resource_type="user_login",
            resource_id=normalized_email or "unknown",
            detail={"retry_after_s": retry_after_s},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after_s)},
        )

    # normalized_email is already strip_lower_or_none'd above; _get_user_by_email
    # normalizes internally too, but idempotent on a pre-normalized value.
    user = await _get_user_by_email(
        db,
        tenant_id=requested_tenant,
        email=normalized_email,
    )
    if user is None:
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=f"ip:{client_ip_}",
            actor_type="anonymous",
            action="auth.login_failed",
            resource_type="user_login",
            resource_id=normalized_email or "unknown",
            detail={"reason": "user_not_found"},
        )
        await db.commit()
        raise invalid_credentials()

    if not user.is_active:
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.login_failed",
            resource_type="user",
            resource_id=user.user_id,
            detail={"reason": "user_inactive"},
        )
        await db.commit()
        raise invalid_credentials()

    if _is_user_locked(user):
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.login_blocked_locked",
            resource_type="user",
            resource_id=user.user_id,
            detail={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
        )
        await db.commit()
        raise invalid_credentials()

    if not get_auth_provider().verify_password_hash(body.password, user.password_hash):
        user.failed_login_attempts += 1
        lockout_applied = _apply_lockout_if_needed(user)
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.login_failed",
            resource_type="user",
            resource_id=user.user_id,
            detail={
                "reason": "invalid_password",
                "failed_login_attempts": user.failed_login_attempts,
            },
        )
        if lockout_applied:
            await write_audit_event(
                db,
                tenant_id=requested_tenant,
                actor_id=user.user_id,
                actor_type="user",
                action="auth.lockout_applied",
                resource_type="user",
                resource_id=user.user_id,
                detail={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
            )
        # Persist failed-attempt counters even when returning 401.
        await db.commit()
        raise invalid_credentials()

    user.failed_login_attempts = 0
    user.locked_until = None
    if user.totp_enabled:
        challenge_token = issue_totp_challenge_token(
            user_context_from_row(user, amr=("pwd",))
        )
        await write_audit_event(
            db,
            tenant_id=requested_tenant,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.totp_challenge_issued",
            resource_type="user",
            resource_id=user.user_id,
            detail={"client_ip": client_ip_},
        )
        await db.flush()
        return LoginResponse(
            requires_totp=True,
            challenge_token=challenge_token,
            challenge_expires_in_s=settings.auth_totp_challenge_ttl_s,
            tenant_id=user.tenant_id,
            tenant_name=tenant_display_name(tenant, tenant_id=user.tenant_id),
            role=user.role,
        )

    user.last_login_at = datetime.now(UTC)
    refresh_token, session_id, refresh_ttl_s = await create_auth_session(
        db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        amr=("pwd",),
    )
    token = issue_user_token(
        user_context_from_row(user),
        amr=["pwd"],
        session_id=session_id,
    )
    await write_audit_event(
        db,
        tenant_id=requested_tenant,
        actor_id=user.user_id,
        actor_type="user",
        action="auth.login_success",
        resource_type="user",
        resource_id=user.user_id,
        detail={"amr": ["pwd"], "client_ip": client_ip_},
    )
    await db.flush()
    return LoginResponse(
        requires_totp=False,
        access_token=token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_s=settings.local_auth_token_ttl_s,
        refresh_expires_in_s=refresh_ttl_s,
        tenant_id=settings.tenant_id,
        tenant_name=tenant_display_name(tenant, tenant_id=user.tenant_id),
        role=user.role,
    )


@router.post("/login/totp", response_model=LoginResponse)
async def login_totp(
    body: TotpLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    client_ip_ = client_ip(request)
    claims = decode_totp_challenge_token(body.challenge_token)
    if claims.tenant_id != settings.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    tenant = await require_active_tenant_context(
        db,
        tenant_id=claims.tenant_id,
        enforce_instance_tenant=True,
    )

    user = await get_user_by_id(
        db,
        tenant_id=claims.tenant_id,
        user_id=claims.sub,
    )
    if user is None:
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=f"sub:{claims.sub}",
            actor_type="anonymous",
            action="auth.totp_failed",
            resource_type="user_login",
            resource_id=claims.sub,
            detail={"reason": "user_not_found"},
        )
        await db.commit()
        raise invalid_credentials()

    if not user.is_active:
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.totp_failed",
            resource_type="user",
            resource_id=user.user_id,
            detail={"reason": "user_inactive"},
        )
        await db.commit()
        raise invalid_credentials()

    if _is_user_locked(user):
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.login_blocked_locked",
            resource_type="user",
            resource_id=user.user_id,
            detail={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
        )
        await db.commit()
        raise invalid_credentials()

    if not user.totp_enabled or not user.totp_secret_encrypted:
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.totp_failed",
            resource_type="user",
            resource_id=user.user_id,
            detail={"reason": "totp_not_configured"},
        )
        await db.commit()
        raise invalid_credentials()

    from ..auth import decrypt_totp_secret
    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    matched_counter = resolve_totp_counter(
        secret,
        body.code,
        step_s=settings.auth_totp_step_s,
        window=settings.auth_totp_window,
    )
    used_recovery_code = False
    if matched_counter is None:
        used_recovery_code = await _consume_recovery_code(
            db,
            tenant_id=claims.tenant_id,
            user_id=user.user_id,
            candidate=body.code,
        )

    if matched_counter is None and not used_recovery_code:
        user.failed_login_attempts += 1
        lockout_applied = _apply_lockout_if_needed(user)
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.totp_failed",
            resource_type="user",
            resource_id=user.user_id,
            detail={
                "reason": "invalid_totp_or_recovery_code",
                "failed_login_attempts": user.failed_login_attempts,
            },
        )
        if lockout_applied:
            await write_audit_event(
                db,
                tenant_id=claims.tenant_id,
                actor_id=user.user_id,
                actor_type="user",
                action="auth.lockout_applied",
                resource_type="user",
                resource_id=user.user_id,
                detail={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
            )
        # Persist failed-attempt counters even when returning 401.
        await db.commit()
        raise invalid_credentials()

    if not used_recovery_code:
        replay_key = f"{claims.tenant_id}:{user.user_id}:{matched_counter}"
        replay_ok = consume_totp_counter_once(
            key=replay_key,
            ttl_s=settings.auth_totp_replay_ttl_s,
        )
        if not replay_ok:
            await write_audit_event(
                db,
                tenant_id=claims.tenant_id,
                actor_id=user.user_id,
                actor_type="user",
                action="auth.totp_replay_blocked",
                resource_type="user",
                resource_id=user.user_id,
                detail={"counter": matched_counter},
            )
            await db.commit()
            raise invalid_credentials()
    else:
        remaining = await _count_active_recovery_codes(
            db,
            tenant_id=claims.tenant_id,
            user_id=user.user_id,
        )
        await write_audit_event(
            db,
            tenant_id=claims.tenant_id,
            actor_id=user.user_id,
            actor_type="user",
            action="auth.recovery_code_consumed",
            resource_type="user",
            resource_id=user.user_id,
            detail={"remaining": remaining},
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    amr = ["pwd", "recovery_code"] if used_recovery_code else ["pwd", "totp"]
    refresh_token, session_id, refresh_ttl_s = await create_auth_session(
        db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        amr=tuple(amr),
    )
    token = issue_user_token(
        user_context_from_row(user, amr=tuple(amr)),
        amr=amr,
        session_id=session_id,
    )
    await write_audit_event(
        db,
        tenant_id=claims.tenant_id,
        actor_id=user.user_id,
        actor_type="user",
        action="auth.login_success",
        resource_type="user",
        resource_id=user.user_id,
        detail={"amr": amr, "client_ip": client_ip_},
    )
    await db.flush()
    return LoginResponse(
        requires_totp=False,
        access_token=token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_s=settings.local_auth_token_ttl_s,
        refresh_expires_in_s=refresh_ttl_s,
        tenant_id=user.tenant_id,
        tenant_name=tenant_display_name(tenant, tenant_id=user.tenant_id),
        role=user.role,
    )
