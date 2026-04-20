from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import ApiProblem, TENANT_QUOTA_EXCEEDED
from ..models import (
    PackRunState,
    PlatformSettingsRow,
    RunRow,
    RunState,
    ScenarioPackRow,
    ScenarioRow,
    ScheduleRow,
    TenantRow,
)

QuotaName = Literal[
    "max_concurrent_runs",
    "max_runs_per_day",
    "max_schedules",
    "max_scenarios",
    "max_packs",
]


@dataclass(frozen=True)
class TenantQuotas:
    max_concurrent_runs: int = 100
    max_runs_per_day: int = 500
    max_schedules: int = 50
    max_scenarios: int = 200
    max_packs: int = 50


DEFAULT_TENANT_QUOTAS = TenantQuotas()
_QUOTA_FIELDS = frozenset(asdict(DEFAULT_TENANT_QUOTAS))


def sanitize_quota_config(config: dict[str, object] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(config, dict):
        return out
    for key in _QUOTA_FIELDS:
        value = config.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"Quota '{key}' must be an integer")
        if not isinstance(value, int):
            raise ValueError(f"Quota '{key}' must be an integer")
        if value < 0:
            raise ValueError(f"Quota '{key}' must be >= 0")
        out[key] = value
    unknown = sorted(set(config) - _QUOTA_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported quota keys: {unknown}")
    return out


def effective_tenant_quotas(
    tenant: TenantRow | None,
    *,
    defaults: TenantQuotas = DEFAULT_TENANT_QUOTAS,
) -> TenantQuotas:
    overrides = sanitize_quota_config(dict(tenant.quota_config or {})) if tenant is not None else {}
    payload = {**asdict(defaults), **overrides}
    return TenantQuotas(**payload)


async def platform_quota_defaults(db: AsyncSession) -> TenantQuotas:
    row = await db.get(PlatformSettingsRow, "default")
    overrides = sanitize_quota_config(dict(row.quota_defaults or {})) if row is not None else {}
    payload = {**asdict(DEFAULT_TENANT_QUOTAS), **overrides}
    return TenantQuotas(**payload)


async def _current_quota_usage(
    db: AsyncSession,
    *,
    tenant_id: str,
    quota_name: QuotaName,
) -> int:
    if quota_name == "max_scenarios":
        result = await db.execute(
            select(func.count(ScenarioRow.scenario_id)).where(ScenarioRow.tenant_id == tenant_id)
        )
        return int(result.scalar_one() or 0)

    if quota_name == "max_schedules":
        result = await db.execute(
            select(func.count(ScheduleRow.schedule_id)).where(ScheduleRow.tenant_id == tenant_id)
        )
        return int(result.scalar_one() or 0)

    if quota_name == "max_packs":
        result = await db.execute(
            select(func.count(ScenarioPackRow.pack_id)).where(ScenarioPackRow.tenant_id == tenant_id)
        )
        return int(result.scalar_one() or 0)

    if quota_name == "max_concurrent_runs":
        active_states = (
            RunState.PENDING.value,
            RunState.RUNNING.value,
            RunState.JUDGING.value,
        )
        result = await db.execute(
            select(func.count(RunRow.run_id)).where(
                RunRow.tenant_id == tenant_id,
                RunRow.state.in_(active_states),
            )
        )
        return int(result.scalar_one() or 0)

    if quota_name == "max_runs_per_day":
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(func.count(RunRow.run_id)).where(
                RunRow.tenant_id == tenant_id,
                RunRow.created_at >= day_start,
            )
        )
        return int(result.scalar_one() or 0)

    raise ValueError(f"Unsupported quota name: {quota_name}")


async def assert_tenant_quota_available(
    db: AsyncSession,
    *,
    tenant: TenantRow | None,
    tenant_id: str,
    quota_name: QuotaName,
    needed: int = 1,
) -> None:
    quotas = effective_tenant_quotas(tenant, defaults=await platform_quota_defaults(db))
    limit = getattr(quotas, quota_name)
    usage = await _current_quota_usage(db, tenant_id=tenant_id, quota_name=quota_name)
    if usage + needed <= limit:
        return
    raise ApiProblem(
        status=409,
        error_code=TENANT_QUOTA_EXCEEDED,
        detail=(
            f"Tenant quota exceeded for {quota_name}: "
            f"limit={limit}, current={usage}, requested={needed}"
        ),
    )
