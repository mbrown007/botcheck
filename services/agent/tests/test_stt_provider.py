import os

import pytest
from botcheck_scenarios import STTProviderDisabledError, STTProviderUnsupportedError

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

from src.stt_provider import STTProviderUnconfiguredError, resolve_live_stt_provider  # noqa: E402


def _settings(**overrides):
    defaults = {
        "feature_stt_provider_deepgram_enabled": True,
        "feature_stt_provider_azure_enabled": False,
        "deepgram_api_key": "test-deepgram-key",
        "azure_speech_key": "",
        "azure_speech_region": "",
        "azure_speech_endpoint": "",
    }
    defaults.update(overrides)
    return type("SettingsStub", (), defaults)()


def test_resolve_live_stt_provider_uses_configured_model_label():
    provider = resolve_live_stt_provider(
        stt_provider=" Deepgram ",
        stt_model="nova-2-phonecall",
        language="en-GB",
        settings_obj=_settings(),
    )

    assert provider.provider_id == "deepgram"
    assert provider.model_label == "nova-2-phonecall"
    assert provider.language == "en-GB"


def test_resolve_live_stt_provider_raises_when_deepgram_disabled():
    with pytest.raises(STTProviderDisabledError, match="deepgram"):
        resolve_live_stt_provider(
            stt_provider="deepgram",
            stt_model="nova-2-general",
            language="en-US",
            settings_obj=_settings(feature_stt_provider_deepgram_enabled=False),
        )


def test_resolve_live_stt_provider_raises_when_deepgram_unconfigured():
    with pytest.raises(STTProviderUnconfiguredError, match="deepgram"):
        resolve_live_stt_provider(
            stt_provider="deepgram",
            stt_model="nova-2-general",
            language="en-US",
            settings_obj=_settings(deepgram_api_key=""),
        )


def test_resolve_live_stt_provider_uses_azure_settings_when_enabled():
    provider = resolve_live_stt_provider(
        stt_provider=" Azure ",
        stt_model="azure-default",
        language="en-GB",
        settings_obj=_settings(
            feature_stt_provider_azure_enabled=True,
            azure_speech_key="test-azure-key",
            azure_speech_region="uksouth",
        ),
    )

    assert provider.provider_id == "azure"
    assert provider.model_label == "azure-default"
    assert provider.language == "en-GB"


def test_resolve_live_stt_provider_raises_when_azure_disabled():
    with pytest.raises(STTProviderDisabledError, match="azure"):
        resolve_live_stt_provider(
            stt_provider="azure",
            stt_model="azure-default",
            language="en-US",
            settings_obj=_settings(
                feature_stt_provider_azure_enabled=False,
                azure_speech_key="test-azure-key",
                azure_speech_region="uksouth",
            ),
        )


def test_resolve_live_stt_provider_raises_when_azure_unconfigured():
    with pytest.raises(STTProviderUnconfiguredError, match="azure"):
        resolve_live_stt_provider(
            stt_provider="azure",
            stt_model="azure-default",
            language="en-US",
            settings_obj=_settings(
                feature_stt_provider_azure_enabled=True,
                azure_speech_key="",
                azure_speech_region="",
                azure_speech_endpoint="",
            ),
        )


def test_resolve_live_stt_provider_raises_when_provider_unsupported():
    with pytest.raises(STTProviderUnsupportedError, match="whisper"):
        resolve_live_stt_provider(
            stt_provider="whisper",
            stt_model="whisper-large",
            language="en-US",
            settings_obj=_settings(),
        )
