from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import uuid4


class ConflictError(Exception):
    """Raised when a request conflicts with existing resource state."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import database
from ..audit import write_audit_event
from ..auth import tenant_display_name
from ..models import (
    ProviderCatalogRow,
    ProviderCredentialRow,
    ProviderQuotaPolicyRow,
    TenantProviderAssignmentRow,
    TenantRow,
)
from ..providers.service import (
    _PROVIDER_ID_RE,
    decrypt_provider_secret_fields,
    encrypt_provider_secret_fields,
    ensure_provider_registry_seeded,
    get_platform_provider_credential,
    normalize_provider_secret_fields,
    normalize_provider_secret_fields_by_vendor,
    platform_credential_payload,
    provider_seed_env_secret_fields,
    provider_catalog_seed_by_id,
)
from ..providers.usage_service import provider_quota_metric_names_for_capability
from ..providers.usage_service import (
    list_tenant_provider_quota_summary,
    list_tenant_provider_usage_summary,
)

logger = logging.getLogger("botcheck.api.providers.admin")


async def _get_provider_catalog_row(db: AsyncSession, *, provider_id: str) -> ProviderCatalogRow:
    await ensure_provider_registry_seeded(db)
    row = await db.get(ProviderCatalogRow, provider_id)
    if row is None:
        raise LookupError("Provider not found")
    return row


async def _get_tenant_row_or_error(db: AsyncSession, *, tenant_id: str) -> TenantRow:
    row = await db.get(TenantRow, tenant_id)
    if row is None or row.deleted_at is not None:
        raise LookupError("Tenant not found")
    return row


async def _list_provider_assignment_rows(
    db: AsyncSession,
    *,
    provider_id: str,
) -> list[TenantProviderAssignmentRow]:
    return list(
        (
            await db.execute(
                select(TenantProviderAssignmentRow)
                .where(TenantProviderAssignmentRow.provider_id == provider_id)
                .order_by(
                    TenantProviderAssignmentRow.updated_at.desc(),
                    TenantProviderAssignmentRow.created_at.desc(),
                    TenantProviderAssignmentRow.assignment_id.asc(),
                )
            )
        ).scalars().all()
    )


async def _get_current_provider_assignment_row(
    db: AsyncSession,
    *,
    provider_id: str,
) -> TenantProviderAssignmentRow | None:
    rows = await _list_provider_assignment_rows(db, provider_id=provider_id)
    return rows[0] if rows else None


async def upsert_platform_provider_credential(
    db: AsyncSession,
    *,
    provider_id: str,
    secret_fields: dict[str, str],
    actor_id: str,
    actor_tenant_id: str,
) -> ProviderCredentialRow:
    catalog_row = await _get_provider_catalog_row(db, provider_id=provider_id)
    if not catalog_row.supports_platform_credentials:
        raise ValueError("Provider does not support platform credentials")

    seed = provider_catalog_seed_by_id().get(provider_id)
    if seed is not None:
        normalized_secret_fields = normalize_provider_secret_fields(seed, secret_fields)
    else:
        # User-created provider: normalize by vendor heuristic.
        normalized_secret_fields = normalize_provider_secret_fields_by_vendor(
            catalog_row.vendor, secret_fields
        )
    row = await get_platform_provider_credential(db, provider_id=provider_id)
    created = row is None
    now = datetime.now(UTC)
    if row is None:
        row = ProviderCredentialRow(
            credential_id=f"provcred_{uuid4().hex}",
            owner_scope="platform",
            tenant_id=None,
            provider_id=provider_id,
            credential_source="db_encrypted",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    row.credential_source = "db_encrypted"
    row.secret_encrypted = encrypt_provider_secret_fields(normalized_secret_fields)
    row.external_secret_ref = None
    row.validated_at = None
    row.validation_error = None
    row.updated_at = now
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider_credential.created" if created else "provider_credential.updated",
        resource_type="provider",
        resource_id=provider_id,
        detail={
            "provider_id": provider_id,
            "credential_source": row.credential_source,
            "secret_fields": sorted(normalized_secret_fields),
        },
    )
    return row


async def delete_platform_provider_credential(
    db: AsyncSession,
    *,
    provider_id: str,
    actor_id: str,
    actor_tenant_id: str,
) -> None:
    row = await get_platform_provider_credential(db, provider_id=provider_id)
    if row is None:
        raise LookupError("Platform credential not found")
    credential_source = row.credential_source
    await db.delete(row)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider_credential.deleted",
        resource_type="provider",
        resource_id=provider_id,
        detail={"provider_id": provider_id, "credential_source": credential_source},
    )


async def validate_platform_provider_credential_background(*, credential_id: str) -> None:
    factory = database.AsyncSessionLocal
    if factory is None:
        return
    async with factory() as session:
        row = await session.get(ProviderCredentialRow, credential_id)
        if row is None or row.owner_scope != "platform" or row.credential_source != "db_encrypted":
            return
        seed = provider_catalog_seed_by_id().get(row.provider_id)
        try:
            if not row.secret_encrypted:
                row.validation_error = "No credential stored"
                await session.commit()
                return
            secret_fields = decrypt_provider_secret_fields(row.secret_encrypted)
            if seed is not None:
                normalize_provider_secret_fields(seed, secret_fields)
            else:
                # User-created provider: look up the catalog row for the vendor.
                catalog_row = await session.get(ProviderCatalogRow, row.provider_id)
                vendor = catalog_row.vendor if catalog_row is not None else ""
                normalize_provider_secret_fields_by_vendor(vendor, secret_fields)
            row.validated_at = datetime.now(UTC)
            row.validation_error = None
            await session.commit()
            logger.info("provider.credential.validated", extra={"provider_id": row.provider_id})
        except Exception as exc:
            row.validated_at = None
            row.validation_error = str(exc)
            await session.commit()
            logger.warning(
                "provider.credential.validation_failed",
                extra={"provider_id": row.provider_id, "error": str(exc)},
            )


async def list_provider_assignments_admin(
    db: AsyncSession,
    *,
    provider_id: str,
) -> list[dict[str, object]]:
    await _get_provider_catalog_row(db, provider_id=provider_id)
    rows = (
        await db.execute(
            select(TenantProviderAssignmentRow, TenantRow)
            .join(TenantRow, TenantRow.tenant_id == TenantProviderAssignmentRow.tenant_id)
            .where(
                TenantProviderAssignmentRow.provider_id == provider_id,
                TenantRow.deleted_at.is_(None),
            )
            .order_by(
                TenantProviderAssignmentRow.updated_at.desc(),
                TenantProviderAssignmentRow.created_at.desc(),
                TenantProviderAssignmentRow.assignment_id.asc(),
            )
        )
    ).all()
    items: list[dict[str, object]] = []
    for assignment_row, tenant_row in rows:
        items.append(
            {
                "tenant_id": assignment_row.tenant_id,
                "provider_id": assignment_row.provider_id,
                "tenant_display_name": tenant_display_name(tenant_row, tenant_id=tenant_row.tenant_id),
                "enabled": bool(assignment_row.enabled),
                "is_default": bool(assignment_row.is_default),
                "effective_credential_source": str(assignment_row.effective_credential_source),
                "updated_at": assignment_row.updated_at,
            }
        )
    return items


async def get_current_provider_assignment_admin(
    db: AsyncSession,
    *,
    provider_id: str,
) -> TenantProviderAssignmentRow:
    await _get_provider_catalog_row(db, provider_id=provider_id)
    row = await _get_current_provider_assignment_row(db, provider_id=provider_id)
    if row is None:
        raise LookupError("Provider assignment not found")
    return row


def _empty_usage_summary_item(
    provider_row: ProviderCatalogRow,
) -> dict[str, object]:
    return {
        "provider_id": provider_row.provider_id,
        "vendor": provider_row.vendor,
        "model": provider_row.model,
        "capability": provider_row.capability,
        "runtime_scopes": list(provider_row.runtime_scopes or []),
        "last_recorded_at": None,
        "input_tokens_24h": 0,
        "output_tokens_24h": 0,
        "audio_seconds_24h": 0.0,
        "characters_24h": 0,
        "sip_minutes_24h": 0.0,
        "request_count_24h": 0,
        "calculated_cost_microcents_24h": None,
    }


def _empty_quota_summary_item(
    provider_row: ProviderCatalogRow,
) -> dict[str, object]:
    return {
        "provider_id": provider_row.provider_id,
        "vendor": provider_row.vendor,
        "model": provider_row.model,
        "capability": provider_row.capability,
        "metrics": [],
    }


async def get_provider_usage_summary_admin(
    db: AsyncSession,
    *,
    provider_id: str,
) -> tuple[datetime, datetime, dict[str, object]]:
    provider_row = await _get_provider_catalog_row(db, provider_id=provider_id)
    assignment_row = await get_current_provider_assignment_admin(db, provider_id=provider_id)
    window_start, window_end, items = await list_tenant_provider_usage_summary(
        db,
        tenant_id=assignment_row.tenant_id,
    )
    item = next((entry for entry in items if entry["provider_id"] == provider_id), None)
    return window_start, window_end, item or _empty_usage_summary_item(provider_row)


async def get_provider_quota_summary_admin(
    db: AsyncSession,
    *,
    provider_id: str,
) -> tuple[datetime, datetime, dict[str, object]]:
    provider_row = await _get_provider_catalog_row(db, provider_id=provider_id)
    assignment_row = await get_current_provider_assignment_admin(db, provider_id=provider_id)
    window_start, window_end, items = await list_tenant_provider_quota_summary(
        db,
        tenant_id=assignment_row.tenant_id,
    )
    item = next((entry for entry in items if entry["provider_id"] == provider_id), None)
    return window_start, window_end, item or _empty_quota_summary_item(provider_row)


async def assign_provider_to_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    provider_id: str,
    is_default: bool,
    actor_id: str,
    actor_tenant_id: str,
) -> TenantProviderAssignmentRow:
    await _get_provider_catalog_row(db, provider_id=provider_id)
    await _get_tenant_row_or_error(db, tenant_id=tenant_id)
    existing_rows = await _list_provider_assignment_rows(db, provider_id=provider_id)
    row = existing_rows[0] if existing_rows else None
    extras = existing_rows[1:]
    created = row is None
    previous_tenant_id = row.tenant_id if row is not None else None
    now = datetime.now(UTC)
    for extra_row in extras:
        await db.delete(extra_row)
    if row is None:
        row = TenantProviderAssignmentRow(
            assignment_id=f"provassign_{uuid4().hex}",
            tenant_id=tenant_id,
            provider_id=provider_id,
            enabled=True,
            is_default=is_default,
            effective_credential_source="env",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.tenant_id = tenant_id
        row.enabled = True
        row.is_default = is_default
        row.updated_at = now
    stale_quota_rows = (
        await db.execute(
            select(ProviderQuotaPolicyRow).where(
                ProviderQuotaPolicyRow.provider_id == provider_id,
                ProviderQuotaPolicyRow.tenant_id != tenant_id,
            )
        )
    ).scalars().all()
    for quota_row in stale_quota_rows:
        await db.delete(quota_row)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action=(
            "provider_assignment.created"
            if created
            else "provider_assignment.reassigned"
            if previous_tenant_id != tenant_id
            else "provider_assignment.updated"
        ),
        resource_type="tenant_provider_assignment",
        resource_id=provider_id,
        detail={
            "tenant_id": tenant_id,
            "previous_tenant_id": previous_tenant_id,
            "provider_id": provider_id,
            "is_default": is_default,
            "cleared_quota_policy_count": len(stale_quota_rows),
            "deduped_assignment_count": len(extras),
        },
    )
    return row


async def delete_provider_assignment_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    actor_id: str,
    actor_tenant_id: str,
) -> None:
    # Query by provider_id alone — unique post-migration 0055 — to avoid a
    # TOCTOU race where a concurrent reassign changes tenant_id between the
    # caller's lookup and this delete.
    row = (
        await db.execute(
            select(TenantProviderAssignmentRow).where(
                TenantProviderAssignmentRow.provider_id == provider_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("Provider assignment not found")
    tenant_id = row.tenant_id
    quota_rows = (
        await db.execute(
            select(ProviderQuotaPolicyRow).where(
                ProviderQuotaPolicyRow.tenant_id == tenant_id,
                ProviderQuotaPolicyRow.provider_id == provider_id,
            )
        )
    ).scalars().all()
    for quota_row in quota_rows:
        await db.delete(quota_row)
    await db.delete(row)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider_assignment.deleted",
        resource_type="tenant_provider_assignment",
        resource_id=provider_id,
        detail={
            "tenant_id": tenant_id,
            "provider_id": provider_id,
            "cleared_quota_policy_count": len(quota_rows),
        },
    )


async def list_provider_quota_policies_admin(
    db: AsyncSession,
    *,
    provider_id: str,
) -> list[dict[str, object]]:
    await _get_provider_catalog_row(db, provider_id=provider_id)
    rows = (
        await db.execute(
            select(ProviderQuotaPolicyRow, TenantRow)
            .join(TenantRow, TenantRow.tenant_id == ProviderQuotaPolicyRow.tenant_id)
            .where(
                ProviderQuotaPolicyRow.provider_id == provider_id,
                TenantRow.deleted_at.is_(None),
            )
            .order_by(ProviderQuotaPolicyRow.metric.asc(), ProviderQuotaPolicyRow.tenant_id.asc())
        )
    ).all()
    items: list[dict[str, object]] = []
    for policy_row, tenant_row in rows:
        items.append(
            {
                "quota_policy_id": policy_row.quota_policy_id,
                "tenant_id": policy_row.tenant_id,
                "provider_id": policy_row.provider_id,
                "tenant_display_name": tenant_display_name(tenant_row, tenant_id=tenant_row.tenant_id),
                "metric": policy_row.metric,
                "limit_per_day": int(policy_row.limit_per_day),
                "soft_limit_pct": int(policy_row.soft_limit_pct),
                "updated_at": policy_row.updated_at,
            }
        )
    return items


async def upsert_provider_quota_policy_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    tenant_id: str,
    metric: str,
    limit_per_day: int,
    soft_limit_pct: int,
    actor_id: str,
    actor_tenant_id: str,
) -> tuple[ProviderQuotaPolicyRow, TenantRow]:
    provider_row = await _get_provider_catalog_row(db, provider_id=provider_id)
    tenant_row = await _get_tenant_row_or_error(db, tenant_id=tenant_id)
    assignment_row = await _get_current_provider_assignment_row(db, provider_id=provider_id)
    if assignment_row is None:
        raise ValueError("Provider must be assigned to a tenant before quota policies can be configured")
    if assignment_row.tenant_id != tenant_id:
        raise ConflictError(
            f"Provider {provider_id!r} is assigned to tenant {assignment_row.tenant_id!r}, "
            f"not {tenant_id!r}"
        )
    metric_name = str(metric).strip()
    # Validate against the capability-filtered set; this subsumes the global
    # metric-name check so a single clear error message covers both cases.
    allowed_metrics = provider_quota_metric_names_for_capability(provider_row.capability)
    if metric_name not in allowed_metrics:
        raise ValueError(
            f"Metric {metric_name!r} is not supported for capability {provider_row.capability!r}. "
            f"Allowed values: {', '.join(allowed_metrics) or 'none'}"
        )

    row = (
        await db.execute(
            select(ProviderQuotaPolicyRow).where(
                ProviderQuotaPolicyRow.tenant_id == tenant_id,
                ProviderQuotaPolicyRow.provider_id == provider_id,
                ProviderQuotaPolicyRow.metric == metric_name,
            )
        )
    ).scalar_one_or_none()
    created = row is None
    now = datetime.now(UTC)
    if row is None:
        row = ProviderQuotaPolicyRow(
            quota_policy_id=f"provquota_{uuid4().hex}",
            tenant_id=tenant_id,
            provider_id=provider_id,
            metric=metric_name,
            created_at=now,
            updated_at=now,
            limit_per_day=int(limit_per_day),
            soft_limit_pct=int(soft_limit_pct),
        )
        db.add(row)
    row.limit_per_day = int(limit_per_day)
    row.soft_limit_pct = int(soft_limit_pct)
    row.updated_at = now
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider_quota_policy.created" if created else "provider_quota_policy.updated",
        resource_type="provider_quota_policy",
        resource_id=f"{tenant_id}:{provider_id}:{metric_name}",
        detail={
            "tenant_id": tenant_id,
            "provider_id": provider_id,
            "metric": metric_name,
            "limit_per_day": int(limit_per_day),
            "soft_limit_pct": int(soft_limit_pct),
        },
    )
    return row, tenant_row


async def delete_provider_quota_policy_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    tenant_id: str,
    metric: str,
    actor_id: str,
    actor_tenant_id: str,
) -> None:
    await _get_provider_catalog_row(db, provider_id=provider_id)
    metric_name = str(metric).strip()
    row = (
        await db.execute(
            select(ProviderQuotaPolicyRow).where(
                ProviderQuotaPolicyRow.tenant_id == tenant_id,
                ProviderQuotaPolicyRow.provider_id == provider_id,
                ProviderQuotaPolicyRow.metric == metric_name,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("Provider quota policy not found")
    await db.delete(row)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider_quota_policy.deleted",
        resource_type="provider_quota_policy",
        resource_id=f"{tenant_id}:{provider_id}:{metric_name}",
        detail={
            "tenant_id": tenant_id,
            "provider_id": provider_id,
            "metric": metric_name,
        },
    )


async def get_provider_quota_policy_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    tenant_id: str,
    metric: str,
) -> dict[str, object]:
    metric_name = str(metric).strip()
    row = (
        await db.execute(
            select(ProviderQuotaPolicyRow, TenantRow)
            .join(TenantRow, TenantRow.tenant_id == ProviderQuotaPolicyRow.tenant_id)
            .where(
                ProviderQuotaPolicyRow.tenant_id == tenant_id,
                ProviderQuotaPolicyRow.provider_id == provider_id,
                ProviderQuotaPolicyRow.metric == metric_name,
                TenantRow.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise LookupError("Provider quota policy not found")
    policy_row, tenant_row = row
    return {
        "quota_policy_id": policy_row.quota_policy_id,
        "tenant_id": policy_row.tenant_id,
        "provider_id": policy_row.provider_id,
        "tenant_display_name": tenant_display_name(tenant_row, tenant_id=tenant_row.tenant_id),
        "metric": policy_row.metric,
        "limit_per_day": int(policy_row.limit_per_day),
        "soft_limit_pct": int(policy_row.soft_limit_pct),
        "updated_at": policy_row.updated_at,
    }


def provider_credential_response_payload(row: ProviderCredentialRow | None, *, provider_id: str) -> dict[str, object]:
    payload = platform_credential_payload(row)
    if payload is None:
        return {
            "provider_id": provider_id,
            "credential_source": "none",
            "validation_status": "none",
            "validated_at": None,
            "validation_error": None,
            "updated_at": None,
        }
    return {
        "provider_id": provider_id,
        "credential_source": payload["credential_source"],
        "validation_status": payload["validation_status"],
        "validated_at": payload["validated_at"],
        "validation_error": payload["validation_error"],
        "updated_at": payload["updated_at"],
    }


async def create_provider_admin(
    db: AsyncSession,
    *,
    capability: str,
    vendor: str,
    model: str,
    label: str | None,
    api_key: str,
    actor_id: str,
    actor_tenant_id: str,
) -> ProviderCatalogRow:
    """Create a new user-defined provider catalogue entry and store its credential."""
    from uuid import uuid4 as _uuid4

    vendor_norm = vendor.strip().lower()
    model_norm = model.strip()

    # Generate a unique provider_id that won't collide with seeded entries.
    unique_suffix = _uuid4().hex[:8]
    provider_id = f"{vendor_norm}:{model_norm}.{unique_suffix}"

    if not _PROVIDER_ID_RE.fullmatch(provider_id):
        raise ValueError(f"Derived provider_id {provider_id!r} contains invalid characters")

    # Validate the api_key using vendor normalization.
    normalized_secret_fields = normalize_provider_secret_fields_by_vendor(
        vendor_norm, {"api_key": api_key}
    )

    now = datetime.now(UTC)
    catalog_row = ProviderCatalogRow(
        provider_id=provider_id,
        vendor=vendor_norm,
        model=model_norm,
        capability=capability,
        runtime_scopes=[],
        supports_tenant_credentials=False,
        supports_platform_credentials=True,
        label=label,
        user_created=True,
    )
    db.add(catalog_row)
    await db.flush()

    # Store the credential immediately.
    credential_row = ProviderCredentialRow(
        credential_id=f"provcred_{_uuid4().hex}",
        owner_scope="platform",
        tenant_id=None,
        provider_id=provider_id,
        credential_source="db_encrypted",
        created_at=now,
        updated_at=now,
    )
    credential_row.credential_source = "db_encrypted"
    credential_row.secret_encrypted = encrypt_provider_secret_fields(normalized_secret_fields)
    credential_row.external_secret_ref = None
    credential_row.validated_at = None
    credential_row.validation_error = None
    db.add(credential_row)
    await db.flush()

    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider.created",
        resource_type="provider",
        resource_id=provider_id,
        detail={
            "provider_id": provider_id,
            "vendor": vendor_norm,
            "model": model_norm,
            "capability": capability,
            "label": label,
        },
    )
    return catalog_row


async def update_provider_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    label: str | None,
    actor_id: str,
    actor_tenant_id: str,
) -> ProviderCatalogRow:
    row = await _get_provider_catalog_row(db, provider_id=provider_id)
    previous_label = row.label
    row.label = label
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider.updated",
        resource_type="provider",
        resource_id=provider_id,
        detail={
            "provider_id": provider_id,
            "label_before": previous_label,
            "label_after": label,
        },
    )
    return row


async def import_env_provider_credentials_admin(
    db: AsyncSession,
    *,
    actor_id: str,
    actor_tenant_id: str,
) -> list[dict[str, str]]:
    await ensure_provider_registry_seeded(db)
    items: list[dict[str, str]] = []
    for provider_id, seed in provider_catalog_seed_by_id().items():
        if not seed.supports_platform_credentials:
            items.append(
                {
                    "provider_id": provider_id,
                    "status": "skipped",
                    "detail": "Provider does not support platform credentials",
                }
            )
            continue

        secret_fields = provider_seed_env_secret_fields(seed)
        if secret_fields is None:
            items.append(
                {
                    "provider_id": provider_id,
                    "status": "skipped",
                    "detail": "No legacy env credential configured",
                }
            )
            continue

        existing = await get_platform_provider_credential(db, provider_id=provider_id)
        if existing is not None:
            items.append(
                {
                    "provider_id": provider_id,
                    "status": "skipped",
                    "detail": "Stored platform credential already exists",
                }
            )
            continue

        await upsert_platform_provider_credential(
            db,
            provider_id=provider_id,
            secret_fields=secret_fields,
            actor_id=actor_id,
            actor_tenant_id=actor_tenant_id,
        )
        items.append(
            {
                "provider_id": provider_id,
                "status": "imported",
                "detail": "Imported legacy env credential into platform-managed storage",
            }
        )

    imported_count = sum(1 for item in items if item["status"] == "imported")
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        action="created",
        resource_type="provider_credentials",
        resource_id="env_import",
        detail={
            "imported_count": imported_count,
            "skipped_count": len(items) - imported_count,
        },
    )
    return items


async def delete_provider_admin(
    db: AsyncSession,
    *,
    provider_id: str,
    actor_id: str,
    actor_tenant_id: str,
) -> None:
    """Delete a user-created provider catalogue entry and all its related data."""
    await ensure_provider_registry_seeded(db)
    row = await db.get(ProviderCatalogRow, provider_id)
    if row is None:
        raise LookupError("Provider not found")
    if not getattr(row, "user_created", False):
        raise ValueError("Only user-created providers can be deleted")

    # Remove assignments and quota policies (cascade via FK would cover it in Postgres
    # but we delete explicitly so the audit trail is clear).
    assignments = (
        await db.execute(
            select(TenantProviderAssignmentRow).where(
                TenantProviderAssignmentRow.provider_id == provider_id
            )
        )
    ).scalars().all()
    for a in assignments:
        await db.delete(a)

    quota_policies = (
        await db.execute(
            select(ProviderQuotaPolicyRow).where(
                ProviderQuotaPolicyRow.provider_id == provider_id
            )
        )
    ).scalars().all()
    for q in quota_policies:
        await db.delete(q)

    # Remove platform credential.
    credential = await get_platform_provider_credential(db, provider_id=provider_id)
    if credential is not None:
        await db.delete(credential)

    await db.delete(row)
    await db.flush()

    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="provider.deleted",
        resource_type="provider",
        resource_id=provider_id,
        detail={"provider_id": provider_id},
    )
