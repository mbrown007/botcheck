from __future__ import annotations

from typing import Any

from botcheck_scenarios import (
    STTProvider,
    STTProviderDisabledError,
    STTProviderUnsupportedError,
    build_stt_provider,
    parse_stt_config,
    stt_provider_enabled,
)


class STTProviderUnconfiguredError(ValueError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"STT provider is not configured: {provider}")
        self.provider = provider


def resolve_live_stt_provider(
    *,
    stt_provider: str,
    stt_model: str,
    language: str,
    settings_obj: Any,
) -> STTProvider:
    parsed = parse_stt_config(stt_provider, stt_model)

    enabled = stt_provider_enabled(
        parsed.provider,
        feature_stt_provider_deepgram_enabled=bool(
            getattr(settings_obj, "feature_stt_provider_deepgram_enabled", True)
        ),
        feature_stt_provider_azure_enabled=bool(
            getattr(settings_obj, "feature_stt_provider_azure_enabled", False)
        ),
    )

    if parsed.provider not in {"deepgram", "azure"}:
        raise STTProviderUnsupportedError(parsed.provider)

    if not enabled:
        raise STTProviderDisabledError(parsed.provider)

    deepgram_api_key = str(getattr(settings_obj, "deepgram_api_key", "") or "").strip()
    azure_speech_key = str(getattr(settings_obj, "azure_speech_key", "") or "").strip()
    azure_speech_region = str(getattr(settings_obj, "azure_speech_region", "") or "").strip()
    azure_speech_endpoint = str(getattr(settings_obj, "azure_speech_endpoint", "") or "").strip()

    if parsed.provider == "deepgram" and not deepgram_api_key:
        raise STTProviderUnconfiguredError(parsed.provider)

    if parsed.provider == "azure" and (
        not azure_speech_key or not (azure_speech_region or azure_speech_endpoint)
    ):
        raise STTProviderUnconfiguredError(parsed.provider)

    return build_stt_provider(
        parsed.provider,
        model=parsed.model,
        language=language,
        deepgram_api_key=deepgram_api_key,
        azure_speech_key=azure_speech_key,
        azure_speech_region=azure_speech_region,
        azure_speech_endpoint=azure_speech_endpoint,
    )
