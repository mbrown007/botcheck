import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")

from botcheck_scenarios import ElevenLabsTTSProvider, TTSProviderDisabledError

from botcheck_judge import tts_provider


def test_resolve_cache_warm_tts_provider_returns_elevenlabs(monkeypatch) -> None:
    monkeypatch.setattr(tts_provider.settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(tts_provider.settings, "tts_cache_elevenlabs_model", "eleven_flash_v2_5")
    monkeypatch.setattr(tts_provider.settings, "tts_cache_elevenlabs_output_format", "pcm_24000")
    monkeypatch.setattr(tts_provider.settings, "elevenlabs_api_key", "test-elevenlabs")

    provider = tts_provider.resolve_cache_warm_tts_provider("elevenlabs:voice-123")

    assert isinstance(provider, ElevenLabsTTSProvider)
    assert provider.provider_id == "elevenlabs"
    assert provider.model_label == "eleven_flash_v2_5"
    assert provider.output_format == "pcm_24000"


def test_resolve_cache_warm_tts_provider_rejects_disabled_elevenlabs(monkeypatch) -> None:
    monkeypatch.setattr(tts_provider.settings, "feature_tts_provider_elevenlabs_enabled", False)

    try:
        tts_provider.resolve_cache_warm_tts_provider("elevenlabs:voice-123")
    except TTSProviderDisabledError as exc:
        assert exc.provider == "elevenlabs"
    else:
        raise AssertionError("expected ElevenLabs cache-warm provider to be disabled")


def test_resolve_cache_warm_tts_provider_uses_runtime_settings_override() -> None:
    settings_obj = type(
        "SettingsStub",
        (),
        {
            "feature_tts_provider_openai_enabled": True,
            "feature_tts_provider_elevenlabs_enabled": False,
            "tts_cache_openai_model": "gpt-4o-mini-tts",
            "openai_api_key": "stored-openai-key",
        },
    )()

    provider = tts_provider.resolve_cache_warm_tts_provider(
        "openai:alloy",
        settings_obj=settings_obj,
    )

    assert provider.provider_id == "openai"
    assert provider.model_label == "gpt-4o-mini-tts"
