from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics
from ..exceptions import ApiProblem, PROVIDER_QUOTA_EXCEEDED
from ..models import (
    GraiEvalRunRow,
    GraiEvalRunTerminalOutcome,
    ProviderCatalogRow,
    ProviderQuotaPolicyRow,
    ProviderUsageLedgerRow,
)
from .service import ensure_provider_registry_seeded

logger = logging.getLogger("botcheck.api.providers.usage")

# Only these outcomes count toward quota. Runs that failed before any assertion
# ran (execution_failed) or were cancelled should not consume quota budget —
# the work was never completed. New enum members must be explicitly added here
# if they represent finalized, billable outcomes.
_FINALIZED_GRAI_OUTCOMES = (
    GraiEvalRunTerminalOutcome.PASSED.value,
    GraiEvalRunTerminalOutcome.ASSERTION_FAILED.value,
)
_PROVIDER_QUOTA_METRICS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "audio_seconds",
        "characters",
        "sip_minutes",
        "requests",
    }
)


def provider_quota_metric_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDER_QUOTA_METRICS))


def provider_quota_metric_names_for_capability(capability: str) -> tuple[str, ...]:
    capability_name = str(capability).strip()
    metrics_by_capability = {
        "llm": ("input_tokens", "output_tokens", "requests"),
        "judge": ("input_tokens", "output_tokens", "requests"),
        "tts": ("characters", "requests"),
        "stt": ("audio_seconds", "requests"),
        # SIP billing is minute-based only; per-request quotas are not
        # meaningful for SIP trunks and are intentionally excluded.
        "sip": ("sip_minutes",),
    }
    return metrics_by_capability.get(capability_name, ())


@dataclass(frozen=True)
class ProviderQuotaDecision:
    metric: str
    limit_per_day: float
    used_24h: float
    estimated_needed: float
    projected_24h: float
    soft_limit_pct: int
    status: str
    soft_limit_reached: bool
    hard_limit_reached: bool


@dataclass(frozen=True)
class ProviderQuotaCheckResult:
    provider_id: str
    capability: str
    runtime_scope: str
    decisions: tuple[ProviderQuotaDecision, ...]
    blocked: bool
    warning: bool


