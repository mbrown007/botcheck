"""Schedule cron/timezone utilities."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, CroniterBadDateError, croniter


def normalize_timezone(value: str | None, *, default_timezone: str) -> str:
    candidate = (value or default_timezone).strip()
    if not candidate:
        raise ValueError("timezone must not be empty")
    try:
        ZoneInfo(candidate)
    except Exception as exc:
        raise ValueError(f"invalid timezone: {candidate}") from exc
    return candidate


def normalize_cron_expr(value: str) -> str:
    expr = value.strip()
    if not expr:
        raise ValueError("cron_expr must not be empty")
    try:
        croniter(expr, datetime.now(UTC))
    except (CroniterBadCronError, CroniterBadDateError, ValueError) as exc:
        raise ValueError(f"invalid cron_expr: {expr}") from exc
    return expr


def compute_next_run_at(
    *,
    cron_expr: str,
    timezone: str,
    now: datetime | None = None,
) -> datetime:
    base_utc = now or datetime.now(UTC)
    if base_utc.tzinfo is None:
        base_utc = base_utc.replace(tzinfo=UTC)
    tz = ZoneInfo(timezone)
    base_local = base_utc.astimezone(tz)
    try:
        itr = croniter(cron_expr, base_local)
        next_local = itr.get_next(datetime)
    except (CroniterBadCronError, CroniterBadDateError, ValueError) as exc:
        raise ValueError(f"failed to compute next run for cron_expr: {cron_expr}") from exc
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=tz)
    return next_local.astimezone(UTC)


def compute_next_run_occurrences(
    *,
    cron_expr: str,
    timezone: str,
    count: int = 5,
    now: datetime | None = None,
) -> list[datetime]:
    if count < 1:
        raise ValueError("count must be >= 1")

    base_utc = now or datetime.now(UTC)
    if base_utc.tzinfo is None:
        base_utc = base_utc.replace(tzinfo=UTC)
    tz = ZoneInfo(timezone)
    base_local = base_utc.astimezone(tz)

    out: list[datetime] = []
    try:
        itr = croniter(cron_expr, base_local)
        for _ in range(count):
            next_local = itr.get_next(datetime)
            if next_local.tzinfo is None:
                next_local = next_local.replace(tzinfo=tz)
            out.append(next_local.astimezone(UTC))
    except (CroniterBadCronError, CroniterBadDateError, ValueError) as exc:
        raise ValueError(f"failed to compute next runs for cron_expr: {cron_expr}") from exc

    return out
