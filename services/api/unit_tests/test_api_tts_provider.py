from unittest.mock import AsyncMock

from botcheck_api import stt_provider
from botcheck_api import tts_provider


def test_provider_available_tracks_feature_flag_only(monkeypatch) -> None:
    monkeypatch.setattr(tts_provider.settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(tts_provider.settings, "elevenlabs_api_key", "")

    assert tts_provider.provider_available("elevenlabs") is True

    monkeypatch.setattr(tts_provider.settings, "feature_tts_provider_elevenlabs_enabled", False)

    assert tts_provider.provider_available("elevenlabs") is False


def test_build_api_speech_capabilities_keeps_tts_features_without_secrets(monkeypatch) -> None:
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_openai_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "openai_api_key", "")
    monkeypatch.setattr(stt_provider.settings, "feature_tts_provider_elevenlabs_enabled", True)
    monkeypatch.setattr(stt_provider.settings, "elevenlabs_api_key", "")

    capabilities = stt_provider.build_api_speech_capabilities()

    assert [provider.enabled for provider in capabilities.tts] == [True, True]


async def test_resolve_tenant_preview_tts_provider_requires_stored_secret(monkeypatch) -> None:
    monkeypatch.setattr(tts_provider.settings, "openai_api_key", "MUST-NOT-REACH-PREVIEW")
    monkeypatch.setattr(
        tts_provider,
        "_resolve_tenant_tts_voice",
        AsyncMock(
            return_value=(
                tts_provider.parse_tts_voice("openai:nova"),
                {
                    "provider_id": "openai:gpt-4o-mini-tts",
                    "credential_source": "db_encrypted",
                },
            )
        ),
    )
    monkeypatch.setattr(
        tts_provider,
        "get_valid_platform_provider_secret_fields",
        AsyncMock(return_value={}),
    )

    try:
        await tts_provider.resolve_tenant_preview_tts_provider(
            AsyncMock(),
            tenant_id="tenant-1",
            tts_voice="openai:nova",
        )
    except tts_provider.TTSProviderUnconfiguredError as exc:
        assert exc.provider == "openai"
    else:
        raise AssertionError("expected tenant preview provider to require a stored secret")


async def test_resolve_tenant_preview_tts_provider_uses_stored_secret(monkeypatch) -> None:
    monkeypatch.setattr(tts_provider.settings, "tts_preview_openai_model", "gpt-4o-mini-tts")
    monkeypatch.setattr(
        tts_provider,
        "_resolve_tenant_tts_voice",
        AsyncMock(
            return_value=(
                tts_provider.parse_tts_voice("openai:nova"),
                {
                    "provider_id": "openai:gpt-4o-mini-tts",
                    "credential_source": "db_encrypted",
                },
            )
        ),
    )
    monkeypatch.setattr(
        tts_provider,
        "get_valid_platform_provider_secret_fields",
        AsyncMock(return_value={"api_key": "test-openai"}),
    )

    provider = await tts_provider.resolve_tenant_preview_tts_provider(
        AsyncMock(),
        tenant_id="tenant-1",
        tts_voice="openai:nova",
    )

    assert provider.provider_id == "openai"
    assert provider.model_label == "gpt-4o-mini-tts"
    assert getattr(provider, "catalog_provider_id", None) == "openai:gpt-4o-mini-tts"
