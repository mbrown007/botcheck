from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_platform_admin
from ..database import get_db
from ..exceptions import ApiProblem, TENANT_NOT_FOUND
from ..providers.schemas import (
    AdminTenantProviderAssignmentMutationResponse,
    AdminTenantProviderAssignRequest,
)
from .schemas import AdminTenantActionResponse, AdminTenantCreateRequest, AdminTenantDetailResponse, AdminTenantPatchRequest, AdminTenantsListResponse
from .service_providers import assign_provider_to_tenant_admin, delete_provider_assignment_admin
from .service_tenants import (
    UNSET,
    create_tenant_admin,
    delete_tenant_admin,
    get_tenant_admin,
    list_tenants_admin,
    reinstate_tenant_admin,
    suspend_tenant_admin,
    update_tenant_admin,
)

router = APIRouter(prefix="/tenants")

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9._-]+$")


def _detail_response(record) -> AdminTenantDetailResponse:
    row = record.row
    usage = record.usage
    return AdminTenantDetailResponse(
        tenant_id=row.tenant_id,
        slug=row.slug,
        display_name=row.display_name,
        feature_overrides=dict(row.feature_overrides or {}),
        quota_config=dict(row.quota_config or {}),
        effective_quotas={
            "max_concurrent_runs": record.effective_quotas.max_concurrent_runs,
            "max_runs_per_day": record.effective_quotas.max_runs_per_day,
            "max_schedules": record.effective_quotas.max_schedules,
            "max_scenarios": record.effective_quotas.max_scenarios,
            "max_packs": record.effective_quotas.max_packs,
        },
        total_users=usage.total_users,
        active_users=usage.active_users,
        scenario_count=usage.scenario_count,
        schedule_count=usage.schedule_count,
        pack_count=usage.pack_count,
        active_run_count=usage.active_run_count,
        suspended_at=row.suspended_at,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _not_found_problem(detail: str = "Tenant not found") -> ApiProblem:
    return ApiProblem(status=404, error_code=TENANT_NOT_FOUND, detail=detail)


@router.get("/", response_model=AdminTenantsListResponse)
async def list_admin_tenants(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantsListResponse:
    del user
    records, total = await list_tenants_admin(db, limit=limit, offset=offset)
    return AdminTenantsListResponse(
        items=[_detail_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/", response_model=AdminTenantDetailResponse, status_code=201)
async def create_admin_tenant(
    body: AdminTenantCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantDetailResponse:
    try:
        record = await create_tenant_admin(
            db,
            tenant_id=body.tenant_id,
            slug=body.slug,
            display_name=body.display_name,
            feature_overrides=body.feature_overrides,
            quota_config=body.quota_config,
            actor_id=user.sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _detail_response(record)


@router.get("/{tenant_id}", response_model=AdminTenantDetailResponse)
async def get_admin_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantDetailResponse:
    del user
    record = await get_tenant_admin(db, tenant_id=tenant_id)
    if record is None:
        raise _not_found_problem()
    return _detail_response(record)


@router.patch("/{tenant_id}", response_model=AdminTenantDetailResponse)
async def patch_admin_tenant(
    tenant_id: str,
    body: AdminTenantPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantDetailResponse:
    fields = body.model_fields_set
    try:
        record = await update_tenant_admin(
            db,
            tenant_id=tenant_id,
            actor_id=user.sub,
            slug=body.slug if "slug" in fields else UNSET,
            display_name=body.display_name if "display_name" in fields else UNSET,
            feature_overrides=body.feature_overrides if "feature_overrides" in fields else UNSET,
            quota_config=body.quota_config if "quota_config" in fields else UNSET,
        )
    except LookupError as exc:
        raise _not_found_problem(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return _detail_response(record)


@router.post("/{tenant_id}/suspend", response_model=AdminTenantActionResponse)
async def suspend_admin_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantActionResponse:
    try:
        record = await suspend_tenant_admin(db, tenant_id=tenant_id, actor_id=user.sub)
    except LookupError as exc:
        raise _not_found_problem(str(exc)) from exc
    await db.commit()
    return AdminTenantActionResponse(
        tenant_id=record.row.tenant_id,
        suspended_at=record.row.suspended_at,
        deleted_at=record.row.deleted_at,
    )


@router.post("/{tenant_id}/providers/assign", response_model=AdminTenantProviderAssignmentMutationResponse)
async def assign_admin_tenant_provider(
    tenant_id: str,
    body: AdminTenantProviderAssignRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantProviderAssignmentMutationResponse:
    try:
        row = await assign_provider_to_tenant_admin(
            db,
            tenant_id=tenant_id,
            provider_id=body.provider_id,
            is_default=body.is_default,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminTenantProviderAssignmentMutationResponse(
        tenant_id=row.tenant_id,
        provider_id=row.provider_id,
        enabled=row.enabled,
        is_default=row.is_default,
    )


@router.delete(
    "/{tenant_id}/providers/{provider_id}/assign",
    response_model=AdminTenantProviderAssignmentMutationResponse,
)
async def delete_admin_tenant_provider_assignment(
    tenant_id: str,
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantProviderAssignmentMutationResponse:
    if not _PROVIDER_ID_RE.fullmatch(provider_id):
        raise HTTPException(status_code=422, detail="Invalid provider_id format")
    try:
        await delete_provider_assignment_admin(
            db,
            provider_id=provider_id,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminTenantProviderAssignmentMutationResponse(
        tenant_id=tenant_id,
        provider_id=provider_id,
        enabled=False,
        is_default=False,
    )


@router.post("/{tenant_id}/reinstate", response_model=AdminTenantActionResponse)
async def reinstate_admin_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantActionResponse:
    try:
        record = await reinstate_tenant_admin(db, tenant_id=tenant_id, actor_id=user.sub)
    except LookupError as exc:
        raise _not_found_problem(str(exc)) from exc
    await db.commit()
    return AdminTenantActionResponse(
        tenant_id=record.row.tenant_id,
        suspended_at=record.row.suspended_at,
        deleted_at=record.row.deleted_at,
    )


@router.delete("/{tenant_id}", response_model=AdminTenantActionResponse)
async def delete_admin_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminTenantActionResponse:
    try:
        record = await delete_tenant_admin(db, tenant_id=tenant_id, actor_id=user.sub)
    except LookupError as exc:
        raise _not_found_problem(str(exc)) from exc
    await db.commit()
    return AdminTenantActionResponse(
        tenant_id=record.row.tenant_id,
        suspended_at=record.row.suspended_at,
        deleted_at=record.row.deleted_at,
    )