def provider_usage_window(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    window_end = now or datetime.now(UTC)
    return window_end - timedelta(hours=24), window_end


def judge_run_usage_key(*, run_id: str, provider_id: str) -> str:
    return f"judge-run:{run_id}:{provider_id}"


def grai_eval_pair_usage_key(
    *,
    eval_run_id: str,
    provider_id: str,
    destination_index: int,
    prompt_id: str,
    case_id: str,
) -> str:
    return (
        f"grai-pair:{eval_run_id}:{destination_index}:{prompt_id}:{case_id}:{provider_id}"
    )


def _cost_from_units(
    *,
    catalog_row: ProviderCatalogRow,
    input_tokens: int,
    output_tokens: int,
    audio_seconds: float,
    characters: int,
    sip_minutes: float,
    request_count: int,
) -> int | None:
    total = 0
    has_cost_component = False

    if catalog_row.cost_per_input_token_microcents is not None:
        total += int(catalog_row.cost_per_input_token_microcents) * max(0, input_tokens)
        has_cost_component = True
    if catalog_row.cost_per_output_token_microcents is not None:
        total += int(catalog_row.cost_per_output_token_microcents) * max(0, output_tokens)
        has_cost_component = True
    if catalog_row.cost_per_audio_second_microcents is not None:
        if catalog_row.capability == "sip":
            # SIP providers bill via sip_minutes; convert to seconds for the rate.
            sip_audio_seconds = max(0.0, sip_minutes * 60.0)
            total += int(round(float(catalog_row.cost_per_audio_second_microcents) * sip_audio_seconds))
        else:
            total += int(round(float(catalog_row.cost_per_audio_second_microcents) * max(0.0, audio_seconds)))
        has_cost_component = True
    if catalog_row.cost_per_character_microcents is not None:
        total += int(catalog_row.cost_per_character_microcents) * max(0, characters)
        has_cost_component = True
    if catalog_row.cost_per_request_microcents is not None:
        total += int(catalog_row.cost_per_request_microcents) * max(0, request_count)
        has_cost_component = True

    return total if has_cost_component else None


def _finalized_usage_condition():
    # Three cases to include:
    # 1. Non-grai ledger row (eval_run_id is NULL on the ledger row itself).
    # 2. Orphaned grai ledger row: eval_run_id is set on the ledger but the outer
    #    join found no matching GraiEvalRunRow (GraiEvalRunRow.eval_run_id is NULL
    #    after the outer join). Treat as non-grai rather than silently dropping.
    # 3. Grai row whose run reached a finalized, quota-billable outcome.
    return or_(
        ProviderUsageLedgerRow.eval_run_id.is_(None),
        GraiEvalRunRow.eval_run_id.is_(None),
        GraiEvalRunRow.terminal_outcome.in_(_FINALIZED_GRAI_OUTCOMES),
    )


async def _provider_usage_rollups(
    db: AsyncSession,
    *,
    tenant_id: str,
    window_start: datetime,
    window_end: datetime,
):
    # runtime_scopes is excluded from SELECT and GROUP BY: it is a JSON column
    # and PostgreSQL cannot compare JSON for equality in GROUP BY. Since it is
    # functionally determined by provider_id (a catalog attribute), it is loaded
    # separately and merged in the calling functions.
    stmt = (
        select(
            ProviderUsageLedgerRow.provider_id.label("provider_id"),
            ProviderCatalogRow.vendor.label("vendor"),
            ProviderCatalogRow.model.label("model"),
            ProviderCatalogRow.capability.label("capability"),
            func.max(ProviderUsageLedgerRow.recorded_at).label("last_recorded_at"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.input_tokens), 0).label("input_tokens_24h"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.output_tokens), 0).label("output_tokens_24h"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.audio_seconds), 0.0).label("audio_seconds_24h"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.characters), 0).label("characters_24h"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.sip_minutes), 0.0).label("sip_minutes_24h"),
            func.coalesce(func.sum(ProviderUsageLedgerRow.request_count), 0).label("request_count_24h"),
            func.sum(ProviderUsageLedgerRow.calculated_cost_microcents).label(
                "calculated_cost_microcents_24h"
            ),
        )
        .join(
            ProviderCatalogRow,
            ProviderCatalogRow.provider_id == ProviderUsageLedgerRow.provider_id,
        )
        .outerjoin(
            GraiEvalRunRow,
            and_(
                GraiEvalRunRow.eval_run_id == ProviderUsageLedgerRow.eval_run_id,
                GraiEvalRunRow.tenant_id == ProviderUsageLedgerRow.tenant_id,
            ),
        )
        .where(
            ProviderUsageLedgerRow.tenant_id == tenant_id,
            ProviderUsageLedgerRow.recorded_at >= window_start,
            ProviderUsageLedgerRow.recorded_at <= window_end,
            _finalized_usage_condition(),
        )
        .group_by(
            ProviderUsageLedgerRow.provider_id,
            ProviderCatalogRow.vendor,
            ProviderCatalogRow.model,
            ProviderCatalogRow.capability,
        )
        .order_by(func.max(ProviderUsageLedgerRow.recorded_at).desc(), ProviderUsageLedgerRow.provider_id.asc())
    )
    return list((await db.execute(stmt)).all())


def _usage_value_for_metric(*, usage: dict[str, object] | None, metric: str) -> float:
    if usage is None:
        return 0.0
    field_name = {
        "input_tokens": "input_tokens_24h",
        "output_tokens": "output_tokens_24h",
        "audio_seconds": "audio_seconds_24h",
        "characters": "characters_24h",
        "sip_minutes": "sip_minutes_24h",
        "requests": "request_count_24h",
    }.get(metric)
    if field_name is None:
        logger.warning("provider.quota.unknown_metric", extra={"metric": metric})
        return 0.0
    value = usage.get(field_name, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _normalize_estimated_usage(
    estimated_usage: dict[str, int | float] | None,
) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for metric, raw_value in dict(estimated_usage or {}).items():
        metric_name = str(metric).strip()
        if metric_name not in _PROVIDER_QUOTA_METRICS:
            raise ValueError(f"Unsupported provider quota metric: {metric_name}")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"Estimated provider usage for {metric_name} must be numeric")
        normalized[metric_name] = max(0.0, float(raw_value))
    return normalized


