import os

import pytest
from botcheck_scenarios import TTSProviderDisabledError

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

from src.tts_provider import resolve_live_tts_provider  # noqa: E402


def _settings(**overrides):
    defaults = {
        "feature_tts_provider_openai_enabled": True,
        "feature_tts_provider_elevenlabs_enabled": False,
        "tts_live_openai_model": "gpt-4o-mini-tts",
        "openai_api_key": "test-openai-key",
    }
    defaults.update(overrides)
    return type("SettingsStub", (), defaults)()


def test_resolve_live_tts_provider_uses_configured_model_label():
    provider = resolve_live_tts_provider(
        tts_voice=" openai:nova ",
        settings_obj=_settings(tts_live_openai_model="gpt-4.1-mini-tts"),
    )

    assert provider.provider_id == "openai"
    assert provider.model_label == "gpt-4.1-mini-tts"


def test_resolve_live_tts_provider_returns_elevenlabs_when_enabled():
    provider = resolve_live_tts_provider(
        tts_voice="elevenlabs:voice-123",
        settings_obj=_settings(
            feature_tts_provider_elevenlabs_enabled=True,
            tts_live_elevenlabs_model="eleven_flash_v2_5",
            tts_live_elevenlabs_output_format="pcm_24000",
            elevenlabs_api_key="test-elevenlabs",
        ),
    )

    assert provider.provider_id == "elevenlabs"
    assert provider.model_label == "eleven_flash_v2_5"
    assert provider.output_format == "pcm_24000"


def test_resolve_live_tts_provider_raises_when_openai_disabled():
    with pytest.raises(TTSProviderDisabledError, match="openai"):
        resolve_live_tts_provider(
            tts_voice="openai:nova",
            settings_obj=_settings(feature_tts_provider_openai_enabled=False),
        )


def test_resolve_live_tts_provider_raises_when_elevenlabs_disabled():
    with pytest.raises(TTSProviderDisabledError, match="elevenlabs"):
        resolve_live_tts_provider(
            tts_voice="elevenlabs:voice-123",
            settings_obj=_settings(feature_tts_provider_elevenlabs_enabled=False),
        )
