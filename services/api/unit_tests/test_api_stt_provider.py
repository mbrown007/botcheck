import pytest

from botcheck_api import stt_provider
from botcheck_scenarios import DEFAULT_STT_PROVIDER, parse_stt_config


def test_build_api_speech_capabilities_shows_deepgram_enabled_without_api_key(monkeypatch) -> None:
    """Regression guard: deepgram availability is determined by feature flag alone.

    DEEPGRAM_API_KEY lives in the harness agent, not the API service. The /features
    capability report must not require the key to show deepgram as enabled.
    """
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_openai_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_elevenlabs_enabled", False)
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_deepgram_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_azure_enabled", False)
    monkeypatch.setattr(stt_provider.settings, "deepgram_api_key", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_key", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_region", "")

    capabilities = stt_provider.build_api_speech_capabilities()

    assert [provider.id for provider in capabilities.stt] == ["deepgram", "azure"]
    assert [provider.enabled for provider in capabilities.stt] == [True, False]


def test_provider_stt_available_requires_only_feature_flag(monkeypatch) -> None:
    """Regression guard: key absence must not affect provider availability."""
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_deepgram_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "deepgram_api_key", "")
    assert stt_provider.provider_stt_available("deepgram") is True

    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_deepgram_enabled", False)
    assert stt_provider.provider_stt_available("deepgram") is False


def test_provider_stt_available_requires_only_feature_flag_for_azure(monkeypatch) -> None:
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_azure_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "azure_speech_key", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_region", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_endpoint", "")
    assert stt_provider.provider_stt_available("azure") is True

    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_azure_enabled", False)
    assert stt_provider.provider_stt_available("azure") is False


def test_build_api_speech_capabilities_shows_azure_enabled_without_api_secret(monkeypatch) -> None:
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_openai_enabled", False)
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_elevenlabs_enabled", False)
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_deepgram_enabled", False)
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_azure_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "azure_speech_key", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_region", "")
    monkeypatch.setattr(stt_provider.settings, "azure_speech_endpoint", "")

    capabilities = stt_provider.build_api_speech_capabilities()

    assert [provider.enabled for provider in capabilities.stt] == [False, True]


def test_provider_stt_available_returns_false_for_unknown_provider(monkeypatch) -> None:
    """Regression guard: unrecognised provider names must return False, not raise."""
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_deepgram_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "feature_stt_provider_azure_enabled", True)
    assert stt_provider.provider_stt_available("whisper") is False
    assert stt_provider.provider_stt_available("google") is False
    assert stt_provider.provider_stt_available("") is False


def test_parse_stt_config_defaults_empty_provider_to_deepgram() -> None:
    """Empty stt_provider string must fall back to DEFAULT_STT_PROVIDER."""
    parsed = parse_stt_config("", "nova-2-general")
    assert parsed.provider == DEFAULT_STT_PROVIDER


def test_parse_stt_config_raises_for_empty_model() -> None:
    """Empty stt_model must raise ValueError."""
    with pytest.raises(ValueError, match="stt_model"):
        parse_stt_config("deepgram", "")
