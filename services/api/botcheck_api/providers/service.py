from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_scenarios import parse_stt_config, parse_tts_voice

from ..auth import tenant_display_name
from ..config import settings
from ..models import (
    PlatformSettingsRow,
    ProviderCatalogRow,
    ProviderCredentialRow,
    TenantProviderAssignmentRow,
    TenantRow,
)

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9._-]+$")


@dataclass(frozen=True)
class ProviderSeed:
    provider_id: str
    vendor: str
    model: str
    capability: str
    runtime_scopes: tuple[str, ...]
    supports_tenant_credentials: bool = False
    supports_platform_credentials: bool = True
    feature_flag: str | None = None
    readiness_mode: str = "env"


PROVIDER_CATALOG_SEED: tuple[ProviderSeed, ...] = (
    ProviderSeed(
        provider_id="openai:gpt-4o-mini-tts",
        vendor="openai",
        model="gpt-4o-mini-tts",
        capability="tts",
        runtime_scopes=("api", "agent", "judge"),
        feature_flag="feature_tts_provider_openai_enabled",
        readiness_mode="openai",
    ),
    ProviderSeed(
        provider_id="elevenlabs:eleven_flash_v2_5",
        vendor="elevenlabs",
        model="eleven_flash_v2_5",
        capability="tts",
        runtime_scopes=("api", "agent", "judge"),
        feature_flag="feature_tts_provider_elevenlabs_enabled",
        readiness_mode="elevenlabs",
    ),
    ProviderSeed(
        provider_id="deepgram:nova-2-general",
        vendor="deepgram",
        model="nova-2-general",
        capability="stt",
        runtime_scopes=("agent",),
        feature_flag="feature_stt_provider_deepgram_enabled",
        readiness_mode="agent_feature_only",
    ),
    ProviderSeed(
        provider_id="azure:azure-speech",
        vendor="azure",
        model="azure-speech",
        capability="stt",
        runtime_scopes=("api", "agent"),
        feature_flag="feature_stt_provider_azure_enabled",
        readiness_mode="azure_speech",
    ),
    ProviderSeed(
        provider_id="anthropic:claude-sonnet-4-6",
        vendor="anthropic",
        model="claude-sonnet-4-6",
        capability="judge",
        runtime_scopes=("judge",),
        readiness_mode="anthropic",
    ),
    ProviderSeed(
        provider_id="anthropic:claude-sonnet-4-5-20251001",
        vendor="anthropic",
        model="claude-sonnet-4-5-20251001",
        capability="llm",
        runtime_scopes=("api",),
        readiness_mode="anthropic",
    ),
    ProviderSeed(
        provider_id="openai:gpt-4o",
        vendor="openai",
        model="gpt-4o",
        capability="judge",
        runtime_scopes=("api",),
        readiness_mode="openai",
    ),
    ProviderSeed(
        provider_id="openai:gpt-4o-mini",
        vendor="openai",
        model="gpt-4o-mini",
        capability="llm",
        runtime_scopes=("api",),
        readiness_mode="openai",
    ),
)


def provider_catalog_seed_by_id() -> dict[str, ProviderSeed]:
    return {seed.provider_id: seed for seed in PROVIDER_CATALOG_SEED}


def _validate_provider_seed(seed: ProviderSeed) -> None:
    if not _PROVIDER_ID_RE.fullmatch(seed.provider_id):
        raise ValueError(f"invalid provider_id seed: {seed.provider_id}")


_logger = __import__("logging").getLogger("botcheck.api.providers")


def _provider_secret_fernet() -> Fernet:
    configured = settings.auth_totp_encryption_key.strip()
    if configured:
        key = configured.encode()
    else:
        _logger.warning(
            "provider.credential.encryption_key_not_configured: "
            "deriving Fernet key from secret_key; set AUTH_TOTP_ENCRYPTION_KEY for production"
        )
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_provider_secret_fields(secret_fields: dict[str, str]) -> str:
    payload = json.dumps(secret_fields, sort_keys=True, separators=(",", ":"))
    return _provider_secret_fernet().encrypt(payload.encode()).decode()


