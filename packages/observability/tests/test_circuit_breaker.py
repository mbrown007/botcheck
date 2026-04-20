from botcheck_observability import circuit_breaker


def test_circuit_breaker_metric_labels_match_contract() -> None:
    assert tuple(circuit_breaker.PROVIDER_CIRCUIT_TRANSITIONS_TOTAL._labelnames) == (
        "provider",
        "service",
        "component",
        "from_state",
        "to_state",
    )
    assert tuple(circuit_breaker.PROVIDER_CIRCUIT_REJECTIONS_TOTAL._labelnames) == (
        "provider",
        "service",
        "component",
    )
    assert tuple(circuit_breaker.PROVIDER_CIRCUIT_STATE._labelnames) == (
        "source",
        "provider",
        "service",
        "component",
        "state",
    )


def test_set_provider_circuit_state_sets_one_hot_labels() -> None:
    circuit_breaker.set_provider_circuit_state(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="open",
    )

    open_value = circuit_breaker.PROVIDER_CIRCUIT_STATE.labels(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="open",
    )._value.get()
    closed_value = circuit_breaker.PROVIDER_CIRCUIT_STATE.labels(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="closed",
    )._value.get()
    assert open_value == 1.0
    assert closed_value == 0.0


def test_set_provider_circuit_state_unknown_fallback() -> None:
    circuit_breaker.set_provider_circuit_state(
        source="judge",
        provider="anthropic",
        service="llm",
        component="judge_scoring",
        state="not_real",
    )
    unknown_value = circuit_breaker.PROVIDER_CIRCUIT_STATE.labels(
        source="judge",
        provider="anthropic",
        service="llm",
        component="judge_scoring",
        state="unknown",
    )._value.get()
    assert unknown_value == 1.0
