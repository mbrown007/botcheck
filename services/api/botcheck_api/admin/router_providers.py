from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, require_platform_admin
from ..database import get_db
from ..providers.schemas import (
    AdminProviderAssignRequest,
    AdminProviderAssignmentsListResponse,
    AdminProviderAssignmentResponse,
    AdminProviderCreateRequest,
    AdminProviderCredentialMutationResponse,
    AdminProviderCredentialWriteRequest,
    AdminProviderDeleteResponse,
    AdminProviderEnvImportResponse,
    AdminProviderQuotaResponse,
    AdminProviderQuotaPoliciesListResponse,
    AdminProviderQuotaPolicyMutationResponse,
    AdminProviderQuotaPolicyResponse,
    AdminProviderQuotaPolicyWriteRequest,
    AdminProviderSummaryResponse,
    AdminProvidersListResponse,
    AdminProviderUpdateRequest,
    AdminProviderUsageResponse,
)
from ..providers.service import get_platform_provider_credential, list_admin_provider_inventory
from .service_providers import (
    ConflictError,
    create_provider_admin,
    delete_provider_admin,
    delete_provider_assignment_admin,
    delete_provider_quota_policy_admin,
    delete_platform_provider_credential,
    import_env_provider_credentials_admin,
    get_provider_quota_summary_admin,
    get_provider_usage_summary_admin,
    list_provider_quota_policies_admin,
    list_provider_assignments_admin,
    provider_credential_response_payload,
    assign_provider_to_tenant_admin,
    update_provider_admin,
    upsert_provider_quota_policy_admin,
    upsert_platform_provider_credential,
    validate_platform_provider_credential_background,
)
from ..auth import tenant_display_name

router = APIRouter(prefix="/providers")

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9._-]+$")


def _validate_provider_id(provider_id: str) -> None:
    if not _PROVIDER_ID_RE.fullmatch(provider_id):
        raise HTTPException(status_code=422, detail="Invalid provider_id format")


async def _provider_inventory_item_or_500(
    db: AsyncSession,
    *,
    provider_id: str,
) -> AdminProviderSummaryResponse:
    items = await list_admin_provider_inventory(db)
    match = next((item for item in items if item["provider_id"] == provider_id), None)
    if match is None:
        raise HTTPException(status_code=500, detail="Provider found in mutation path but not inventory")
    return AdminProviderSummaryResponse(**match)