async def _load_catalog_runtime_scopes(
    db: AsyncSession,
    provider_ids: list[str],
) -> dict[str, list[str]]:
    """Return a mapping of provider_id → runtime_scopes for the given provider_ids.

    runtime_scopes is a JSON column that cannot safely be included in a GROUP BY
    on PostgreSQL, so it is loaded separately after aggregation.
    """
    if not provider_ids:
        return {}
    rows = (
        await db.execute(
            select(ProviderCatalogRow.provider_id, ProviderCatalogRow.runtime_scopes).where(
                ProviderCatalogRow.provider_id.in_(provider_ids)
            )
        )
    ).all()
    return {str(row.provider_id): list(row.runtime_scopes or []) for row in rows}


def _usage_item_from_mapping(mapping, *, runtime_scopes: list[str]) -> dict[str, object]:
    return {
        "provider_id": str(mapping["provider_id"]),
        "vendor": str(mapping["vendor"]) if mapping.get("vendor") is not None else "",
        "model": str(mapping["model"]) if mapping.get("model") is not None else "",
        "capability": str(mapping["capability"]) if mapping.get("capability") is not None else "",
        "runtime_scopes": runtime_scopes,
        "last_recorded_at": mapping.get("last_recorded_at"),
        "input_tokens_24h": int(mapping["input_tokens_24h"] or 0),
        "output_tokens_24h": int(mapping["output_tokens_24h"] or 0),
        "audio_seconds_24h": float(mapping["audio_seconds_24h"] or 0.0),
        "characters_24h": int(mapping["characters_24h"] or 0),
        "sip_minutes_24h": float(mapping["sip_minutes_24h"] or 0.0),
        "request_count_24h": int(mapping["request_count_24h"] or 0),
        "calculated_cost_microcents_24h": (
            int(mapping["calculated_cost_microcents_24h"])
            if mapping.get("calculated_cost_microcents_24h") is not None
            else None
        ),
    }


async def list_tenant_provider_usage_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime, list[dict[str, object]]]:
    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    window_start, window_end = provider_usage_window(now=now)
    rows = await _provider_usage_rollups(
        db,
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
    )
    provider_ids = [str(row._mapping["provider_id"]) for row in rows]
    runtime_scopes_map = await _load_catalog_runtime_scopes(db, provider_ids)
    items: list[dict[str, object]] = []
    for row in rows:
        pid = str(row._mapping["provider_id"])
        items.append(_usage_item_from_mapping(row._mapping, runtime_scopes=runtime_scopes_map.get(pid, [])))
    return window_start, window_end, items


