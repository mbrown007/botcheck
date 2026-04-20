from types import SimpleNamespace

import pytest
from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn

from botcheck_api.runs import service as runs_service
from botcheck_api.runs import service_judge


def test_current_w3c_trace_context_returns_only_trace_fields(monkeypatch) -> None:
    def _fake_inject(carrier: dict[str, str]) -> None:
        carrier["traceparent"] = " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 "
        carrier["tracestate"] = " vendor=test "
        carrier["baggage"] = "should-not-be-forwarded"

    monkeypatch.setattr("opentelemetry.propagate.inject", _fake_inject)

    payload = runs_service.current_w3c_trace_context()

    assert payload == {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "tracestate": "vendor=test",
    }


def test_current_w3c_trace_context_omits_empty_fields(monkeypatch) -> None:
    monkeypatch.setattr("opentelemetry.propagate.inject", lambda carrier: None)

    assert runs_service.current_w3c_trace_context() == {}


@pytest.mark.asyncio
async def test_build_judge_job_payload_includes_current_trace_headers(monkeypatch) -> None:
    scenario = ScenarioDefinition(
        id="test-scenario",
        name="Test Scenario",
        type=ScenarioType.RELIABILITY,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[Turn(id="t1", text="hello")],
    )

    async def _fake_get_scenario(_db, _scenario_id, _tenant_id):
        return scenario, "sha256:test"

    async def _fake_get_scenario_kind(_db, _scenario_id, _tenant_id):
        return "graph"

    monkeypatch.setattr(
        service_judge.scenarios_store_service,
        "get_scenario",
        _fake_get_scenario,
    )
    monkeypatch.setattr(
        service_judge.scenarios_store_service,
        "get_scenario_kind",
        _fake_get_scenario_kind,
    )
    monkeypatch.setattr(
        service_judge,
        "current_w3c_trace_context",
        lambda: {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        },
    )

    payload = await service_judge.build_judge_job_payload(
        None,
        run=SimpleNamespace(
            run_id="run_test",
            scenario_id="test-scenario",
            tenant_id="tenant-test",
            trigger_source="manual",
            created_at=None,
            conversation=[
                {
                    "turn_id": "t1",
                    "turn_number": 1,
                    "speaker": "harness",
                    "text": "hello",
                }
            ],
            events=[],
        ),
        tool_context=[],
    )

    assert payload["traceparent"] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert payload["tracestate"] == "vendor=test"
