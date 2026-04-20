from botcheck_observability import provider


def test_provider_metric_labels_match_contract() -> None:
    assert tuple(provider.PROVIDER_API_CALLS_TOTAL._labelnames) == (
        "provider",
        "service",
        "model",
        "outcome",
    )
    assert tuple(provider.LLM_TOKENS_TOTAL._labelnames) == (
        "provider",
        "model",
        "token_type",
    )
    assert tuple(provider.TTS_CHARACTERS_TOTAL._labelnames) == (
        "provider",
        "model",
        "scenario_kind",
    )
    assert tuple(provider.STT_SECONDS_TOTAL._labelnames) == (
        "provider",
        "model",
        "scenario_kind",
    )
    assert tuple(provider.TELEPHONY_MINUTES_TOTAL._labelnames) == (
        "provider",
        "direction",
    )
    assert tuple(provider.TTS_PREVIEW_REQUESTS_TOTAL._labelnames) == ("outcome",)
