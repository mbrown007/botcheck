from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..models import RunRow, ScenarioPackRow, ScenarioRow, ScheduleRow, TenantRow
from .query_users import count_users_for_tenant
from .quota_service import TenantQuotas, platform_quota_defaults, sanitize_quota_config

_TENANT_FEATURE_OVERRIDE_ALLOWLIST = frozenset(
    {
        "tts_cache_enabled",
        "feature_packs_enabled",
        "feature_destinations_enabled",
        "feature_ai_scenarios_enabled",
        "feature_tts_provider_openai_enabled",
        "feature_tts_provider_elevenlabs_enabled",
        "feature_stt_provider_deepgram_enabled",
        "feature_stt_provider_azure_enabled",
    }
)
UNSET = object()


@dataclass(frozen=True)
class TenantUsageSummary:
    total_users: int
    active_users: int
    scenario_count: int
    schedule_count: int
    pack_count: int
    active_run_count: int


@dataclass(frozen=True)
class TenantRecord:
    row: TenantRow
    usage: TenantUsageSummary
    effective_quotas: TenantQuotas


def sanitize_tenant_slug(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not candidate:
        raise ValueError("Tenant slug must not be empty")
    return candidate


def sanitize_tenant_id(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,254}", candidate):
        raise ValueError(
            "Tenant ID must match ^[a-z0-9][a-z0-9_-]{1,254}$"
        )
    return candidate


def sanitize_tenant_display_name(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("Display name must not be empty")
    return candidate


def sanitize_feature_overrides(config: dict[str, object] | None) -> dict[str, bool | int | float]:
    out: dict[str, bool | int | float] = {}
    if config is None:
        return out
    if not isinstance(config, dict):
        raise ValueError("feature_overrides must be an object")
    unknown = sorted(set(config) - _TENANT_FEATURE_OVERRIDE_ALLOWLIST)
    if unknown:
        raise ValueError(f"Unsupported feature override keys: {unknown}")
    for key, value in config.items():
        if isinstance(value, bool):
            out[key] = value
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
            continue
        raise ValueError(f"Feature override '{key}' must be a boolean or number")
    return out


def merge_tenant_feature_overrides(
    base: dict[str, bool],
    overrides: dict[str, object] | None,
) -> dict[str, bool]:
    merged = dict(base)
    for key, value in sanitize_feature_overrides(overrides).items():
        if isinstance(value, bool):
            merged[key] = value
    return merged


def _effective_quotas_for_row(*, row: TenantRow, defaults: TenantQuotas) -> TenantQuotas:
    return TenantQuotas(
        **{
            **defaults.__dict__,
            **sanitize_quota_config(dict(row.quota_config or {})),
        }
    )


async def get_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> TenantRecord | None:
    row = await db.get(TenantRow, tenant_id)
    if row is None:
        return None
    defaults = await platform_quota_defaults(db)
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=tenant_id),
        effective_quotas=_effective_quotas_for_row(row=row, defaults=defaults),
    )


