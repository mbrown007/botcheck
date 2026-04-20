from botcheck_observability import trace_contract


def test_canonical_span_names_match_contract() -> None:
    assert trace_contract.CANONICAL_SPAN_NAMES == frozenset(
        {
            "run.lifecycle",
            "dispatch.livekit",
            "dispatch.sip",
            "harness.session",
            "judge.run",
            "judge.llm_score",
        }
    )


def test_required_trace_attributes_match_contract() -> None:
    assert trace_contract.REQUIRED_TRACE_ATTRIBUTES == (
        "run.id",
        "tenant.id",
        "scenario.id",
        "scenario.kind",
        "trigger.source",
        "transport.kind",
        "transport_profile.id",
        "schedule.id",
        "judge.contract_version",
    )


def test_extract_trace_context_headers_returns_only_trimmed_trace_fields() -> None:
    payload = trace_contract.extract_trace_context_headers(
        {
            "traceparent": " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 ",
            "tracestate": " vendor=test ",
            "baggage": "should-not-be-forwarded",
        }
    )

    assert payload == {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "tracestate": "vendor=test",
    }


def test_current_w3c_trace_context_returns_only_trace_fields(monkeypatch) -> None:
    def _fake_inject(*, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 "
        carrier["tracestate"] = " vendor=test "
        carrier["baggage"] = "ignored"

    monkeypatch.setattr("opentelemetry.propagate.inject", _fake_inject)

    assert trace_contract.current_w3c_trace_context() == {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "tracestate": "vendor=test",
    }


def test_inject_trace_context_into_headers_preserves_existing_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        trace_contract,
        "current_w3c_trace_context",
        lambda: {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        },
    )

    headers = trace_contract.inject_trace_context_into_headers({"Authorization": "Bearer token"})

    assert headers == {
        "Authorization": "Bearer token",
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    }


def test_attach_trace_context_from_carrier_roundtrip(monkeypatch) -> None:
    extracted_sentinel = object()
    token_sentinel = object()
    calls: dict[str, object] = {}

    def _fake_extract(*, carrier):
        calls["carrier"] = carrier
        return extracted_sentinel

    def _fake_attach(ctx):
        calls["ctx"] = ctx
        return token_sentinel

    monkeypatch.setattr("opentelemetry.propagate.extract", _fake_extract)
    monkeypatch.setattr("opentelemetry.context.attach", _fake_attach)

    token = trace_contract.attach_trace_context_from_carrier(
        {
            "traceparent": " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 ",
            "tracestate": " vendor=test ",
            "baggage": "ignored",
        }
    )

    assert token is token_sentinel
    assert calls == {
        "carrier": {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        },
        "ctx": extracted_sentinel,
    }


def test_detach_trace_context_is_noop_for_none(monkeypatch) -> None:
    detached: list[object] = []

    monkeypatch.setattr("opentelemetry.context.detach", lambda token: detached.append(token))

    trace_contract.detach_trace_context(None)

    assert detached == []


def test_detach_trace_context_detaches_token(monkeypatch) -> None:
    detached: list[object] = []
    token = object()

    monkeypatch.setattr("opentelemetry.context.detach", lambda received: detached.append(received))

    trace_contract.detach_trace_context(token)

    assert detached == [token]