@router.get("/", response_model=AdminProvidersListResponse)
async def list_admin_providers(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProvidersListResponse:
    del user
    items = await list_admin_provider_inventory(db)
    return AdminProvidersListResponse(
        items=[AdminProviderSummaryResponse(**item) for item in items],
        total=len(items),
    )


@router.post("/import-env-credentials", response_model=AdminProviderEnvImportResponse)
async def import_admin_provider_env_credentials(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderEnvImportResponse:
    items = await import_env_provider_credentials_admin(
        db,
        actor_id=user.sub,
        actor_tenant_id=user.tenant_id,
    )
    await db.commit()
    for item in items:
        if item["status"] != "imported":
            continue
        row = await get_platform_provider_credential(db, provider_id=item["provider_id"])
        if row is not None:
            background_tasks.add_task(
                validate_platform_provider_credential_background,
                credential_id=row.credential_id,
            )
    return AdminProviderEnvImportResponse(
        imported_count=sum(1 for item in items if item["status"] == "imported"),
        skipped_count=sum(1 for item in items if item["status"] != "imported"),
        items=items,
    )


@router.post("/", response_model=AdminProviderSummaryResponse, status_code=201)
async def create_admin_provider(
    body: AdminProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderSummaryResponse:
    try:
        catalog_row = await create_provider_admin(
            db,
            capability=body.capability,
            vendor=body.vendor,
            model=body.model,
            label=body.label,
            api_key=body.api_key,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _provider_inventory_item_or_500(db, provider_id=catalog_row.provider_id)


@router.patch("/{provider_id}", response_model=AdminProviderSummaryResponse)
async def update_admin_provider(
    provider_id: str,
    body: AdminProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderSummaryResponse:
    _validate_provider_id(provider_id)
    try:
        await update_provider_admin(
            db,
            provider_id=provider_id,
            label=body.label,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
        await db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _provider_inventory_item_or_500(db, provider_id=provider_id)


@router.delete("/{provider_id}", response_model=AdminProviderDeleteResponse)
async def delete_admin_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderDeleteResponse:
    _validate_provider_id(provider_id)
    try:
        await delete_provider_admin(
            db,
            provider_id=provider_id,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
        await db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AdminProviderDeleteResponse(provider_id=provider_id)


@router.get("/{provider_id}/assignments", response_model=AdminProviderAssignmentsListResponse)
async def list_admin_provider_assignments(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderAssignmentsListResponse:
    del user
    _validate_provider_id(provider_id)
    try:
        items = await list_provider_assignments_admin(db, provider_id=provider_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminProviderAssignmentsListResponse(
        items=[AdminProviderAssignmentResponse(**item) for item in items],
        total=len(items),
    )


@router.post("/{provider_id}/assign", response_model=AdminProviderSummaryResponse)
async def assign_admin_provider(
    provider_id: str,
    body: AdminProviderAssignRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderSummaryResponse:
    _validate_provider_id(provider_id)
    try:
        await assign_provider_to_tenant_admin(
            db,
            tenant_id=body.tenant_id,
            provider_id=provider_id,
            is_default=False,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
        await db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Provider is already assigned") from exc
    return await _provider_inventory_item_or_500(db, provider_id=provider_id)


@router.delete("/{provider_id}/assign", response_model=AdminProviderSummaryResponse)
async def delete_admin_provider_assignment(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderSummaryResponse:
    _validate_provider_id(provider_id)
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
    return await _provider_inventory_item_or_500(db, provider_id=provider_id)


@router.get("/{provider_id}/quota-policies", response_model=AdminProviderQuotaPoliciesListResponse)
async def list_admin_provider_quota_policies(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderQuotaPoliciesListResponse:
    del user
    _validate_provider_id(provider_id)
    try:
        items = await list_provider_quota_policies_admin(db, provider_id=provider_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminProviderQuotaPoliciesListResponse(
        items=[AdminProviderQuotaPolicyResponse(**item) for item in items],
        total=len(items),
    )


@router.get("/{provider_id}/usage", response_model=AdminProviderUsageResponse)
async def get_admin_provider_usage(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderUsageResponse:
    del user
    _validate_provider_id(provider_id)
    try:
        window_start, window_end, item = await get_provider_usage_summary_admin(
            db,
            provider_id=provider_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminProviderUsageResponse(
        window_start=window_start,
        window_end=window_end,
        item=item,
    )


@router.get("/{provider_id}/quota", response_model=AdminProviderQuotaResponse)
async def get_admin_provider_quota(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderQuotaResponse:
    del user
    _validate_provider_id(provider_id)
    try:
        window_start, window_end, item = await get_provider_quota_summary_admin(
            db,
            provider_id=provider_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminProviderQuotaResponse(
        window_start=window_start,
        window_end=window_end,
        item=item,
    )


@router.post("/{provider_id}/quota-policies", response_model=AdminProviderQuotaPolicyResponse)
async def upsert_admin_provider_quota_policy(
    provider_id: str,
    body: AdminProviderQuotaPolicyWriteRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderQuotaPolicyResponse:
    _validate_provider_id(provider_id)
    try:
        row, t_row = await upsert_provider_quota_policy_admin(
            db,
            provider_id=provider_id,
            tenant_id=body.tenant_id,
            metric=body.metric,
            limit_per_day=body.limit_per_day,
            soft_limit_pct=body.soft_limit_pct,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return AdminProviderQuotaPolicyResponse(
        quota_policy_id=row.quota_policy_id,
        tenant_id=row.tenant_id,
        provider_id=row.provider_id,
        tenant_display_name=tenant_display_name(t_row, tenant_id=row.tenant_id),
        metric=row.metric,
        limit_per_day=int(row.limit_per_day),
        soft_limit_pct=int(row.soft_limit_pct),
        updated_at=row.updated_at,
    )


@router.delete(
    "/{provider_id}/quota-policies/{tenant_id}/{metric}",
    response_model=AdminProviderQuotaPolicyMutationResponse,
)
async def delete_admin_provider_quota_policy(
    provider_id: str,
    tenant_id: str,
    metric: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderQuotaPolicyMutationResponse:
    _validate_provider_id(provider_id)
    try:
        await delete_provider_quota_policy_admin(
            db,
            provider_id=provider_id,
            tenant_id=tenant_id,
            metric=metric,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminProviderQuotaPolicyMutationResponse(
        provider_id=provider_id,
        tenant_id=tenant_id,
        metric=metric,
        applied=True,
    )


@router.post("/{provider_id}/credentials", response_model=AdminProviderCredentialMutationResponse, status_code=202)
async def upsert_admin_provider_credential(
    provider_id: str,
    body: AdminProviderCredentialWriteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderCredentialMutationResponse:
    _validate_provider_id(provider_id)
    try:
        row = await upsert_platform_provider_credential(
            db,
            provider_id=provider_id,
            secret_fields=body.secret_fields,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    background_tasks.add_task(
        validate_platform_provider_credential_background,
        credential_id=row.credential_id,
    )
    return AdminProviderCredentialMutationResponse(
        **provider_credential_response_payload(row, provider_id=provider_id)
    )


@router.delete("/{provider_id}/credentials", response_model=AdminProviderCredentialMutationResponse)
async def delete_admin_provider_credential(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_platform_admin),
) -> AdminProviderCredentialMutationResponse:
    _validate_provider_id(provider_id)
    try:
        existing = await get_platform_provider_credential(db, provider_id=provider_id)
        await delete_platform_provider_credential(
            db,
            provider_id=provider_id,
            actor_id=user.sub,
            actor_tenant_id=user.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return AdminProviderCredentialMutationResponse(
        **provider_credential_response_payload(existing, provider_id=provider_id)
    )