async def list_tenants_admin(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[list[TenantRecord], int]:
    total_result = await db.execute(select(func.count(TenantRow.tenant_id)))
    total = int(total_result.scalar_one() or 0)
    rows_result = await db.execute(
        select(TenantRow)
        .order_by(TenantRow.created_at.desc(), TenantRow.tenant_id.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(rows_result.scalars().all())
    defaults = await platform_quota_defaults(db)
    # TODO: O(N) — build_tenant_usage_summary issues several queries per tenant.
    #   Replace with a single batched query (GROUP BY tenant_id) when list pages grow.
    records = [
        TenantRecord(
            row=row,
            usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
            effective_quotas=_effective_quotas_for_row(row=row, defaults=defaults),
        )
        for row in rows
    ]
    return records, total


async def build_tenant_usage_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> TenantUsageSummary:
    user_total = await count_users_for_tenant(db, tenant_id=tenant_id)
    active_users = await count_users_for_tenant(db, tenant_id=tenant_id, active_only=True)
    scenarios = int(
        (
            await db.execute(
                select(func.count(ScenarioRow.scenario_id)).where(ScenarioRow.tenant_id == tenant_id)
            )
        ).scalar_one()
        or 0
    )
    schedules = int(
        (
            await db.execute(
                select(func.count(ScheduleRow.schedule_id)).where(ScheduleRow.tenant_id == tenant_id)
            )
        ).scalar_one()
        or 0
    )
    packs = int(
        (
            await db.execute(
                select(func.count(ScenarioPackRow.pack_id)).where(ScenarioPackRow.tenant_id == tenant_id)
            )
        ).scalar_one()
        or 0
    )
    active_runs = int(
        (
            await db.execute(
                select(func.count(RunRow.run_id)).where(
                    RunRow.tenant_id == tenant_id,
                    RunRow.state.in_(("pending", "running", "judging")),
                )
            )
        ).scalar_one()
        or 0
    )
    return TenantUsageSummary(
        total_users=user_total,
        active_users=active_users,
        scenario_count=scenarios,
        schedule_count=schedules,
        pack_count=packs,
        active_run_count=active_runs,
    )


async def create_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    slug: str,
    display_name: str,
    feature_overrides: dict[str, object] | None,
    quota_config: dict[str, object] | None,
    actor_id: str,
) -> TenantRecord:
    normalized_tenant_id = sanitize_tenant_id(tenant_id)
    normalized_slug = sanitize_tenant_slug(slug)
    normalized_name = sanitize_tenant_display_name(display_name)
    normalized_features = sanitize_feature_overrides(feature_overrides)
    normalized_quotas = sanitize_quota_config(quota_config)

    if await db.get(TenantRow, normalized_tenant_id) is not None:
        raise ValueError("Tenant already exists")

    existing_slug = await db.execute(select(TenantRow).where(TenantRow.slug == normalized_slug))
    if existing_slug.scalar_one_or_none() is not None:
        raise ValueError("Tenant slug already exists")

    row = TenantRow(
        tenant_id=normalized_tenant_id,
        slug=normalized_slug,
        display_name=normalized_name,
        feature_overrides=normalized_features,
        quota_config=normalized_quotas,
    )
    db.add(row)
    await db.flush()
    from ..providers.service import ensure_provider_registry_seeded

    await ensure_provider_registry_seeded(db, tenant_ids=[row.tenant_id])
    await write_audit_event(
        db,
        tenant_id=row.tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.tenant.create",
        resource_type="tenant",
        resource_id=row.tenant_id,
        detail={
            "slug": row.slug,
            "display_name": row.display_name,
            "feature_overrides": dict(row.feature_overrides or {}),
            "quota_config": dict(row.quota_config or {}),
        },
    )
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
        effective_quotas=_effective_quotas_for_row(
            row=row,
            defaults=await platform_quota_defaults(db),
        ),
    )


async def update_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
    slug: object = UNSET,
    display_name: object = UNSET,
    feature_overrides: object = UNSET,
    quota_config: object = UNSET,
) -> TenantRecord:
    row = await db.get(TenantRow, tenant_id)
    if row is None:
        raise LookupError("Tenant not found")

    detail: dict[str, object] = {}

    if slug is not UNSET:
        normalized_slug = sanitize_tenant_slug(str(slug))
        if normalized_slug != row.slug:
            existing_slug = await db.execute(
                select(TenantRow).where(
                    TenantRow.slug == normalized_slug,
                    TenantRow.tenant_id != row.tenant_id,
                )
            )
            if existing_slug.scalar_one_or_none() is not None:
                raise ValueError("Tenant slug already exists")
            detail["from_slug"] = row.slug
            detail["to_slug"] = normalized_slug
            row.slug = normalized_slug

    if display_name is not UNSET:
        normalized_name = sanitize_tenant_display_name(str(display_name))
        if normalized_name != row.display_name:
            detail["from_display_name"] = row.display_name
            detail["to_display_name"] = normalized_name
            row.display_name = normalized_name

    if feature_overrides is not UNSET:
        normalized_features = sanitize_feature_overrides(
            feature_overrides if isinstance(feature_overrides, dict) else None
        )
        if normalized_features != dict(row.feature_overrides or {}):
            detail["from_feature_overrides"] = dict(row.feature_overrides or {})
            detail["to_feature_overrides"] = normalized_features
            row.feature_overrides = normalized_features

    if quota_config is not UNSET:
        normalized_quotas = sanitize_quota_config(
            quota_config if isinstance(quota_config, dict) else None
        )
        if normalized_quotas != dict(row.quota_config or {}):
            detail["from_quota_config"] = dict(row.quota_config or {})
            detail["to_quota_config"] = normalized_quotas
            row.quota_config = normalized_quotas

    if detail:
        await write_audit_event(
            db,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            actor_type="user",
            action="admin.tenant.update",
            resource_type="tenant",
            resource_id=row.tenant_id,
            detail=detail,
        )
    await db.flush()
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
        effective_quotas=_effective_quotas_for_row(
            row=row,
            defaults=await platform_quota_defaults(db),
        ),
    )


async def suspend_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
) -> TenantRecord:
    row = await db.get(TenantRow, tenant_id)
    if row is None:
        raise LookupError("Tenant not found")
    if row.suspended_at is None:
        row.suspended_at = datetime.now(UTC)
        await write_audit_event(
            db,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            actor_type="user",
            action="admin.tenant.suspend",
            resource_type="tenant",
            resource_id=row.tenant_id,
            detail={},
        )
    await db.flush()
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
        effective_quotas=_effective_quotas_for_row(
            row=row,
            defaults=await platform_quota_defaults(db),
        ),
    )


async def reinstate_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
) -> TenantRecord:
    row = await db.get(TenantRow, tenant_id)
    if row is None:
        raise LookupError("Tenant not found")
    if row.suspended_at is not None:
        row.suspended_at = None
        await write_audit_event(
            db,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            actor_type="user",
            action="admin.tenant.reinstate",
            resource_type="tenant",
            resource_id=row.tenant_id,
            detail={},
        )
    await db.flush()
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
        effective_quotas=_effective_quotas_for_row(
            row=row,
            defaults=await platform_quota_defaults(db),
        ),
    )


async def delete_tenant_admin(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str,
) -> TenantRecord:
    row = await db.get(TenantRow, tenant_id)
    if row is None:
        raise LookupError("Tenant not found")
    if row.deleted_at is None:
        row.deleted_at = datetime.now(UTC)
        await write_audit_event(
            db,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            actor_type="user",
            action="admin.tenant.delete",
            resource_type="tenant",
            resource_id=row.tenant_id,
            detail={"retention_window_days": 30},
        )
    await db.flush()
    return TenantRecord(
        row=row,
        usage=await build_tenant_usage_summary(db, tenant_id=row.tenant_id),
        effective_quotas=_effective_quotas_for_row(
            row=row,
            defaults=await platform_quota_defaults(db),
        ),
    )