def decrypt_provider_secret_fields(secret_encrypted: str) -> dict[str, str]:
    try:
        decoded = _provider_secret_fernet().decrypt(secret_encrypted.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid provider credential payload") from exc
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Provider credential payload must decode to an object")
    normalized: dict[str, str] = {}
    for key, raw in payload.items():
        normalized[str(key)] = str(raw)
    return normalized


def normalize_provider_secret_fields(seed: ProviderSeed, secret_fields: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, raw_value in secret_fields.items():
        candidate_key = str(key).strip()
        candidate_value = str(raw_value).strip()
        if not candidate_key or not candidate_value:
            raise ValueError("Credential fields must not be blank")
        normalized[candidate_key] = candidate_value

    api_key = normalized.get("api_key", "").strip()
    if seed.readiness_mode in {"openai", "elevenlabs", "anthropic", "agent_feature_only"}:
        if not api_key:
            raise ValueError("secret_fields.api_key is required")
        return {"api_key": api_key}

    if seed.readiness_mode == "azure_speech":
        region = normalized.get("region", "").strip()
        endpoint = normalized.get("endpoint", "").strip()
        if not api_key:
            raise ValueError("secret_fields.api_key is required")
        if not region and not endpoint:
            raise ValueError("secret_fields.region or secret_fields.endpoint is required")
        out = {"api_key": api_key}
        if region:
            out["region"] = region
        if endpoint:
            out["endpoint"] = endpoint
        return out

    raise ValueError(f"Unsupported provider readiness mode: {seed.readiness_mode}")


# Vendor-level normalization for user-created providers that have no seed entry.
# All common API vendors need only an api_key; azure additionally needs region/endpoint.
_VENDOR_API_KEY_ONLY = frozenset(
    {"openai", "anthropic", "elevenlabs", "deepgram", "mistral", "cohere", "groq", "google"}
)


def normalize_provider_secret_fields_by_vendor(
    vendor: str,
    secret_fields: dict[str, str],
) -> dict[str, str]:
    """Normalize secret fields for a user-created provider by vendor heuristic."""
    normalized: dict[str, str] = {}
    for key, raw_value in secret_fields.items():
        candidate_key = str(key).strip()
        candidate_value = str(raw_value).strip()
        if not candidate_key or not candidate_value:
            raise ValueError("Credential fields must not be blank")
        normalized[candidate_key] = candidate_value

    api_key = normalized.get("api_key", "").strip()
    vendor_lower = vendor.strip().lower()

    if vendor_lower == "azure":
        region = normalized.get("region", "").strip()
        endpoint = normalized.get("endpoint", "").strip()
        if not api_key:
            raise ValueError("secret_fields.api_key is required")
        if not region and not endpoint:
            raise ValueError("secret_fields.region or secret_fields.endpoint is required")
        out: dict[str, str] = {"api_key": api_key}
        if region:
            out["region"] = region
        if endpoint:
            out["endpoint"] = endpoint
        return out

    # Default: require api_key for all other vendors (including known and unknown vendors)
    if not api_key:
        raise ValueError("secret_fields.api_key is required")
    return {"api_key": api_key}


def platform_credential_status(row: ProviderCredentialRow | None) -> str:
    if row is None:
        return "none"
    if row.validation_error:
        return "invalid"
    if row.validated_at is not None:
        return "valid"
    return "pending"


def platform_credential_payload(row: ProviderCredentialRow | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "credential_source": row.credential_source,
        "validation_status": platform_credential_status(row),
        "validated_at": row.validated_at,
        "validation_error": row.validation_error,
        "updated_at": row.updated_at,
        "has_stored_secret": bool(row.secret_encrypted),
    }


async def get_valid_platform_provider_secret_fields(
    db: AsyncSession,
    *,
    provider_id: str,
) -> dict[str, str] | None:
    row = await get_platform_provider_credential(db, provider_id=provider_id)
    if row is None or platform_credential_status(row) != "valid" or not row.secret_encrypted:
        return None
    try:
        return decrypt_provider_secret_fields(row.secret_encrypted)
    except ValueError:
        return None


def provider_cost_payload(row: ProviderCatalogRow) -> dict[str, int | None]:
    return {
        "cost_per_input_token_microcents": row.cost_per_input_token_microcents,
        "cost_per_output_token_microcents": row.cost_per_output_token_microcents,
        "cost_per_audio_second_microcents": row.cost_per_audio_second_microcents,
        "cost_per_character_microcents": row.cost_per_character_microcents,
        "cost_per_request_microcents": row.cost_per_request_microcents,
    }


async def get_platform_provider_credential(
    db: AsyncSession,
    *,
    provider_id: str,
) -> ProviderCredentialRow | None:
    return (
        await db.execute(
            select(ProviderCredentialRow).where(
                ProviderCredentialRow.owner_scope == "platform",
                ProviderCredentialRow.tenant_id.is_(None),
                ProviderCredentialRow.provider_id == provider_id,
            )
        )
    ).scalar_one_or_none()


async def get_platform_provider_credentials_by_provider_id(
    db: AsyncSession,
) -> dict[str, ProviderCredentialRow]:
    rows = (
        await db.execute(
            select(ProviderCredentialRow).where(
                ProviderCredentialRow.owner_scope == "platform",
                ProviderCredentialRow.tenant_id.is_(None),
            )
        )
    ).scalars().all()
    return {row.provider_id: row for row in rows}


def provider_seed_env_secret_fields(seed: ProviderSeed) -> dict[str, str] | None:
    if seed.readiness_mode == "openai":
        api_key = str(settings.openai_api_key or "").strip()
        return {"api_key": api_key} if api_key else None
    if seed.readiness_mode == "elevenlabs":
        api_key = str(settings.elevenlabs_api_key or "").strip()
        return {"api_key": api_key} if api_key else None
    if seed.readiness_mode == "anthropic":
        api_key = str(settings.anthropic_api_key or "").strip()
        return {"api_key": api_key} if api_key else None
    if seed.readiness_mode == "azure_speech":
        api_key = str(settings.azure_speech_key or "").strip()
        region = str(settings.azure_speech_region or "").strip()
        endpoint = str(settings.azure_speech_endpoint or "").strip()
        if not api_key or not (region or endpoint):
            return None
        payload = {"api_key": api_key}
        if region:
            payload["region"] = region
        if endpoint:
            payload["endpoint"] = endpoint
        return payload
    if seed.readiness_mode == "agent_feature_only":
        api_key = str(settings.deepgram_api_key or "").strip()
        return {"api_key": api_key} if api_key else None
    _logger.warning(
        "provider.seed.unknown_readiness_mode",
        extra={"provider_id": seed.provider_id, "readiness_mode": seed.readiness_mode},
    )
    return None


def _feature_enabled(seed: ProviderSeed, effective_flags: dict[str, bool]) -> bool:
    if not seed.feature_flag:
        return True
    return bool(effective_flags.get(seed.feature_flag, False))


def resolve_provider_runtime_state(
    seed: ProviderSeed,
    *,
    effective_flags: dict[str, bool],
    platform_credential: ProviderCredentialRow | None = None,
) -> dict[str, object]:
    feature_enabled = _feature_enabled(seed, effective_flags)
    credential_status = platform_credential_status(platform_credential)

    if platform_credential is not None and credential_status == "valid":
        return {
            "available": feature_enabled,
            "availability_status": "available" if feature_enabled else "disabled",
            "configured": True,
            "credential_source": "db_encrypted",
        }
    if platform_credential is not None and credential_status == "pending":
        return {
            "available": False,
            "availability_status": "pending_validation" if feature_enabled else "disabled",
            "configured": True,
            "credential_source": "db_encrypted",
        }
    if platform_credential is not None and credential_status == "invalid":
        return {
            "available": False,
            "availability_status": "invalid_credential" if feature_enabled else "disabled",
            "configured": True,
            "credential_source": "db_encrypted",
        }

    if not feature_enabled:
        return {
            "available": False,
            "availability_status": "disabled",
            "configured": False,
            "credential_source": "none",
        }
    return {
        "available": False,
        "availability_status": "unconfigured",
        "configured": False,
        "credential_source": "none",
    }


async def ensure_provider_registry_seeded(
    db: AsyncSession,
    *,
    tenant_ids: list[str] | None = None,
) -> None:
    existing_catalog = set((await db.execute(select(ProviderCatalogRow.provider_id))).scalars().all())
    for seed in PROVIDER_CATALOG_SEED:
        _validate_provider_seed(seed)
        if seed.provider_id in existing_catalog:
            continue
        db.add(
            ProviderCatalogRow(
                provider_id=seed.provider_id,
                vendor=seed.vendor,
                model=seed.model,
                capability=seed.capability,
                runtime_scopes=list(seed.runtime_scopes),
                supports_tenant_credentials=seed.supports_tenant_credentials,
                supports_platform_credentials=seed.supports_platform_credentials,
            )
        )
    await db.flush()

    if tenant_ids is None:
        tenant_ids = list(
            (
                await db.execute(select(TenantRow.tenant_id).where(TenantRow.deleted_at.is_(None)))
            ).scalars().all()
        )
    else:
        tenant_ids = [tenant_id for tenant_id in tenant_ids if tenant_id]
    if not tenant_ids:
        return

    existing_assignment = (
        await db.execute(select(TenantProviderAssignmentRow.assignment_id).limit(1))
    ).scalar_one_or_none()
    if existing_assignment is not None:
        return

    seed_tenant_id = settings.tenant_id if settings.tenant_id in tenant_ids else tenant_ids[0]
    now = datetime.now(UTC)
    for seed in PROVIDER_CATALOG_SEED:
        db.add(
            TenantProviderAssignmentRow(
                assignment_id=f"provassign_{uuid4().hex}",
                tenant_id=seed_tenant_id,
                provider_id=seed.provider_id,
                enabled=True,
                is_default=False,
                effective_credential_source="env",
                created_at=now,
                updated_at=now,
            )
        )
    await db.flush()


async def _effective_flags_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, bool]:
    from ..admin.platform_settings import effective_platform_feature_flags  # noqa: PLC0415
    from ..admin.service_tenants import merge_tenant_feature_overrides  # noqa: PLC0415
    platform_settings = await db.get(PlatformSettingsRow, "default")
    effective_flags = effective_platform_feature_flags(platform_settings)
    tenant = await db.get(TenantRow, tenant_id)
    overrides = dict(tenant.feature_overrides or {}) if tenant is not None else None
    return merge_tenant_feature_overrides(effective_flags, overrides)


async def list_available_providers_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> list[dict[str, object]]:
    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    effective_flags = await _effective_flags_for_tenant(db, tenant_id=tenant_id)
    platform_credentials = await get_platform_provider_credentials_by_provider_id(db)
    rows = (
        await db.execute(
            select(ProviderCatalogRow, TenantProviderAssignmentRow)
            .join(
                TenantProviderAssignmentRow,
                TenantProviderAssignmentRow.provider_id == ProviderCatalogRow.provider_id,
            )
            .where(
                TenantProviderAssignmentRow.tenant_id == tenant_id,
                TenantProviderAssignmentRow.enabled.is_(True),
            )
            .order_by(
                ProviderCatalogRow.capability.asc(),
                ProviderCatalogRow.vendor.asc(),
                ProviderCatalogRow.model.asc(),
            )
        )
    ).all()

    seed_by_provider_id = provider_catalog_seed_by_id()
    items: list[dict[str, object]] = []
    for catalog_row, _assignment_row in rows:
        seed = seed_by_provider_id.get(catalog_row.provider_id)
        if seed is None:
            continue
        resolved = resolve_provider_runtime_state(
            seed,
            effective_flags=effective_flags,
            platform_credential=platform_credentials.get(catalog_row.provider_id),
        )
        if not bool(resolved["available"]):
            continue
        items.append(
            {
                "provider_id": catalog_row.provider_id,
                "vendor": catalog_row.vendor,
                "model": catalog_row.model,
                "capability": catalog_row.capability,
                "runtime_scopes": list(catalog_row.runtime_scopes or []),
                "credential_source": str(resolved["credential_source"]),
                "configured": bool(resolved["configured"]),
                "availability_status": str(resolved["availability_status"]),
                "supports_tenant_credentials": bool(catalog_row.supports_tenant_credentials),
            }
        )
    return items


async def speech_feature_flags_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, bool]:
    effective_flags = await _effective_flags_for_tenant(db, tenant_id=tenant_id)
    return {
        "feature_tts_provider_openai_enabled": bool(
            effective_flags.get("feature_tts_provider_openai_enabled", False)
        ),
        "feature_tts_provider_elevenlabs_enabled": bool(
            effective_flags.get("feature_tts_provider_elevenlabs_enabled", False)
        ),
        "feature_stt_provider_deepgram_enabled": bool(
            effective_flags.get("feature_stt_provider_deepgram_enabled", False)
        ),
        "feature_stt_provider_azure_enabled": bool(
            effective_flags.get("feature_stt_provider_azure_enabled", False)
        ),
    }


