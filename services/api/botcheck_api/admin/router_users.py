from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_admin
from ..database import get_db
from .schemas import (
    AdminUserActionResponse,
    AdminUserCreateRequest,
    AdminUserDetailResponse,
    AdminUserPatchRequest,
    AdminUserPasswordResetRequest,
    AdminUserReset2FAResponse,
    AdminUsersListResponse,
)
from .service_users import (
    create_user_admin,
    get_user_admin,
    list_users_admin,
    lock_user_admin,
    reset_user_2fa_admin,
    reset_user_password_admin,
    revoke_user_sessions_admin,
    unlock_user_admin,
    update_user_admin,
)

router = APIRouter(prefix="/users")


def _detail_response(record) -> AdminUserDetailResponse:
    row = record.row
    return AdminUserDetailResponse(
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        email=row.email,
        role=row.role,
        is_active=row.is_active,
        totp_enabled=row.totp_enabled,
        failed_login_attempts=row.failed_login_attempts,
        locked_until=row.locked_until,
        sessions_invalidated_at=row.sessions_invalidated_at,
        last_login_at=row.last_login_at,
        active_session_count=record.active_session_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=AdminUsersListResponse)
async def list_admin_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUsersListResponse:
    page = await list_users_admin(
        db,
        tenant_id=user.tenant_id,
        limit=limit,
        offset=offset,
    )
    return AdminUsersListResponse(
        items=[_detail_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/", response_model=AdminUserDetailResponse, status_code=201)
async def create_admin_user(
    body: AdminUserCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserDetailResponse:
    try:
        record = await create_user_admin(
            db,
            tenant_id=user.tenant_id,
            email=body.email,
            role=body.role,
            password=body.password,
            is_active=body.is_active,
            actor_id=user.sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _detail_response(record)


@router.get("/{user_id}", response_model=AdminUserDetailResponse)
async def get_admin_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserDetailResponse:
    record = await get_user_admin(db, tenant_id=user.tenant_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _detail_response(record)


@router.patch("/{user_id}", response_model=AdminUserDetailResponse)
async def patch_admin_user(
    user_id: str,
    body: AdminUserPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserDetailResponse:
    try:
        record = await update_user_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            actor_id=user.sub,
            email=(str(body.email) if body.email is not None else None),
            role=body.role,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _detail_response(record)


@router.post("/{user_id}/lock", response_model=AdminUserActionResponse)
async def lock_admin_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserActionResponse:
    try:
        result = await lock_user_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            actor_id=user.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminUserActionResponse(
        user_id=result.user_id,
        revoked_sessions=result.revoked_sessions,
    )


@router.post("/{user_id}/unlock", response_model=AdminUserActionResponse)
async def unlock_admin_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserActionResponse:
    try:
        result = await unlock_user_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            actor_id=user.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminUserActionResponse(user_id=result.user_id)


@router.post("/{user_id}/reset-password", response_model=AdminUserActionResponse)
async def reset_admin_user_password(
    user_id: str,
    body: AdminUserPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserActionResponse:
    try:
        result = await reset_user_password_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            new_password=body.password,
            actor_id=user.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminUserActionResponse(
        user_id=result.user_id,
        revoked_sessions=result.revoked_sessions,
    )


@router.post("/{user_id}/reset-2fa", response_model=AdminUserReset2FAResponse)
async def reset_admin_user_2fa(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserReset2FAResponse:
    try:
        result = await reset_user_2fa_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            actor_id=user.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminUserReset2FAResponse(
        user_id=result.user_id,
        revoked_sessions=result.revoked_sessions,
        recovery_codes_invalidated=result.recovery_codes_invalidated,
    )


@router.delete("/{user_id}/sessions", response_model=AdminUserActionResponse)
async def revoke_admin_user_sessions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> AdminUserActionResponse:
    try:
        result = await revoke_user_sessions_admin(
            db,
            tenant_id=user.tenant_id,
            user_id=user_id,
            actor_id=user.sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminUserActionResponse(
        user_id=result.user_id,
        revoked_sessions=result.revoked_sessions,
    )