async def list_tenant_provider_quota_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime, list[dict[str, object]]]:
    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    window_start, window_end = provider_usage_window(now=now)
    usage_rows = await _provider_usage_rollups(
        db,
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
    )
    usage_provider_ids = [str(row._mapping["provider_id"]) for row in usage_rows]
    runtime_scopes_map = await _load_catalog_runtime_scopes(db, usage_provider_ids)
    usage_items: list[dict[str, object]] = []
    for row in usage_rows:
        pid = str(row._mapping["provider_id"])
        usage_items.append(_usage_item_from_mapping(row._mapping, runtime_scopes=runtime_scopes_map.get(pid, [])))
    usage_by_provider = {str(item["provider_id"]): item for item in usage_items}
    policy_rows = (
        await db.execute(
            select(ProviderQuotaPolicyRow, ProviderCatalogRow)
            .join(
                ProviderCatalogRow,
                ProviderCatalogRow.provider_id == ProviderQuotaPolicyRow.provider_id,
            )
            .where(ProviderQuotaPolicyRow.tenant_id == tenant_id)
            .order_by(ProviderQuotaPolicyRow.provider_id.asc(), ProviderQuotaPolicyRow.metric.asc())
        )
    ).all()
    grouped: dict[str, dict[str, object]] = {}
    for policy_row, catalog_row in policy_rows:
        usage = usage_by_provider.get(policy_row.provider_id)
        used_24h = _usage_value_for_metric(usage=usage, metric=policy_row.metric)
        remaining_24h = max(float(policy_row.limit_per_day) - used_24h, 0.0)
        if policy_row.limit_per_day <= 0:
            status = "blocked"
            percent_used = 0.0 if used_24h <= 0 else 100.0
            soft_limit_reached = False
            hard_limit_reached = True
        else:
            percent_used = min((used_24h / float(policy_row.limit_per_day)) * 100.0, 100.0)
            hard_limit_reached = used_24h >= float(policy_row.limit_per_day)
            soft_limit_reached = percent_used >= float(policy_row.soft_limit_pct)
            if hard_limit_reached:
                status = "exceeded"
            elif soft_limit_reached:
                status = "watch"
            else:
                status = "healthy"
        provider_summary = grouped.setdefault(
            policy_row.provider_id,
            {
                "provider_id": policy_row.provider_id,
                "vendor": catalog_row.vendor,
                "model": catalog_row.model,
                "capability": catalog_row.capability,
                "metrics": [],
            },
        )
        metrics_list = provider_summary["metrics"]
        if not isinstance(metrics_list, list):
            raise RuntimeError("provider quota summary metrics container must be a list")
        metrics_list.append(
            {
                "metric": policy_row.metric,
                "limit_per_day": int(policy_row.limit_per_day),
                "used_24h": used_24h,
                "remaining_24h": remaining_24h,
                "soft_limit_pct": int(policy_row.soft_limit_pct),
                "percent_used": percent_used,
                "status": status,
                "soft_limit_reached": soft_limit_reached,
                "hard_limit_reached": hard_limit_reached,
            }
        )
    return window_start, window_end, list(grouped.values())


async def check_provider_quota_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    provider_id: str,
    runtime_scope: str,
    capability: str,
    estimated_usage: dict[str, int | float] | None = None,
) -> ProviderQuotaCheckResult:
    # TOCTOU note: this is an optimistic preflight, not an atomic gate. Between the
    # usage read and the actual run/request creation, another concurrent request from the
    # same tenant can pass the same check. This is intentional — the overhead of a
    # SELECT FOR UPDATE or Redis INCR/EXPIRE is not warranted at current traffic levels.
    # The threshold should be set conservatively enough to absorb burst over-commit.
    provider_id = provider_id.strip()
    if not provider_id:
        raise ValueError("provider_id must not be blank")

    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    catalog_row = await db.get(ProviderCatalogRow, provider_id)
    if catalog_row is None:
        raise ValueError(f"Unknown provider_id: {provider_id}")
    if capability != catalog_row.capability:
        raise ValueError(
            f"Capability mismatch for provider_id {provider_id}: expected {catalog_row.capability}, got {capability}"
        )
    if runtime_scope not in set(catalog_row.runtime_scopes or []):
        raise ValueError(
            f"Runtime scope mismatch for provider_id {provider_id}: {runtime_scope} not in {catalog_row.runtime_scopes}"
        )

    normalized_estimated_usage = _normalize_estimated_usage(estimated_usage)
    window_start, window_end = provider_usage_window()
    usage_rows = await _provider_usage_rollups(
        db,
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
    )
    usage_mapping = next(
        (
            _usage_item_from_mapping(
                row._mapping,
                runtime_scopes=list(catalog_row.runtime_scopes or []),
            )
            for row in usage_rows
            if str(row._mapping["provider_id"]) == provider_id
        ),
        None,
    )
    policy_rows = (
        await db.execute(
            select(ProviderQuotaPolicyRow)
            .where(
                ProviderQuotaPolicyRow.tenant_id == tenant_id,
                ProviderQuotaPolicyRow.provider_id == provider_id,
            )
            .order_by(ProviderQuotaPolicyRow.metric.asc())
        )
    ).scalars().all()

    decisions: list[ProviderQuotaDecision] = []
    blocked = False
    warning = False
    for policy_row in policy_rows:
        used_24h = _usage_value_for_metric(usage=usage_mapping, metric=policy_row.metric)
        estimated_needed = normalized_estimated_usage.get(policy_row.metric, 0.0)
        projected_24h = used_24h + estimated_needed
        limit_per_day = float(policy_row.limit_per_day)
        if limit_per_day <= 0:
            status = "blocked"
            soft_limit_reached = False
            hard_limit_reached = True
        else:
            percent_used = min((projected_24h / limit_per_day) * 100.0, 100.0)
            hard_limit_reached = projected_24h >= limit_per_day
            soft_limit_reached = percent_used >= float(policy_row.soft_limit_pct)
            if hard_limit_reached:
                status = "exceeded"
            elif soft_limit_reached:
                status = "watch"
            else:
                status = "healthy"
        decisions.append(
            ProviderQuotaDecision(
                metric=policy_row.metric,
                limit_per_day=limit_per_day,
                used_24h=used_24h,
                estimated_needed=estimated_needed,
                projected_24h=projected_24h,
                soft_limit_pct=int(policy_row.soft_limit_pct),
                status=status,
                soft_limit_reached=soft_limit_reached,
                hard_limit_reached=hard_limit_reached,
            )
        )
        blocked = blocked or hard_limit_reached
        warning = warning or soft_limit_reached

    return ProviderQuotaCheckResult(
        provider_id=provider_id,
        capability=capability,
        runtime_scope=runtime_scope,
        decisions=tuple(decisions),
        blocked=blocked,
        # warning is independent of blocked: a provider can be both hard-blocked on one
        # metric and soft-limited on another. Callers that only act on blocking still get
        # the full picture for logging/alerting.
        warning=warning,
    )


