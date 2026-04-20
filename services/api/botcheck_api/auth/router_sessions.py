"""
Auth session routes: POST /auth/refresh, POST /auth/logout-all, GET /auth/me.

Also exposes shared helpers used by auth_login.py and auth_totp.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import (
    UserContext,
    build_refresh_token_pair,
    hash_refresh_token_secret,
    issue_user_token,
    parse_refresh_token,
    require_active_tenant_context,
    require_viewer,
    tenant_display_name,
    user_context_from_row,
)
from ..config import settings
from ..database import get_db
from ..models import AuthSessionRow, UserRow

router = APIRouter(prefix="/auth")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CurrentUserResponse(BaseModel):
    sub: str
    tenant_id: str
    role: str
    amr: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_s: int
    refresh_expires_in_s: int
    tenant_id: str
    tenant_name: str
    role: str


class LogoutAllResponse(BaseModel):
    revoked_sessions: int


# ---------------------------------------------------------------------------
# Shared helpers (imported by auth_login.py and auth_totp.py)
# ---------------------------------------------------------------------------


def invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email, password, or verification code",
        headers={"WWW-Authenticate": "Bearer"},
    )


def client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def get_user_by_id(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> UserRow | None:
    result = await db.execute(
        select(UserRow).where(
            UserRow.tenant_id == tenant_id,
            UserRow.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_auth_session_by_id(
    db: AsyncSession,
    *,
    session_id: str,
) -> AuthSessionRow | None:
    result = await db.execute(
        select(AuthSessionRow).where(AuthSessionRow.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def create_auth_session(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    amr: tuple[str, ...],
    expires_at: datetime | None = None,
) -> tuple[str, str, int]:
    now = datetime.now(UTC)
    effective_expires_at = expires_at or (
        now + timedelta(seconds=settings.local_auth_refresh_token_ttl_s)
    )
    if effective_expires_at.tzinfo is None:
        effective_expires_at = effective_expires_at.replace(tzinfo=UTC)
    ttl_s = max(0, int((effective_expires_at - now).total_seconds()))
    session_id, refresh_secret, refresh_token = build_refresh_token_pair()
    db.add(
        AuthSessionRow(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            refresh_token_hash=hash_refresh_token_secret(refresh_secret),
            amr=list(amr),
            issued_at=now,
            expires_at=effective_expires_at,
        )
    )
    return refresh_token, session_id, ttl_s


async def resolve_refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
) -> tuple[AuthSessionRow, UserRow]:
    parsed = parse_refresh_token(refresh_token)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    session_id, refresh_secret = parsed
    session = await get_auth_session_by_id(db, session_id=session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hash_refresh_token_secret(refresh_secret) != session.refresh_token_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(
        db,
        tenant_id=session.tenant_id,
        user_id=session.user_id,
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    issued_at = session.issued_at
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    if user.sessions_invalidated_at and issued_at <= user.sessions_invalidated_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session, user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_session(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    client_ip_ = client_ip(request)
    session, user = await resolve_refresh_session(db, refresh_token=body.refresh_token)
    tenant = await require_active_tenant_context(
        db,
        tenant_id=user.tenant_id,
        enforce_instance_tenant=True,
    )
    now = datetime.now(UTC)
    # Rotate refresh token on every use and preserve absolute session expiry.
    amr = tuple(str(item) for item in (session.amr or ["pwd"]) if str(item))
    refresh_token, new_session_id, refresh_ttl_s = await create_auth_session(
        db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        amr=amr or ("pwd",),
        expires_at=session.expires_at,
    )
    session.revoked_at = now
    session.replaced_by_session_id = new_session_id
    session.last_used_at = now

    access_amr = list(amr or ("pwd",))
    access_token = issue_user_token(
        user_context_from_row(user, amr=tuple(access_amr)),
        amr=access_amr,
        session_id=new_session_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.user_id,
        actor_type="user",
        action="auth.refresh_success",
        resource_type="user",
        resource_id=user.user_id,
        detail={"client_ip": client_ip_},
    )
    await db.flush()
    return RefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_s=settings.local_auth_token_ttl_s,
        refresh_expires_in_s=refresh_ttl_s,
        tenant_id=user.tenant_id,
        tenant_name=tenant_display_name(tenant, tenant_id=user.tenant_id),
        role=user.role,
    )


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all_sessions(
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> LogoutAllResponse:
    row = await get_user_by_id(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    now = datetime.now(UTC)
    result = await db.execute(
        update(AuthSessionRow)
        .where(
            AuthSessionRow.tenant_id == user.tenant_id,
            AuthSessionRow.user_id == user.sub,
            AuthSessionRow.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    revoked_sessions = int(result.rowcount or 0)
    row.sessions_invalidated_at = now
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="auth.logout_all",
        resource_type="user",
        resource_id=user.sub,
        detail={"revoked_sessions": revoked_sessions},
    )
    await db.flush()
    return LogoutAllResponse(revoked_sessions=revoked_sessions)


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(
    user: UserContext = Depends(require_viewer),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        sub=user.sub,
        tenant_id=user.tenant_id,
        role=user.role,
        amr=list(user.amr),
    )
