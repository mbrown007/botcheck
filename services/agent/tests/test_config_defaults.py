from src.config import Settings


def test_branching_graph_execution_enabled_by_default() -> None:
    settings = Settings.model_construct(
        livekit_url="ws://livekit.example.test",
        livekit_api_key="key",
        livekit_api_secret="secret",
        openai_api_key="openai-key",
        deepgram_api_key="deepgram-key",
    )

    assert settings.enable_branching_graph is True
    assert settings.feature_stt_provider_deepgram_enabled is True
    assert settings.feature_stt_provider_azure_enabled is False
    assert settings.playground_mock_agent_model == "gpt-4o-mini"