async def assert_provider_quota_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    provider_id: str,
    runtime_scope: str,
    capability: str,
    source: str,
    estimated_usage: dict[str, int | float] | None = None,
) -> ProviderQuotaCheckResult:
    result = await check_provider_quota_available(
        db,
        tenant_id=tenant_id,
        provider_id=provider_id,
        runtime_scope=runtime_scope,
        capability=capability,
        estimated_usage=estimated_usage,
    )
    if not result.decisions:
        # No policy rows configured for this provider — quota check is a no-op.
        metrics.PROVIDER_QUOTA_DECISIONS_TOTAL.labels(
            outcome="bypass",
            runtime_scope=runtime_scope,
            capability=capability,
            source=source,
        ).inc()
        return result

    outcome = "blocked" if result.blocked else "soft_limit" if result.warning else "allowed"
    metrics.PROVIDER_QUOTA_DECISIONS_TOTAL.labels(
        outcome=outcome,
        runtime_scope=runtime_scope,
        capability=capability,
        source=source,
    ).inc()
    decision_payload = [
        {
            "metric": item.metric,
            "used_24h": item.used_24h,
            "estimated_needed": item.estimated_needed,
            "projected_24h": item.projected_24h,
            "limit_per_day": item.limit_per_day,
            "soft_limit_pct": item.soft_limit_pct,
            "status": item.status,
        }
        for item in result.decisions
    ]
    if result.blocked:
        blocking = next(item for item in result.decisions if item.hard_limit_reached)
        logger.warning(
            "provider.quota.blocked",
            extra={
                "tenant_id": tenant_id,
                "provider_id": provider_id,
                "runtime_scope": runtime_scope,
                "capability": capability,
                "source": source,
                "decisions": decision_payload,
            },
        )
        raise ApiProblem(
            status=429,
            error_code=PROVIDER_QUOTA_EXCEEDED,
            detail=(
                f"Provider quota exceeded for {provider_id} ({blocking.metric}): "
                f"limit={blocking.limit_per_day:g}, used_24h={blocking.used_24h:g}, "
                f"estimated={blocking.estimated_needed:g}"
            ),
        )
    if result.warning:
        logger.info(
            "provider.quota.soft_limit",
            extra={
                "tenant_id": tenant_id,
                "provider_id": provider_id,
                "runtime_scope": runtime_scope,
                "capability": capability,
                "source": source,
                "decisions": decision_payload,
            },
        )
    return result


