from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_scenarios import (
    STTProviderDisabledError,
    STTProviderUnsupportedError,
    SpeechCapabilities,
    build_speech_capabilities,
    parse_stt_config,
    stt_provider_enabled,
)

from .config import settings
from .exceptions import (
    ApiProblem,
    STT_PROVIDER_DISABLED,
    STT_PROVIDER_UNCONFIGURED,
    STT_PROVIDER_UNSUPPORTED,
)
from .providers.service import resolve_tenant_provider_state
from .tts_provider import provider_available

_SUPPORTED_STT_PROVIDERS = frozenset({"deepgram", "azure"})


class STTProviderUnconfiguredError(ValueError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"STT provider is not configured: {provider}")
        self.provider = provider


def _provider_feature_enabled(
    provider: str,
    *,
    feature_stt_provider_deepgram_enabled: bool | None = None,
    feature_stt_provider_azure_enabled: bool | None = None,
) -> bool:
    return stt_provider_enabled(
        provider,
        feature_stt_provider_deepgram_enabled=(
            settings.feature_stt_provider_deepgram_enabled
            if feature_stt_provider_deepgram_enabled is None
            else feature_stt_provider_deepgram_enabled
        ),
        feature_stt_provider_azure_enabled=(
            settings.feature_stt_provider_azure_enabled
            if feature_stt_provider_azure_enabled is None
            else feature_stt_provider_azure_enabled
        ),
    )


def provider_stt_available(
    provider: str,
    *,
    feature_stt_provider_deepgram_enabled: bool | None = None,
    feature_stt_provider_azure_enabled: bool | None = None,
) -> bool:
    normalized = provider.strip().lower()
    enabled = _provider_feature_enabled(
        normalized,
        feature_stt_provider_deepgram_enabled=feature_stt_provider_deepgram_enabled,
        feature_stt_provider_azure_enabled=feature_stt_provider_azure_enabled,
    )
    return enabled


def build_api_speech_capabilities(
    *,
    feature_tts_provider_openai_enabled: bool | None = None,
    feature_tts_provider_elevenlabs_enabled: bool | None = None,
    feature_stt_provider_deepgram_enabled: bool | None = None,
    feature_stt_provider_azure_enabled: bool | None = None,
) -> SpeechCapabilities:
    return build_speech_capabilities(
        feature_tts_provider_openai_enabled=provider_available(
            "openai",
            feature_tts_provider_openai_enabled=feature_tts_provider_openai_enabled,
            feature_tts_provider_elevenlabs_enabled=feature_tts_provider_elevenlabs_enabled,
        ),
        feature_tts_provider_elevenlabs_enabled=provider_available(
            "elevenlabs",
            feature_tts_provider_openai_enabled=feature_tts_provider_openai_enabled,
            feature_tts_provider_elevenlabs_enabled=feature_tts_provider_elevenlabs_enabled,
        ),
        feature_stt_provider_deepgram_enabled=provider_stt_available(
            "deepgram",
            feature_stt_provider_deepgram_enabled=feature_stt_provider_deepgram_enabled,
        ),
        feature_stt_provider_azure_enabled=provider_stt_available(
            "azure",
            feature_stt_provider_azure_enabled=feature_stt_provider_azure_enabled,
        ),
    )


def _provider_resolution_problem(exc: Exception, *, status_code: int) -> ApiProblem:
    if isinstance(exc, STTProviderDisabledError):
        return ApiProblem(
            status=status_code,
            error_code=STT_PROVIDER_DISABLED,
            detail=f"STT provider disabled: {exc.provider}",
        )
    if isinstance(exc, STTProviderUnsupportedError):
        return ApiProblem(
            status=status_code,
            error_code=STT_PROVIDER_UNSUPPORTED,
            detail=f"STT provider currently unsupported: {exc.provider}",
        )
    if isinstance(exc, STTProviderUnconfiguredError):
        return ApiProblem(
            status=status_code,
            error_code=STT_PROVIDER_UNCONFIGURED,
            detail=f"STT provider not configured: {exc.provider}",
        )
    raise TypeError(f"Unsupported provider resolution error type: {type(exc).__name__}")


async def _resolve_tenant_stt_config(
    db: AsyncSession,
    *,
    tenant_id: str,
    stt_provider: str,
    stt_model: str,
    runtime_scope: str,
):
    parsed = parse_stt_config(stt_provider, stt_model)
    if parsed.provider not in _SUPPORTED_STT_PROVIDERS:
        raise STTProviderUnsupportedError(parsed.provider)

    resolved = await resolve_tenant_provider_state(
        db,
        tenant_id=tenant_id,
        capability="stt",
        vendor=parsed.provider,
        runtime_scope=runtime_scope,
    )
    availability_status = str(resolved["availability_status"])
    if bool(resolved["available"]):
        return parsed
    if availability_status == "unsupported":
        raise STTProviderUnsupportedError(parsed.provider)
    if availability_status in {"unconfigured", "pending_validation", "invalid_credential"}:
        raise STTProviderUnconfiguredError(parsed.provider)
    raise STTProviderDisabledError(parsed.provider)


async def assert_tenant_stt_config_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    stt_provider: str,
    stt_model: str,
    status_code: int,
    runtime_scope: str = "agent",
) -> None:
    try:
        await _resolve_tenant_stt_config(
            db,
            tenant_id=tenant_id,
            stt_provider=stt_provider,
            stt_model=stt_model,
            runtime_scope=runtime_scope,
        )
    except (
        STTProviderDisabledError,
        STTProviderUnsupportedError,
        STTProviderUnconfiguredError,
    ) as exc:
        raise _provider_resolution_problem(exc, status_code=status_code) from exc
