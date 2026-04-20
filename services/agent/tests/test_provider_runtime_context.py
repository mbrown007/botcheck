from src.provider_runtime_context import RuntimeSettingsOverlay, build_settings_overrides


def test_build_settings_overrides_maps_provider_secret_fields() -> None:
    overrides = build_settings_overrides(
        {
            "feature_flags": {
                "feature_tts_provider_openai_enabled": False,
                "feature_stt_provider_azure_enabled": True,
            },
            "tts": {
                "vendor": "openai",
                "secret_fields": {"api_key": "stored-openai-key"},
            },
            "stt": {
                "vendor": "azure",
                "secret_fields": {
                    "api_key": "stored-azure-key",
                    "region": "uksouth",
                    "endpoint": "https://speech.test",
                },
            },
        }
    )

    assert overrides["feature_tts_provider_openai_enabled"] is False
    assert overrides["feature_stt_provider_azure_enabled"] is True
    assert overrides["openai_api_key"] == "stored-openai-key"
    assert overrides["azure_speech_key"] == "stored-azure-key"
    assert overrides["azure_speech_region"] == "uksouth"
    assert overrides["azure_speech_endpoint"] == "https://speech.test"


def test_runtime_settings_overlay_falls_back_to_base_settings() -> None:
    base_settings = type(
        "SettingsStub",
        (),
        {
            "openai_api_key": "env-openai-key",
            "feature_tts_provider_openai_enabled": True,
        },
    )()
    overlay = RuntimeSettingsOverlay(
        base_settings=base_settings,
        overrides={"openai_api_key": "stored-openai-key"},
    )

    assert overlay.openai_api_key == "stored-openai-key"
    assert overlay.feature_tts_provider_openai_enabled is True


def test_runtime_settings_overlay_masks_base_provider_secrets_without_override() -> None:
    base_settings = type(
        "SettingsStub",
        (),
        {
            "openai_api_key": "env-openai-key",
            "deepgram_api_key": "env-deepgram-key",
            "feature_tts_provider_openai_enabled": True,
        },
    )()
    overlay = RuntimeSettingsOverlay(
        base_settings=base_settings,
        overrides={},
    )

    assert overlay.openai_api_key == ""
    assert overlay.deepgram_api_key == ""
    assert overlay.feature_tts_provider_openai_enabled is True
