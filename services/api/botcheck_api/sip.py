from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass

import aioboto3
import httpx

from .config import Settings


@dataclass(frozen=True)
class SIPCredentials:
    trunk_id: str
    auth_username: str
    auth_password: str


@dataclass(frozen=True)
class _CachedCredentials:
    creds: SIPCredentials
    expires_at: float


_CREDENTIALS_CACHE: dict[str, _CachedCredentials] = {}
_CACHE_LOCK = asyncio.Lock()


def clear_sip_credentials_cache() -> None:
    _CREDENTIALS_CACHE.clear()


async def load_sip_credentials(settings: Settings) -> SIPCredentials:
    provider = settings.sip_secret_provider.strip().lower()
    if provider == "env":
        if settings.is_production and not settings.allow_env_sip_secrets_in_production:
            raise RuntimeError(
                "SIP env secrets are disabled in production. Configure "
                "SIP_SECRET_PROVIDER=aws_secrets_manager|vault."
            )
        return _from_env(settings)
    if provider not in {"aws_secrets_manager", "vault"}:
        raise RuntimeError(f"Unsupported SIP secret provider: {settings.sip_secret_provider}")

    cache_key = _build_cache_key(settings, provider)
    now = time.monotonic()
    cached = _CREDENTIALS_CACHE.get(cache_key)
    if cached and cached.expires_at > now:
        return cached.creds

    async with _CACHE_LOCK:
        cached = _CREDENTIALS_CACHE.get(cache_key)
        now = time.monotonic()
        if cached and cached.expires_at > now:
            return cached.creds

        if provider == "aws_secrets_manager":
            creds = await _from_aws_secrets_manager(settings)
        else:
            creds = await _from_vault(settings)

        ttl = int(settings.sip_secret_cache_ttl_s)
        if ttl > 0:
            _CREDENTIALS_CACHE[cache_key] = _CachedCredentials(
                creds=creds,
                expires_at=now + ttl,
            )
        return creds


def _build_cache_key(settings: Settings, provider: str) -> str:
    ref = settings.sip_secret_ref or ""
    return "|".join(
        [
            provider,
            ref,
            settings.sip_secret_region,
            settings.vault_addr or "",
            settings.vault_namespace or "",
            str(settings.vault_kv_version),
        ]
    )


def _parse_payload_to_credentials(payload: dict[str, object]) -> SIPCredentials:
    def _field(*names: str) -> str:
        for name in names:
            value = payload.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    creds = SIPCredentials(
        trunk_id=_field("sip_trunk_id", "trunk_id"),
        auth_username=_field("sip_auth_username", "auth_username", "username"),
        auth_password=_field("sip_auth_password", "auth_password", "password"),
    )
    _validate_credentials(creds)
    return creds


def _parse_json_payload(raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SIP secret payload must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("SIP secret payload must be a JSON object")
    return parsed


async def _fetch_aws_secret_json(settings: Settings) -> str:
    session = aioboto3.Session()
    async with session.client(
        "secretsmanager",
        region_name=settings.sip_secret_region,
    ) as client:
        resp = await client.get_secret_value(SecretId=settings.sip_secret_ref)

    raw = resp.get("SecretString")
    if isinstance(raw, str) and raw:
        return raw

    secret_binary = resp.get("SecretBinary")
    if isinstance(secret_binary, str) and secret_binary:
        return base64.b64decode(secret_binary).decode("utf-8")
    if isinstance(secret_binary, (bytes, bytearray)) and secret_binary:
        return bytes(secret_binary).decode("utf-8")
    raise RuntimeError("AWS secret has no SecretString or SecretBinary payload")


async def _fetch_vault_secret(settings: Settings) -> dict[str, object]:
    if not settings.vault_addr:
        raise RuntimeError("vault_addr must be set for vault provider")
    if not settings.vault_token:
        raise RuntimeError("vault_token must be set for vault provider")

    url = f"{settings.vault_addr.rstrip('/')}/v1/{settings.sip_secret_ref.lstrip('/')}"
    headers = {"X-Vault-Token": settings.vault_token}
    if settings.vault_namespace:
        headers["X-Vault-Namespace"] = settings.vault_namespace

    timeout = max(0.1, float(settings.sip_secret_timeout_s))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Vault secret fetch failed ({resp.status_code}): {resp.text}"
            )
        body = resp.json()

    if not isinstance(body, dict):
        raise RuntimeError("Vault response must be a JSON object")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Vault response missing object field: data")
    if settings.vault_kv_version == 2:
        nested = data.get("data")
        if not isinstance(nested, dict):
            raise RuntimeError("Vault KV v2 response missing object field: data.data")
        return nested
    return data


async def _from_aws_secrets_manager(settings: Settings) -> SIPCredentials:
    if not settings.sip_secret_ref:
        raise RuntimeError("sip_secret_ref must be set for aws_secrets_manager provider")

    raw = await _fetch_aws_secret_json(settings)
    payload = _parse_json_payload(raw)
    return _parse_payload_to_credentials(payload)


async def _from_vault(settings: Settings) -> SIPCredentials:
    if not settings.sip_secret_ref:
        raise RuntimeError("sip_secret_ref must be set for vault provider")
    payload = await _fetch_vault_secret(settings)
    return _parse_payload_to_credentials(payload)


def _from_env(settings: Settings) -> SIPCredentials:
    creds = SIPCredentials(
        trunk_id=settings.sip_trunk_id.strip(),
        auth_username=settings.sip_auth_username.strip(),
        auth_password=settings.sip_auth_password.strip(),
    )
    _validate_credentials(creds)
    return creds


def _validate_credentials(creds: SIPCredentials) -> None:
    if not creds.trunk_id:
        raise RuntimeError("Missing SIP trunk id")
    if not creds.auth_username:
        raise RuntimeError("Missing SIP auth username")
    if not creds.auth_password:
        raise RuntimeError("Missing SIP auth password")
