from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PlatformSettingsRow
from .quota_service import DEFAULT_TENANT_QUOTAS, TenantQuotas, sanitize_quota_config

_PLATFORM_FEATURE_FLAG_ALLOWLIST = frozenset(
    {
        "tts_cache_enabled",
        "feature_packs_enabled",
        "feature_destinations_enabled",
        "feature_ai_scenarios_enabled",
        "feature_tts_provider_openai_enabled",
        "feature_tts_provider_elevenlabs_enabled",
        "feature_stt_provider_deepgram_enabled",
        "feature_stt_provider_azure_enabled",
        "run_dispatch_require_harness_healthy",
    }
)


async def get_or_create_platform_settings(db: AsyncSession) -> PlatformSettingsRow:
    row = await db.get(PlatformSettingsRow, "default")
    if row is not None:
        return row
    row = PlatformSettingsRow(
        singleton_id="default",
        feature_flags={},
        quota_defaults={},
    )
    db.add(row)
    await db.flush()
    return row


def sanitize_platform_feature_flags(config: dict[str, object] | None) -> dict[str, bool | int | float]:
    out: dict[str, bool | int | float] = {}
    if config is None:
        return out
    if not isinstance(config, dict):
        raise ValueError("feature_flags must be an object")
    unknown = sorted(set(config) - _PLATFORM_FEATURE_FLAG_ALLOWLIST)
    if unknown:
        raise ValueError(f"Unsupported platform feature flag keys: {unknown}")
    for key, value in config.items():
        if isinstance(value, bool):
            out[key] = value
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
            continue
        raise ValueError(f"Platform feature flag '{key}' must be a boolean or number")
    return out


def platform_feature_flag_defaults() -> dict[str, bool]:
    return {
        "tts_cache_enabled": settings.tts_cache_enabled,
        "feature_packs_enabled": settings.feature_packs_enabled,
        "feature_destinations_enabled": settings.feature_destinations_enabled,
        "feature_ai_scenarios_enabled": settings.feature_ai_scenarios_enabled,
        "feature_tts_provider_openai_enabled": settings.feature_tts_provider_openai_enabled,
        "feature_tts_provider_elevenlabs_enabled": settings.feature_tts_provider_elevenlabs_enabled,
        "feature_stt_provider_deepgram_enabled": settings.feature_stt_provider_deepgram_enabled,
        "feature_stt_provider_azure_enabled": settings.feature_stt_provider_azure_enabled,
        "run_dispatch_require_harness_healthy": settings.run_dispatch_require_harness_healthy,
    }


def effective_platform_feature_flags(row: PlatformSettingsRow | None) -> dict[str, bool]:
    base = platform_feature_flag_defaults()
    overrides = sanitize_platform_feature_flags(dict(row.feature_flags or {})) if row is not None else {}
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, bool):
            merged[key] = value
    return merged


def effective_platform_quota_defaults(row: PlatformSettingsRow | None) -> TenantQuotas:
    overrides = sanitize_quota_config(dict(row.quota_defaults or {})) if row is not None else {}
    payload = {**DEFAULT_TENANT_QUOTAS.__dict__, **overrides}
    return TenantQuotas(**payload)