async def resolve_tenant_provider_state(
    db: AsyncSession,
    *,
    tenant_id: str,
    capability: str,
    vendor: str,
    runtime_scope: str,
) -> dict[str, object]:
    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    effective_flags = await _effective_flags_for_tenant(db, tenant_id=tenant_id)
    platform_credentials = await get_platform_provider_credentials_by_provider_id(db)
    rows = (
        await db.execute(
            select(ProviderCatalogRow, TenantProviderAssignmentRow)
            .join(
                TenantProviderAssignmentRow,
                TenantProviderAssignmentRow.provider_id == ProviderCatalogRow.provider_id,
            )
            .where(
                TenantProviderAssignmentRow.tenant_id == tenant_id,
                ProviderCatalogRow.capability == capability,
                ProviderCatalogRow.vendor == vendor,
            )
            .order_by(ProviderCatalogRow.model.asc())
        )
    ).all()

    scoped_rows = [
        (catalog_row, assignment_row)
        for catalog_row, assignment_row in rows
        if runtime_scope in set(catalog_row.runtime_scopes or [])
    ]
    if not scoped_rows:
        return {
            "available": False,
            "availability_status": "unsupported",
            "configured": False,
            "credential_source": "none",
            "provider_id": None,
            "vendor": vendor,
            "model": None,
        }

    enabled_rows = [
        (catalog_row, assignment_row)
        for catalog_row, assignment_row in scoped_rows
        if bool(assignment_row.enabled)
    ]
    if not enabled_rows:
        return {
            "available": False,
            "availability_status": "disabled",
            "configured": False,
            "credential_source": "none",
            "provider_id": scoped_rows[0][0].provider_id,
            "vendor": scoped_rows[0][0].vendor,
            "model": scoped_rows[0][0].model,
        }

    seed_by_provider_id = provider_catalog_seed_by_id()
    first_unavailable: dict[str, object] | None = None
    for catalog_row, _assignment_row in enabled_rows:
        seed = seed_by_provider_id.get(catalog_row.provider_id)
        if seed is None:
            continue
        resolved = resolve_provider_runtime_state(
            seed,
            effective_flags=effective_flags,
            platform_credential=platform_credentials.get(catalog_row.provider_id),
        )
        candidate = {
            "available": bool(resolved["available"]),
            "availability_status": str(resolved["availability_status"]),
            "configured": bool(resolved["configured"]),
            "credential_source": str(resolved["credential_source"]),
            "provider_id": catalog_row.provider_id,
            "vendor": catalog_row.vendor,
            "model": catalog_row.model,
        }
        if bool(candidate["available"]):
            return candidate
        if first_unavailable is None:
            first_unavailable = candidate

    return first_unavailable or {
        "available": False,
        "availability_status": "disabled",
        "configured": False,
        "credential_source": "none",
        "provider_id": enabled_rows[0][0].provider_id,
        "vendor": enabled_rows[0][0].vendor,
        "model": enabled_rows[0][0].model,
    }


