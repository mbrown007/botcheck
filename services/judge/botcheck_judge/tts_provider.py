from __future__ import annotations

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

_CACHE_WARM_TTS_BREAKERS = ProviderKeyedRegistry[AsyncCircuitBreaker[bytes]](
    lambda provider: AsyncCircuitBreaker[bytes](
        name=f"judge.cache_tts.{provider}",
        failure_threshold=settings.tts_cache_circuit_failure_threshold,
        recovery_timeout_s=settings.tts_cache_circuit_recovery_s,
    )
)


def get_cache_warm_tts_circuit_breaker(provider: str) -> AsyncCircuitBreaker[bytes]:
    return _CACHE_WARM_TTS_BREAKERS.get(provider)


def reset_cache_warm_tts_breakers(provider: str | None = None) -> None:
    _CACHE_WARM_TTS_BREAKERS.reset(provider)


def resolve_cache_warm_tts_provider(tts_voice: str, *, settings_obj=settings) -> TTSProvider:
    parsed_voice = parse_tts_voice(tts_voice)
    enabled = tts_provider_enabled(
        parsed_voice.provider,
        feature_tts_provider_openai_enabled=bool(
            getattr(settings_obj, "feature_tts_provider_openai_enabled", True)
        ),
        feature_tts_provider_elevenlabs_enabled=bool(
            getattr(settings_obj, "feature_tts_provider_elevenlabs_enabled", False)
        ),
    )

    if parsed_voice.provider == "openai":
        if not enabled:
            raise TTSProviderDisabledError(parsed_voice.provider)
        return OpenAITTSProvider(
            voice_id=parsed_voice.voice,
            model_label=str(getattr(settings_obj, "tts_cache_openai_model", settings.tts_cache_openai_model)),
            api_key=str(getattr(settings_obj, "openai_api_key", "")),
        )

    if parsed_voice.provider == "elevenlabs":
        if not enabled:
            raise TTSProviderDisabledError(parsed_voice.provider)
        return ElevenLabsTTSProvider(
            voice_id=parsed_voice.voice,
            model_label=str(
                getattr(settings_obj, "tts_cache_elevenlabs_model", settings.tts_cache_elevenlabs_model)
            ),
            api_key=str(getattr(settings_obj, "elevenlabs_api_key", "")),
            output_format=str(
                getattr(
                    settings_obj,
                    "tts_cache_elevenlabs_output_format",
                    settings.tts_cache_elevenlabs_output_format,
                )
            ),
        )

    raise TTSProviderUnsupportedError(parsed_voice.provider)
