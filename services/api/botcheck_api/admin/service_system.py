from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..config import settings
from .platform_settings import (
    effective_platform_feature_flags,
    effective_platform_quota_defaults,
    get_or_create_platform_settings,
    sanitize_platform_feature_flags,
)
from .quota_service import sanitize_quota_config

_REDACT_SUBSTRINGS = (
    "secret",
    "password",
    "token",
    "api_key",
    "encryption_key",
)


async def build_system_health(
    db: AsyncSession,
    *,
    redis_pool: object | None,
) -> dict[str, Any]:
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    livekit_status = "configured"
    if not (
        str(settings.livekit_url or "").strip()
        and str(settings.livekit_api_key or "").strip()
        and str(settings.livekit_api_secret or "").strip()
    ):
        livekit_status = "unconfigured"

    return {
        "database": {"status": db_status},
        "redis": {"status": "ok" if redis_pool is not None else "unavailable"},
        "livekit": {"status": livekit_status},
        "providers": {
            # API-side providers: key must be present on this process.
            "openai": {
                "configured": bool(str(settings.openai_api_key or "").strip()),
                "key_location": "api",
            },
            "elevenlabs": {
                "configured": bool(str(settings.elevenlabs_api_key or "").strip()),
                "key_location": "api",
            },
            # Agent-side providers: key lives in the agent service, not here.
            # The API does not require the key; "configured" reflects API-side
            # presence only and should not be treated as a health warning.
            "deepgram": {
                "configured": bool(str(settings.deepgram_api_key or "").strip()),
                "key_location": "agent",
            },
            "azure": {
                "configured": bool(str(settings.azure_speech_key or "").strip()),
                "key_location": "agent",
            },
        },
        "timestamp": datetime.now(UTC),
    }


def redacted_effective_config() -> dict[str, object]:
    raw = settings.model_dump()
    out: dict[str, object] = {}
    for key, value in raw.items():
        lowered = key.lower()
        if any(part in lowered for part in _REDACT_SUBSTRINGS):
            out[key] = "<redacted>"
            continue
        out[key] = value
    return out


async def get_platform_feature_flags(db: AsyncSession) -> tuple[dict[str, bool], datetime]:
    row = await get_or_create_platform_settings(db)
    return effective_platform_feature_flags(row), row.updated_at


async def patch_platform_feature_flags(
    db: AsyncSession,
    *,
    overrides: dict[str, object],
    actor_id: str,
    actor_tenant_id: str,
) -> tuple[dict[str, bool], datetime]:
    row = await get_or_create_platform_settings(db)
    current = sanitize_platform_feature_flags(dict(row.feature_flags or {}))
    incoming = sanitize_platform_feature_flags(overrides)
    merged = {**current, **incoming}
    row.feature_flags = merged
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.system.feature_flags.update",
        resource_type="platform_settings",
        resource_id=row.singleton_id,
        detail={"feature_flags": merged},
    )
    await db.flush()
    return effective_platform_feature_flags(row), row.updated_at


async def get_platform_quota_defaults(db: AsyncSession) -> tuple[dict[str, int], datetime]:
    row = await get_or_create_platform_settings(db)
    quotas = effective_platform_quota_defaults(row)
    return quotas.__dict__, row.updated_at


async def patch_platform_quota_defaults(
    db: AsyncSession,
    *,
    overrides: dict[str, object],
    actor_id: str,
    actor_tenant_id: str,
) -> tuple[dict[str, int], datetime]:
    row = await get_or_create_platform_settings(db)
    current = sanitize_quota_config(dict(row.quota_defaults or {}))
    incoming = sanitize_quota_config(overrides)
    merged = {**current, **incoming}
    row.quota_defaults = merged
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.system.quotas.update",
        resource_type="platform_settings",
        resource_id=row.singleton_id,
        detail={"quota_defaults": merged},
    )
    await db.flush()
    quotas = effective_platform_quota_defaults(row)
    return quotas.__dict__, row.updated_at