async def resolve_tenant_provider_binding_state(
    db: AsyncSession,
    *,
    tenant_id: str,
    capability: str,
    model: str,
    runtime_scope: str,
    vendor: str | None = None,
) -> dict[str, object]:
    await ensure_provider_registry_seeded(db, tenant_ids=[tenant_id])
    effective_flags = await _effective_flags_for_tenant(db, tenant_id=tenant_id)
    platform_credentials = await get_platform_provider_credentials_by_provider_id(db)
    query = (
        select(ProviderCatalogRow, TenantProviderAssignmentRow)
        .join(
            TenantProviderAssignmentRow,
            TenantProviderAssignmentRow.provider_id == ProviderCatalogRow.provider_id,
        )
        .where(
            TenantProviderAssignmentRow.tenant_id == tenant_id,
            ProviderCatalogRow.capability == capability,
            ProviderCatalogRow.model == model,
        )
        .order_by(ProviderCatalogRow.vendor.asc(), ProviderCatalogRow.model.asc())
    )
    if isinstance(vendor, str) and vendor.strip():
        query = query.where(ProviderCatalogRow.vendor == vendor.strip().lower())
    rows = (await db.execute(query)).all()

    scoped_rows = [
        (catalog_row, assignment_row)
        for catalog_row, assignment_row in rows
        if runtime_scope in set(catalog_row.runtime_scopes or [])
    ]
    if not scoped_rows:
        return {
            "available": False,
            "availability_status": "unsupported",
            "configured": False,
            "credential_source": "none",
            "provider_id": None,
            "vendor": (vendor or "").strip().lower(),
            "model": model,
        }

    enabled_rows = [
        (catalog_row, assignment_row)
        for catalog_row, assignment_row in scoped_rows
        if bool(assignment_row.enabled)
    ]
    if not enabled_rows:
        return {
            "available": False,
            "availability_status": "disabled",
            "configured": False,
            "credential_source": "none",
            "provider_id": scoped_rows[0][0].provider_id,
            "vendor": scoped_rows[0][0].vendor,
            "model": scoped_rows[0][0].model,
        }

    seed_by_provider_id = provider_catalog_seed_by_id()
    first_unavailable: dict[str, object] | None = None
    for catalog_row, _assignment_row in enabled_rows:
        seed = seed_by_provider_id.get(catalog_row.provider_id)
        if seed is None:
            continue
        resolved = resolve_provider_runtime_state(
            seed,
            effective_flags=effective_flags,
            platform_credential=platform_credentials.get(catalog_row.provider_id),
        )
        candidate = {
            "available": bool(resolved["available"]),
            "availability_status": str(resolved["availability_status"]),
            "configured": bool(resolved["configured"]),
            "credential_source": str(resolved["credential_source"]),
            "provider_id": catalog_row.provider_id,
            "vendor": catalog_row.vendor,
            "model": catalog_row.model,
        }
        if bool(candidate["available"]):
            return candidate
        if first_unavailable is None:
            first_unavailable = candidate

    return first_unavailable or {
        "available": False,
        "availability_status": "disabled",
        "configured": False,
        "credential_source": "none",
        "provider_id": enabled_rows[0][0].provider_id,
        "vendor": enabled_rows[0][0].vendor,
        "model": enabled_rows[0][0].model,
    }


