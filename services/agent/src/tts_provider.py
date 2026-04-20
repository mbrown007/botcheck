from __future__ import annotations

from typing import Any

from botcheck_scenarios import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
    TTSProvider,
    TTSProviderDisabledError,
    TTSProviderUnsupportedError,
    parse_tts_voice,
    tts_provider_enabled,
)


def resolve_live_tts_provider(
    *,
    tts_voice: str,
    settings_obj: Any,
) -> TTSProvider:
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
            model_label=str(
                getattr(settings_obj, "tts_live_openai_model", "gpt-4o-mini-tts")
            ).strip()
            or "gpt-4o-mini-tts",
            api_key=getattr(settings_obj, "openai_api_key", ""),
        )

    if parsed_voice.provider == "elevenlabs":
        if not enabled:
            raise TTSProviderDisabledError(parsed_voice.provider)
        return ElevenLabsTTSProvider(
            voice_id=parsed_voice.voice,
            model_label=str(
                getattr(settings_obj, "tts_live_elevenlabs_model", "eleven_flash_v2_5")
            ).strip()
            or "eleven_flash_v2_5",
            api_key=getattr(settings_obj, "elevenlabs_api_key", ""),
            output_format=str(
                getattr(settings_obj, "tts_live_elevenlabs_output_format", "pcm_24000")
            ).strip()
            or "pcm_24000",
        )

    raise TTSProviderUnsupportedError(parsed_voice.provider)
