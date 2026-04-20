"""
TOTP management routes:
  GET  /auth/totp/status
  POST /auth/totp/enroll/start
  POST /auth/totp/enroll/confirm
  POST /auth/totp/recovery-codes/regenerate
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO
from secrets import choice
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import (
    UserContext,
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_tenant_row,
    pwd_context,
    require_viewer,
    tenant_display_name,
)
from ..auth.security import consume_totp_counter_once
from ..config import settings
from ..database import get_db
from ..models import RecoveryCodeRow
from ..auth.totp import generate_totp_secret, resolve_totp_counter
from .router_sessions import get_user_by_id, invalid_credentials

import qrcode
from qrcode.image.svg import SvgPathImage

router = APIRouter(prefix="/auth")

_RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RECOVERY_CODE_GROUPS = 3
_RECOVERY_CODE_GROUP_LEN = 4
_RECOVERY_CODE_COUNT = 10


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TotpStatusResponse(BaseModel):
    totp_enabled: bool
    enrollment_pending: bool
    recovery_codes_remaining: int


class TotpEnrollmentStartResponse(BaseModel):
    secret: str
    otpauth_uri: str
    otpauth_qr_data_url: str
    issuer: str
    account_name: str


class TotpEnrollmentConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class TotpEnrollmentConfirmResponse(BaseModel):
    totp_enabled: bool
    recovery_codes: list[str] | None = None


class TotpRecoveryCodesRegenerateResponse(BaseModel):
    recovery_codes: list[str]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _totp_issuer(tenant_name: str) -> str:
    return f"BotCheck ({tenant_name})"


def _totp_account_name(user: "UserRow") -> str:  # noqa: F821
    return f"{settings.tenant_id}:{user.email}"


def _build_otpauth_uri(user: "UserRow", secret: str, *, issuer: str) -> str:  # noqa: F821
    label = quote(f"{issuer}:{_totp_account_name(user)}", safe="")
    issuer_q = quote(issuer, safe="")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}&issuer={issuer_q}&digits=6&period={settings.auth_totp_step_s}"
    )


def _build_otpauth_qr_data_url(otpauth_uri: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def _normalize_recovery_code(value: str) -> str:
    return "".join(ch for ch in value.strip().upper() if ch.isalnum())


def _format_recovery_code(normalized: str) -> str:
    return "-".join(
        normalized[i : i + _RECOVERY_CODE_GROUP_LEN]
        for i in range(0, len(normalized), _RECOVERY_CODE_GROUP_LEN)
    )


def _generate_recovery_code() -> str:
    raw = "".join(
        choice(_RECOVERY_CODE_ALPHABET)
        for _ in range(_RECOVERY_CODE_GROUPS * _RECOVERY_CODE_GROUP_LEN)
    )
    return _format_recovery_code(raw)


async def _get_active_recovery_codes(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> list[RecoveryCodeRow]:
    from sqlalchemy import select
    result = await db.execute(
        select(RecoveryCodeRow).where(
            RecoveryCodeRow.tenant_id == tenant_id,
            RecoveryCodeRow.user_id == user_id,
            RecoveryCodeRow.consumed_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def _count_active_recovery_codes(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> int:
    rows = await _get_active_recovery_codes(db, tenant_id=tenant_id, user_id=user_id)
    return len(rows)


async def _issue_recovery_codes(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
) -> tuple[list[str], int]:
    now = datetime.now(UTC)
    invalidated_count = 0
    existing_rows = await _get_active_recovery_codes(db, tenant_id=tenant_id, user_id=user_id)
    for row in existing_rows:
        row.consumed_at = now
        invalidated_count += 1

    batch_id = f"rcb_{uuid4().hex}"
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < _RECOVERY_CODE_COUNT:
        candidate = _generate_recovery_code()
        normalized = _normalize_recovery_code(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        db.add(
            RecoveryCodeRow(
                code_id=f"rc_{uuid4().hex}",
                tenant_id=tenant_id,
                user_id=user_id,
                batch_id=batch_id,
                code_hash=pwd_context.hash(normalized),
            )
        )
        codes.append(candidate)
    return codes, invalidated_count


async def _consume_recovery_code(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    candidate: str,
) -> bool:
    from sqlalchemy import update
    normalized_candidate = _normalize_recovery_code(candidate)
    if not normalized_candidate:
        return False

    rows = await _get_active_recovery_codes(db, tenant_id=tenant_id, user_id=user_id)
    matched_code_id: str | None = None
    for row in rows:
        if pwd_context.verify(normalized_candidate, row.code_hash):
            matched_code_id = row.code_id
            break

    if not matched_code_id:
        return False

    result = await db.execute(
        update(RecoveryCodeRow)
        .where(
            RecoveryCodeRow.code_id == matched_code_id,
            RecoveryCodeRow.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
    )
    return bool(result.rowcount and result.rowcount > 0)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/totp/status", response_model=TotpStatusResponse)
async def totp_status(
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> TotpStatusResponse:
    row = await get_user_by_id(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    remaining = await _count_active_recovery_codes(
        db,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
    )
    return TotpStatusResponse(
        totp_enabled=row.totp_enabled,
        enrollment_pending=bool(row.totp_secret_encrypted and not row.totp_enabled),
        recovery_codes_remaining=remaining,
    )


@router.post("/totp/enroll/start", response_model=TotpEnrollmentStartResponse)
async def start_totp_enrollment(
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> TotpEnrollmentStartResponse:
    row = await get_user_by_id(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if row.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TOTP is already enabled for this user",
        )

    secret = generate_totp_secret()
    row.totp_secret_encrypted = encrypt_totp_secret(secret)
    row.failed_login_attempts = 0
    row.locked_until = None
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=row.user_id,
        actor_type="user",
        action="auth.totp_enroll_started",
        resource_type="user",
        resource_id=row.user_id,
        detail={},
    )
    await db.flush()
    tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
    issuer = _totp_issuer(tenant_display_name(tenant, tenant_id=user.tenant_id))
    otpauth_uri = _build_otpauth_uri(row, secret, issuer=issuer)
    return TotpEnrollmentStartResponse(
        secret=secret,
        otpauth_uri=otpauth_uri,
        otpauth_qr_data_url=_build_otpauth_qr_data_url(otpauth_uri),
        issuer=issuer,
        account_name=_totp_account_name(row),
    )


@router.post("/totp/enroll/confirm", response_model=TotpEnrollmentConfirmResponse)
async def confirm_totp_enrollment(
    body: TotpEnrollmentConfirmRequest,
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> TotpEnrollmentConfirmResponse:
    row = await get_user_by_id(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if row.totp_enabled:
        return TotpEnrollmentConfirmResponse(totp_enabled=True, recovery_codes=None)
    if not row.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TOTP enrollment has not been started",
        )

    secret = decrypt_totp_secret(row.totp_secret_encrypted)
    matched_counter = resolve_totp_counter(
        secret,
        body.code,
        step_s=settings.auth_totp_step_s,
        window=settings.auth_totp_window,
    )
    if matched_counter is None:
        row.failed_login_attempts += 1
        await write_audit_event(
            db,
            tenant_id=user.tenant_id,
            actor_id=row.user_id,
            actor_type="user",
            action="auth.totp_enroll_failed",
            resource_type="user",
            resource_id=row.user_id,
            detail={"reason": "invalid_totp_code"},
        )
        await db.commit()
        raise invalid_credentials()

    replay_key = f"{user.tenant_id}:{row.user_id}:enroll:{matched_counter}"
    replay_ok = consume_totp_counter_once(
        key=replay_key,
        ttl_s=settings.auth_totp_replay_ttl_s,
    )
    if not replay_ok:
        await write_audit_event(
            db,
            tenant_id=user.tenant_id,
            actor_id=row.user_id,
            actor_type="user",
            action="auth.totp_replay_blocked",
            resource_type="user",
            resource_id=row.user_id,
            detail={"counter": matched_counter, "context": "enroll_confirm"},
        )
        await db.commit()
        raise invalid_credentials()

    row.totp_enabled = True
    row.failed_login_attempts = 0
    row.locked_until = None
    recovery_codes, invalidated_count = await _issue_recovery_codes(
        db,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=row.user_id,
        actor_type="user",
        action="auth.totp_enroll_confirmed",
        resource_type="user",
        resource_id=row.user_id,
        detail={
            "recovery_codes_issued": len(recovery_codes),
            "recovery_codes_invalidated": invalidated_count,
        },
    )
    await db.flush()
    return TotpEnrollmentConfirmResponse(
        totp_enabled=True,
        recovery_codes=recovery_codes,
    )


@router.post(
    "/totp/recovery-codes/regenerate",
    response_model=TotpRecoveryCodesRegenerateResponse,
)
async def regenerate_totp_recovery_codes(
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> TotpRecoveryCodesRegenerateResponse:
    row = await get_user_by_id(db, tenant_id=user.tenant_id, user_id=user.sub)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not row.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TOTP must be enabled before generating recovery codes",
        )

    recovery_codes, invalidated_count = await _issue_recovery_codes(
        db,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
    )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=row.user_id,
        actor_type="user",
        action="auth.recovery_codes_regenerated",
        resource_type="user",
        resource_id=row.user_id,
        detail={
            "recovery_codes_issued": len(recovery_codes),
            "recovery_codes_invalidated": invalidated_count,
        },
    )
    await db.flush()
    return TotpRecoveryCodesRegenerateResponse(recovery_codes=recovery_codes)