async def build_provider_runtime_context(
    db: AsyncSession,
    *,
    tenant_id: str,
    runtime_scope: str,
    tts_voice: str | None = None,
    stt_provider: str | None = None,
    stt_model: str | None = None,
    provider_bindings: list[dict[str, str | None]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "tenant_id": tenant_id,
        "runtime_scope": runtime_scope,
        "feature_flags": await speech_feature_flags_for_tenant(db, tenant_id=tenant_id),
        "tts": None,
        "stt": None,
        "providers": [],
    }

    if isinstance(tts_voice, str) and tts_voice.strip():
        parsed_voice = parse_tts_voice(tts_voice)
        resolved = await resolve_tenant_provider_state(
            db,
            tenant_id=tenant_id,
            capability="tts",
            vendor=parsed_voice.provider,
            runtime_scope=runtime_scope,
        )
        secret_fields = (
            await get_valid_platform_provider_secret_fields(
                db,
                provider_id=str(resolved.get("provider_id") or "").strip(),
            )
            if str(resolved.get("credential_source") or "").strip() == "db_encrypted"
            and str(resolved.get("provider_id") or "").strip()
            else None
        )
        payload["tts"] = {
            "capability": "tts",
            "vendor": parsed_voice.provider,
            "model": str(resolved.get("model") or parsed_voice.voice),
            "provider_id": resolved.get("provider_id"),
            "credential_source": str(resolved.get("credential_source") or "none"),
            "availability_status": str(resolved.get("availability_status") or "unsupported"),
            "secret_fields": dict(secret_fields or {}),
        }

    effective_stt_provider = str(stt_provider or "").strip()
    effective_stt_model = str(stt_model or "").strip()
    if effective_stt_provider or effective_stt_model:
        parsed_stt = parse_stt_config(effective_stt_provider, effective_stt_model)
        resolved = await resolve_tenant_provider_state(
            db,
            tenant_id=tenant_id,
            capability="stt",
            vendor=parsed_stt.provider,
            runtime_scope=runtime_scope,
        )
        secret_fields = (
            await get_valid_platform_provider_secret_fields(
                db,
                provider_id=str(resolved.get("provider_id") or "").strip(),
            )
            if str(resolved.get("credential_source") or "").strip() == "db_encrypted"
            and str(resolved.get("provider_id") or "").strip()
            else None
        )
        payload["stt"] = {
            "capability": "stt",
            "vendor": parsed_stt.provider,
            "model": str(resolved.get("model") or parsed_stt.model),
            "provider_id": resolved.get("provider_id"),
            "credential_source": str(resolved.get("credential_source") or "none"),
            "availability_status": str(resolved.get("availability_status") or "unsupported"),
            "secret_fields": dict(secret_fields or {}),
        }

    for requested_binding in list(provider_bindings or []):
        capability = str(requested_binding.get("capability") or "").strip().lower()
        model = str(requested_binding.get("model") or "").strip()
        vendor = str(requested_binding.get("vendor") or "").strip().lower()
        if not capability or not model:
            continue
        resolved = await resolve_tenant_provider_binding_state(
            db,
            tenant_id=tenant_id,
            capability=capability,
            model=model,
            vendor=vendor or None,
            runtime_scope=runtime_scope,
        )
        provider_id = str(resolved.get("provider_id") or "").strip()
        secret_fields = (
            await get_valid_platform_provider_secret_fields(db, provider_id=provider_id)
            if str(resolved.get("credential_source") or "").strip() == "db_encrypted"
            and provider_id
            else None
        )
        cast_providers = payload["providers"]
        if not isinstance(cast_providers, list):
            raise TypeError(f"providers payload entry is not a list: {type(cast_providers)}")
        cast_providers.append(
            {
                "capability": capability,
                "vendor": str(resolved.get("vendor") or vendor),
                "model": str(resolved.get("model") or model),
                "provider_id": provider_id or None,
                "credential_source": str(resolved.get("credential_source") or "none"),
                "availability_status": str(resolved.get("availability_status") or "unsupported"),
                "secret_fields": dict(secret_fields or {}),
            }
        )

    return payload


async def list_admin_provider_inventory(db: AsyncSession) -> list[dict[str, object]]:
    await ensure_provider_registry_seeded(db)
    assignment_rows = (
        await db.execute(
            select(TenantProviderAssignmentRow, TenantRow)
            .join(TenantRow, TenantRow.tenant_id == TenantProviderAssignmentRow.tenant_id)
            .where(TenantRow.deleted_at.is_(None))
            .order_by(
                TenantProviderAssignmentRow.updated_at.desc(),
                TenantProviderAssignmentRow.created_at.desc(),
                TenantProviderAssignmentRow.assignment_id.asc(),
            )
        )
    ).all()
    assignments_by_provider: dict[str, dict[str, object]] = {}
    for assignment_row, tenant_row in assignment_rows:
        assignments_by_provider.setdefault(
            assignment_row.provider_id,
            {
                "tenant_id": assignment_row.tenant_id,
                "tenant_display_name": tenant_display_name(tenant_row, tenant_id=tenant_row.tenant_id),
                "enabled": bool(assignment_row.enabled),
            },
        )
    from ..admin.platform_settings import effective_platform_feature_flags  # noqa: PLC0415
    platform_settings = await db.get(PlatformSettingsRow, "default")
    effective_flags = effective_platform_feature_flags(platform_settings)
    platform_credentials = await get_platform_provider_credentials_by_provider_id(db)
    rows = (
        await db.execute(
            select(ProviderCatalogRow).order_by(
                ProviderCatalogRow.capability.asc(),
                ProviderCatalogRow.vendor.asc(),
                ProviderCatalogRow.model.asc(),
            )
        )
    ).scalars().all()

    seed_by_provider_id = provider_catalog_seed_by_id()
    items: list[dict[str, object]] = []
    for row in rows:
        seed = seed_by_provider_id.get(row.provider_id)
        platform_credential = platform_credentials.get(row.provider_id)
        if seed is not None:
            resolved = resolve_provider_runtime_state(
                seed,
                effective_flags=effective_flags,
                platform_credential=platform_credential,
            )
        else:
            # User-created provider: availability is determined solely by credential state.
            cred_status = platform_credential_status(platform_credential)
            configured = platform_credential is not None
            available = configured and cred_status == "valid"
            if not configured:
                status = "no_credential"
            elif cred_status == "valid":
                status = "available"
            elif cred_status == "pending":
                status = "pending_validation"
            else:
                status = "invalid_credential"
            resolved = {
                "available": available,
                "availability_status": status,
                "configured": configured,
                "credential_source": "db_encrypted" if configured else "none",
            }
        items.append(
            {
                "provider_id": row.provider_id,
                "vendor": row.vendor,
                "model": row.model,
                "capability": row.capability,
                "label": row.label,
                "user_created": bool(getattr(row, "user_created", False)),
                "runtime_scopes": list(row.runtime_scopes or []),
                "supports_tenant_credentials": bool(row.supports_tenant_credentials),
                "supports_platform_credentials": bool(row.supports_platform_credentials),
                "credential_source": str(resolved["credential_source"]),
                "configured": bool(resolved["configured"]),
                "available": bool(resolved["available"]),
                "availability_status": str(resolved["availability_status"]),
                "tenant_assignment_count": 1 if row.provider_id in assignments_by_provider else 0,
                "assigned_tenant": assignments_by_provider.get(row.provider_id),
                "cost_metadata": provider_cost_payload(row),
                "platform_credential": platform_credential_payload(platform_credential),
            }
        )
    return items
