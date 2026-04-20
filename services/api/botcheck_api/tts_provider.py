from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_scenarios import (
    AsyncCircuitBreaker,
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
    ProviderKeyedRegistry,
    TTSProvider,
    TTSProviderDisabledError,
    TTSProviderUnsupportedError,
    parse_tts_voice,
    tts_provider_enabled,
)

from .config import settings
from .exceptions import (
    ApiProblem,
    TTS_PROVIDER_DISABLED,
    TTS_PROVIDER_UNCONFIGURED,
    TTS_PROVIDER_UNSUPPORTED,
)
from .providers.service import (
    get_valid_platform_provider_secret_fields,
    resolve_tenant_provider_state,
)

_SUPPORTED_TTS_PROVIDERS = frozenset({"openai", "elevenlabs"})


class TTSProviderUnconfiguredError(ValueError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"TTS provider is not configured: {provider}")
        self.provider = provider


_PREVIEW_TTS_BREAKERS = ProviderKeyedRegistry[AsyncCircuitBreaker[bytes]](
    lambda provider: AsyncCircuitBreaker[bytes](
        name=f"api.preview_tts.{provider}",
        failure_threshold=settings.tts_preview_circuit_failure_threshold,
        recovery_timeout_s=settings.tts_preview_circuit_recovery_s,
    )
)


def get_preview_tts_circuit_breaker(provider: str) -> AsyncCircuitBreaker[bytes]:
    return _PREVIEW_TTS_BREAKERS.get(provider)


def reset_preview_tts_breakers(provider: str | None = None) -> None:
    _PREVIEW_TTS_BREAKERS.reset(provider)


def _provider_feature_enabled(
    provider: str,
    *,
    feature_tts_provider_openai_enabled: bool | None = None,
    feature_tts_provider_elevenlabs_enabled: bool | None = None,
) -> bool:
    return tts_provider_enabled(
        provider,
        feature_tts_provider_openai_enabled=(
            settings.feature_tts_provider_openai_enabled
            if feature_tts_provider_openai_enabled is None
            else feature_tts_provider_openai_enabled
        ),
        feature_tts_provider_elevenlabs_enabled=(
            settings.feature_tts_provider_elevenlabs_enabled
            if feature_tts_provider_elevenlabs_enabled is None
            else feature_tts_provider_elevenlabs_enabled
        ),
    )


def provider_available(
    provider: str,
    *,
    feature_tts_provider_openai_enabled: bool | None = None,
    feature_tts_provider_elevenlabs_enabled: bool | None = None,
) -> bool:
    normalized = provider.strip().lower()
    return _provider_feature_enabled(
        normalized,
        feature_tts_provider_openai_enabled=feature_tts_provider_openai_enabled,
        feature_tts_provider_elevenlabs_enabled=feature_tts_provider_elevenlabs_enabled,
    )


def _provider_resolution_problem(exc: Exception, *, status_code: int) -> ApiProblem:
    if isinstance(exc, TTSProviderDisabledError):
        return ApiProblem(
            status=status_code,
            error_code=TTS_PROVIDER_DISABLED,
            detail=f"TTS provider disabled: {exc.provider}",
        )
    if isinstance(exc, TTSProviderUnsupportedError):
        return ApiProblem(
            status=status_code,
            error_code=TTS_PROVIDER_UNSUPPORTED,
            detail=f"TTS provider currently unsupported: {exc.provider}",
        )
    if isinstance(exc, TTSProviderUnconfiguredError):
        return ApiProblem(
            status=status_code,
            error_code=TTS_PROVIDER_UNCONFIGURED,
            detail=f"TTS provider not configured: {exc.provider}",
        )
    raise TypeError(f"Unsupported provider resolution error type: {type(exc).__name__}")


async def _resolve_tenant_tts_voice(
    db: AsyncSession,
    *,
    tenant_id: str,
    tts_voice: str,
    runtime_scope: str,
):
    parsed_voice = parse_tts_voice(tts_voice)
    if parsed_voice.provider not in _SUPPORTED_TTS_PROVIDERS:
        raise TTSProviderUnsupportedError(parsed_voice.provider)

    resolved = await resolve_tenant_provider_state(
        db,
        tenant_id=tenant_id,
        capability="tts",
        vendor=parsed_voice.provider,
        runtime_scope=runtime_scope,
    )
    availability_status = str(resolved["availability_status"])
    if bool(resolved["available"]):
        return parsed_voice, resolved
    if availability_status == "unsupported":
        raise TTSProviderUnsupportedError(parsed_voice.provider)
    if availability_status in {"unconfigured", "pending_validation", "invalid_credential"}:
        raise TTSProviderUnconfiguredError(parsed_voice.provider)
    raise TTSProviderDisabledError(parsed_voice.provider)


async def assert_tenant_tts_voice_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    tts_voice: str,
    status_code: int,
    runtime_scope: str = "agent",
) -> None:
    try:
        await _resolve_tenant_tts_voice(
            db,
            tenant_id=tenant_id,
            tts_voice=tts_voice,
            runtime_scope=runtime_scope,
        )
    except (
        TTSProviderDisabledError,
        TTSProviderUnsupportedError,
        TTSProviderUnconfiguredError,
    ) as exc:
        raise _provider_resolution_problem(exc, status_code=status_code) from exc


async def resolve_tenant_preview_tts_provider(
    db: AsyncSession,
    *,
    tenant_id: str,
    tts_voice: str,
) -> TTSProvider:
    parsed_voice, resolved = await _resolve_tenant_tts_voice(
        db,
        tenant_id=tenant_id,
        tts_voice=tts_voice,
        runtime_scope="api",
    )
    provider_id = str(resolved.get("provider_id") or "").strip()
    credential_source = str(resolved.get("credential_source") or "").strip()
    secret_fields = (
        await get_valid_platform_provider_secret_fields(db, provider_id=provider_id)
        if provider_id and credential_source == "db_encrypted"
        else None
    )

    if parsed_voice.provider == "openai":
        api_key = str((secret_fields or {}).get("api_key") or "").strip()
        if not api_key:
            raise TTSProviderUnconfiguredError(parsed_voice.provider)
        provider = OpenAITTSProvider(
            voice_id=parsed_voice.voice,
            model_label=settings.tts_preview_openai_model,
            api_key=api_key,
        )
        setattr(provider, "catalog_provider_id", provider_id)
        return provider

    if parsed_voice.provider == "elevenlabs":
        api_key = str((secret_fields or {}).get("api_key") or "").strip()
        if not api_key:
            raise TTSProviderUnconfiguredError(parsed_voice.provider)
        provider = ElevenLabsTTSProvider(
            voice_id=parsed_voice.voice,
            model_label=settings.tts_preview_elevenlabs_model,
            api_key=api_key,
            output_format=settings.tts_preview_elevenlabs_output_format,
        )
        setattr(provider, "catalog_provider_id", provider_id)
        return provider

    raise TTSProviderUnsupportedError(parsed_voice.provider)


def preview_provider_http_error(exc: Exception) -> Exception:
    if isinstance(
        exc,
        (
            TTSProviderDisabledError,
            TTSProviderUnsupportedError,
            TTSProviderUnconfiguredError,
        ),
    ):
        return _provider_resolution_problem(exc, status_code=503)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    raise TypeError(f"Unsupported preview provider error type: {type(exc).__name__}")