async def record_provider_usage(
    db: AsyncSession,
    *,
    tenant_id: str,
    provider_id: str,
    usage_key: str,
    runtime_scope: str,
    capability: str,
    run_id: str | None = None,
    eval_run_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    audio_seconds: float = 0.0,
    characters: int = 0,
    sip_minutes: float = 0.0,
    request_count: int = 1,
    source: str,
) -> str:
    provider_id = provider_id.strip()
    if not provider_id:
        raise ValueError("provider_id must not be blank")
    usage_key = usage_key.strip()
    if not usage_key:
        raise ValueError("usage_key must not be blank")

    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    catalog_row = await db.get(ProviderCatalogRow, provider_id)
    if catalog_row is None:
        raise ValueError(f"Unknown provider_id: {provider_id}")
    if capability != catalog_row.capability:
        raise ValueError(
            f"Capability mismatch for provider_id {provider_id}: expected {catalog_row.capability}, got {capability}"
        )
    if runtime_scope not in set(catalog_row.runtime_scopes or []):
        raise ValueError(
            f"Runtime scope mismatch for provider_id {provider_id}: {runtime_scope} not in {catalog_row.runtime_scopes}"
        )

    recorded_at = datetime.now(UTC)
    calculated_cost_microcents = _cost_from_units(
        catalog_row=catalog_row,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        audio_seconds=audio_seconds,
        characters=characters,
        sip_minutes=sip_minutes,
        request_count=request_count,
    )
    # Optimistic insert first — safe under concurrent writes via savepoint.
    ledger_id = f"provusage_{uuid4().hex}"
    try:
        async with db.begin_nested():
            db.add(
                ProviderUsageLedgerRow(
                    ledger_id=ledger_id,
                    usage_key=usage_key,
                    tenant_id=tenant_id,
                    provider_id=provider_id,
                    runtime_scope=runtime_scope,
                    capability=capability,
                    run_id=run_id,
                    eval_run_id=eval_run_id,
                    input_tokens=max(0, int(input_tokens)),
                    output_tokens=max(0, int(output_tokens)),
                    audio_seconds=max(0.0, float(audio_seconds)),
                    characters=max(0, int(characters)),
                    sip_minutes=max(0.0, float(sip_minutes)),
                    request_count=max(0, int(request_count)),
                    calculated_cost_microcents=calculated_cost_microcents,
                    recorded_at=recorded_at,
                )
            )
    except IntegrityError:
        # Idempotent retry or concurrent insert — fetch and update.
        existing = (
            await db.execute(
                select(ProviderUsageLedgerRow).where(ProviderUsageLedgerRow.usage_key == usage_key)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.provider_id != provider_id or existing.tenant_id != tenant_id:
            raise ValueError("usage_key collision against different provider or tenant")
        existing.runtime_scope = runtime_scope
        existing.capability = capability
        # Preserve existing run/eval association if new value is absent.
        if run_id is not None:
            existing.run_id = run_id
        if eval_run_id is not None:
            existing.eval_run_id = eval_run_id
        existing.input_tokens = max(0, int(input_tokens))
        existing.output_tokens = max(0, int(output_tokens))
        existing.audio_seconds = max(0.0, float(audio_seconds))
        existing.characters = max(0, int(characters))
        existing.sip_minutes = max(0.0, float(sip_minutes))
        existing.request_count = max(0, int(request_count))
        existing.calculated_cost_microcents = calculated_cost_microcents
        existing.recorded_at = recorded_at
        await db.flush()
        ledger_id = existing.ledger_id
    metrics.PROVIDER_USAGE_LEDGER_WRITES_TOTAL.labels(
        outcome="success",
        runtime_scope=runtime_scope,
        capability=capability,
        source=source,
    ).inc()
    logger.info(
        "provider.usage.recorded",
        extra={
            "ledger_id": ledger_id,
            "tenant_id": tenant_id,
            "provider_id": provider_id,
            "runtime_scope": runtime_scope,
            "capability": capability,
            "run_id": run_id,
            "eval_run_id": eval_run_id,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "audio_seconds": float(audio_seconds),
            "characters": int(characters),
            "sip_minutes": float(sip_minutes),
            "request_count": int(request_count),
            "calculated_cost_microcents": calculated_cost_microcents,
            "source": source,
        },
    )
    return ledger_id


def observe_provider_usage_write_failure(
    *,
    runtime_scope: str,
    capability: str,
    source: str,
) -> None:
    metrics.PROVIDER_USAGE_LEDGER_WRITES_TOTAL.labels(
        outcome="error",
        runtime_scope=runtime_scope,
        capability=capability,
        source=source,
    ).inc()
