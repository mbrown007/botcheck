"""Tests for judge worker error classification helpers."""

import json
import os
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")

import pytest
from botcheck_observability.trace_contract import (
    ATTR_JUDGE_CONTRACT_VERSION,
    ATTR_JUDGE_GATE,
    ATTR_JUDGE_METRIC_TYPE,
    ATTR_JUDGE_PASSED,
    ATTR_JUDGE_SCORE,
    ATTR_JUDGE_STATUS,
    ATTR_JUDGE_THRESHOLD,
    ATTR_RUN_ID,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_KIND,
    ATTR_SCORE_DIMENSION,
    ATTR_TENANT_ID,
    ATTR_TRIGGER_SOURCE,
    SPAN_JUDGE_LLM_SCORE,
    SPAN_JUDGE_RUN,
)
from botcheck_scenarios import (
    BotConfig,
    DimensionScore,
    GateResult,
    MetricType,
    RunReport,
    RunStatus,
    ScenarioDefinition,
    ScenarioType,
    Turn,
    classify_judge_error,
)

from botcheck_judge.workers.judge_worker import (
    JudgeJobPayload,
    _build_report_s3_key,
    _classify_judge_error,
    _validate_safety_input_contract,
    judge_run,
)
from botcheck_judge.workers.scheduler_worker import (
    dispatch_pack_run,
    reap_orphan_runs,
    tick_schedules,
)
from botcheck_judge.metrics import JUDGE_RUNS_INFLIGHT
from botcheck_judge.metrics import JUDGE_LLM_LATENCY_SECONDS, SCENARIO_GATE_RESULTS_TOTAL


class _FakeSpan(AbstractContextManager[None]):
    def __init__(self, recorder: list[tuple[str, dict[str, object] | None]], name: str, attributes):
        self._recorder = recorder
        self._name = name
        self._attributes = dict(attributes) if attributes is not None else None

    def __enter__(self):
        self._recorder.append((self._name, self._attributes))
        return None

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FakeTracer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def start_as_current_span(self, name: str, *, attributes=None):
        return _FakeSpan(self.calls, name, attributes)


def _counter_value(counter, **labels):
    return counter.labels(**labels)._value.get()


def _hist_count(histogram, **labels):
    labeled = histogram.labels(**labels)
    for metric in labeled.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    raise AssertionError("Histogram count sample not found")


def _scenario(scenario_type: ScenarioType) -> ScenarioDefinition:
    return ScenarioDefinition(
        id="test-scenario",
        name="Test Scenario",
        type=scenario_type,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[Turn(id="t1", text="hello")],
    )


def _payload(
    *,
    include_tool_context_key: bool = True,
    tool_context: list | None = None,
    scenario_kind: str | None = None,
    judge_contract_version: int | None = None,
    ai_context: dict | None = None,
) -> dict:
    payload = {
        "run_id": "run_test",
        "scenario_id": "test-scenario",
        "tenant_id": "tenant-test",
        "started_at": "2026-01-01T00:00:00+00:00",
        "conversation": [
            {
                "turn_id": "t1",
                "turn_number": 1,
                "speaker": "harness",
                "text": "hello",
                "audio_start_ms": 0,
                "audio_end_ms": 250,
            },
            {
                "turn_id": "t2",
                "turn_number": 2,
                "speaker": "bot",
                "text": "hi there",
                "audio_start_ms": 300,
                "audio_end_ms": 900,
            },
        ],
    }
    if include_tool_context_key:
        payload["tool_context"] = [] if tool_context is None else tool_context
    if scenario_kind is not None:
        payload["scenario_kind"] = scenario_kind
    if judge_contract_version is not None:
        payload["judge_contract_version"] = judge_contract_version
    if ai_context is not None:
        payload["ai_context"] = ai_context
    return payload


def _judge_runtime_context(*, api_key: str = "stored-anthropic-key", model: str = "test-model") -> dict:
    return {
        "providers": [
            {
                "capability": "judge",
                "provider_id": f"anthropic:{model}",
                "vendor": "anthropic",
                "model": model,
                "availability_status": "available",
                "credential_source": "db_encrypted",
                "secret_fields": {"api_key": api_key},
            }
        ]
    }


def test_classify_value_error_as_parse_failure():
    assert _classify_judge_error(ValueError("Unparseable judge response JSON")) == "judge_parse_failure"


def test_classify_json_decode_error_as_parse_failure():
    exc = json.JSONDecodeError("Expecting value", "{}", 0)
    assert _classify_judge_error(exc) == "judge_parse_failure"


def test_classify_other_errors_as_llm_failure():
    assert _classify_judge_error(RuntimeError("Anthropic request failed")) == "judge_llm_failure"


def test_worker_classifier_matches_shared_taxonomy():
    exc = RuntimeError("upstream failed")
    assert _classify_judge_error(exc) == classify_judge_error(exc).value


def test_report_s3_key_is_tenant_prefixed():
    key = _build_report_s3_key(
        run_id="run_abc",
        tenant_id="acme",
        now=datetime(2026, 2, 27, tzinfo=UTC),
    )
    assert key == "acme/reports/2026/02/27/run_abc.json"


def test_report_s3_key_uses_default_prefix_for_blank_tenant():
    key = _build_report_s3_key(
        run_id="run_abc",
        tenant_id="",
        now=datetime(2026, 2, 27, tzinfo=UTC),
    )
    assert key == "default/reports/2026/02/27/run_abc.json"


def test_safety_contract_rejects_missing_tool_context_key():
    scenario = _scenario(ScenarioType.ADVERSARIAL)
    raw_payload = _payload(include_tool_context_key=False)
    job_payload = JudgeJobPayload.model_validate(raw_payload)
    with pytest.raises(ValueError, match="tool_context"):
        _validate_safety_input_contract(
            scenario=scenario,
            job_payload=job_payload,
            raw_payload=raw_payload,
        )


def test_safety_contract_rejects_tool_context_unknown_turn_reference():
    scenario = _scenario(ScenarioType.ADVERSARIAL)
    raw_payload = _payload(
        tool_context=[
            {"tool_name": "lookup_customer", "turn_number": 99, "status": "success"},
        ]
    )
    job_payload = JudgeJobPayload.model_validate(raw_payload)
    with pytest.raises(ValueError, match="unknown turn_number"):
        _validate_safety_input_contract(
            scenario=scenario,
            job_payload=job_payload,
            raw_payload=raw_payload,
        )


def test_non_safety_scenario_allows_missing_tool_context_key():
    scenario = _scenario(ScenarioType.RELIABILITY)
    raw_payload = _payload(include_tool_context_key=False)
    job_payload = JudgeJobPayload.model_validate(raw_payload)
    _validate_safety_input_contract(
        scenario=scenario,
        job_payload=job_payload,
        raw_payload=raw_payload,
    )


def test_payload_validation_rejects_non_monotonic_turn_numbers():
    raw_payload = _payload()
    raw_payload["conversation"][1]["turn_number"] = 1
    with pytest.raises(ValueError, match="strictly increasing"):
        JudgeJobPayload.model_validate(raw_payload)


def test_payload_validation_rejects_branching_without_taken_path_steps():
    raw_payload = _payload()
    raw_payload["scenario_has_branching"] = True
    with pytest.raises(ValueError, match="taken_path_steps"):
        JudgeJobPayload.model_validate(raw_payload)


def test_payload_validation_rejects_branching_with_empty_taken_path_steps():
    raw_payload = _payload()
    raw_payload["scenario_has_branching"] = True
    raw_payload["taken_path_steps"] = []
    with pytest.raises(ValueError, match="taken_path_steps"):
        JudgeJobPayload.model_validate(raw_payload)


def test_payload_validation_accepts_branching_with_taken_path_steps():
    raw_payload = _payload()
    raw_payload["scenario_has_branching"] = True
    raw_payload["taken_path_steps"] = [
        {"turn_id": "t1", "visit": 1, "turn_number": 1},
    ]
    payload = JudgeJobPayload.model_validate(raw_payload)
    assert payload.scenario_has_branching is True
    assert len(payload.taken_path_steps) == 1
    assert payload.taken_path_steps[0].turn_id == "t1"
    assert payload.taken_path_steps[0].visit == 1
    assert payload.taken_path_steps[0].turn_number == 1


def test_payload_validation_defaults_to_graph_contract_v1():
    payload = JudgeJobPayload.model_validate(_payload())
    assert payload.scenario_kind == "graph"
    assert payload.judge_contract_version == 1


def test_payload_validation_rejects_ai_scenario_with_v1_contract():
    raw_payload = _payload(scenario_kind="ai", judge_contract_version=1)
    with pytest.raises(ValueError, match="judge_contract_version >= 2"):
        JudgeJobPayload.model_validate(raw_payload)


def test_payload_validation_accepts_ai_scenario_with_v2_contract():
    payload = JudgeJobPayload.model_validate(
        _payload(
            scenario_kind="ai",
            judge_contract_version=2,
            ai_context={
                "dataset_input": "Caller asks for a two-bedroom condo in Queens.",
                "expected_output": "Recommend options and avoid booking a tour.",
                "persona_id": "persona_real_estate_1",
            },
        )
    )
    assert payload.scenario_kind == "ai"
    assert payload.judge_contract_version == 2


def test_payload_validation_rejects_ai_scenario_without_ai_context():
    raw_payload = _payload(scenario_kind="ai", judge_contract_version=2)
    with pytest.raises(ValueError, match="ai_context"):
        JudgeJobPayload.model_validate(raw_payload)


def test_payload_validation_accepts_trace_context_headers():
    payload = JudgeJobPayload.model_validate(
        {
            **_payload(),
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        }
    )
    assert payload.traceparent == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert payload.tracestate == "vendor=test"


def _make_http_client_cm(scenario: ScenarioDefinition):
    """Return a context manager that serves a single scenario GET response."""

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return scenario.model_dump(mode="json")

    class _Client:
        async def get(self, url: str):
            return _Resp()

    class _CM:
        async def __aenter__(self):
            return _Client()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return lambda *args, **kwargs: _CM()


@pytest.mark.asyncio
@patch("botcheck_judge.workers.judge_worker._patch_fail_closed", new_callable=AsyncMock)
async def test_judge_run_unavailable_binding_applies_fail_closed_patch(
    mock_patch_fail_closed, monkeypatch
):
    """Provider binding with availability_status != 'available' must fail-close the run."""
    scenario = _scenario(ScenarioType.RELIABILITY)
    raw_payload = _payload()
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.httpx.AsyncClient",
        _make_http_client_cm(scenario),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._fetch_provider_runtime_context",
        AsyncMock(
            return_value={
                "providers": [
                    {
                        "capability": "judge",
                        "provider_id": "anthropic:claude-sonnet-4-6",
                        "vendor": "anthropic",
                        "model": "claude-sonnet-4-6",
                        "availability_status": "unconfigured",
                        "credential_source": "none",
                        "secret_fields": None,
                    }
                ]
            }
        ),
    )
    with pytest.raises(RuntimeError, match="Judge provider runtime binding unavailable"):
        await judge_run({}, payload=raw_payload)
    mock_patch_fail_closed.assert_awaited_once()
    assert mock_patch_fail_closed.await_args.args[0] == "run_test"


@pytest.mark.asyncio
@patch("botcheck_judge.workers.judge_worker._patch_fail_closed", new_callable=AsyncMock)
async def test_judge_run_available_binding_with_missing_api_key_applies_fail_closed_patch(
    mock_patch_fail_closed, monkeypatch
):
    """Binding marked available but with empty secret_fields must fail-close the run."""
    scenario = _scenario(ScenarioType.RELIABILITY)
    raw_payload = _payload()
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.httpx.AsyncClient",
        _make_http_client_cm(scenario),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._fetch_provider_runtime_context",
        AsyncMock(
            return_value={
                "providers": [
                    {
                        "capability": "judge",
                        "provider_id": "anthropic:claude-sonnet-4-6",
                        "vendor": "anthropic",
                        "model": "claude-sonnet-4-6",
                        "availability_status": "available",
                        "credential_source": "db_encrypted",
                        "secret_fields": {},
                    }
                ]
            }
        ),
    )
    with pytest.raises(RuntimeError, match="Judge provider runtime binding missing api_key"):
        await judge_run({}, payload=raw_payload)
    mock_patch_fail_closed.assert_awaited_once()
    assert mock_patch_fail_closed.await_args.args[0] == "run_test"


@pytest.mark.asyncio
@patch("botcheck_judge.workers.judge_worker._patch_fail_closed", new_callable=AsyncMock)
async def test_judge_run_invalid_branching_payload_applies_fail_closed_patch(mock_patch_fail_closed):
    raw_payload = _payload()
    raw_payload["scenario_has_branching"] = True
    with pytest.raises(ValueError, match="taken_path_steps"):
        await judge_run({}, payload=raw_payload)
    mock_patch_fail_closed.assert_awaited_once()
    call_args = mock_patch_fail_closed.await_args.args
    assert call_args[0] == "run_test"


@pytest.mark.asyncio
@patch("botcheck_judge.workers.judge_worker._patch_fail_closed", new_callable=AsyncMock)
async def test_judge_run_invalid_ai_payload_applies_fail_closed_patch(mock_patch_fail_closed):
    raw_payload = _payload(scenario_kind="ai", judge_contract_version=2)
    with pytest.raises(ValueError, match="ai_context"):
        await judge_run({}, payload=raw_payload)
    mock_patch_fail_closed.assert_awaited_once()
    call_args = mock_patch_fail_closed.await_args.args
    assert call_args[0] == "run_test"


@pytest.mark.asyncio
async def test_judge_run_restores_parent_context_and_emits_canonical_spans(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("botcheck_judge.workers.judge_worker._tracer", tracer)

    attached: list[dict[str, str]] = []
    detached: list[object | None] = []
    trace_token = object()
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.attach_trace_context_from_carrier",
        lambda carrier: attached.append(dict(carrier)) or trace_token,
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.detach_trace_context",
        lambda token: detached.append(token),
    )

    raw_payload = {
        **_payload(),
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "tracestate": "vendor=test",
    }
    scenario = _scenario(ScenarioType.RELIABILITY)

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _HTTPClient:
        async def get(self, url: str):
            assert url == "/scenarios/test-scenario"
            return _Response(scenario.model_dump(mode="json"))

        async def patch(self, url: str, json: dict):
            assert url == "/runs/run_test"
            assert json["gate_result"] == "passed"
            return _Response({"ok": True})

    class _ClientCM:
        async def __aenter__(self):
            return _HTTPClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    report = RunReport(
        run_id="run_test",
        scenario_id="test-scenario",
        scenario_version_hash="sha256:test",
        bot_endpoint="sip:bot@test.example.com",
        tenant_id="tenant-test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ms=1000,
        overall_status=RunStatus.PASS,
        gate_result=GateResult.PASSED,
        scores={
            "jailbreak": DimensionScore(
                metric_type=MetricType.SCORE,
                score=1.0,
                passed=None,
                status=RunStatus.PASS,
                threshold=0.7,
                gate=True,
                findings=[],
                reasoning="Objective satisfied",
            )
        },
        deterministic={},
        conversation=[],
        all_findings=[],
        judge_model="test-model",
        judge_version="test-version",
    )

    async def _fake_judge_conversation(**kwargs):
        del kwargs
        return report, {"input_tokens": 11, "output_tokens": 7}

    monkeypatch.setattr("botcheck_judge.workers.judge_worker.httpx.AsyncClient", lambda *args, **kwargs: _ClientCM())
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.judge_conversation",
        _fake_judge_conversation,
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._store_report_s3",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.anthropic.AsyncAnthropic",
        lambda api_key: object(),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._fetch_provider_runtime_context",
        AsyncMock(return_value=_judge_runtime_context()),
    )
    monkeypatch.setattr("botcheck_judge.workers.judge_worker.settings.judge_model", "test-model")

    inflight_before = JUDGE_RUNS_INFLIGHT._value.get()
    llm_latency_before = _hist_count(
        JUDGE_LLM_LATENCY_SECONDS,
        model="test-model",
        trigger_source="manual",
    )
    gate_results_before = _counter_value(
        SCENARIO_GATE_RESULTS_TOTAL,
        result="passed",
        scenario_kind="graph",
        trigger_source="manual",
    )

    result = await judge_run({}, payload=raw_payload)

    assert result["gate_result"] == "passed"
    assert JUDGE_RUNS_INFLIGHT._value.get() == inflight_before
    assert (
        _hist_count(
            JUDGE_LLM_LATENCY_SECONDS,
            model="test-model",
            trigger_source="manual",
        )
        == llm_latency_before + 1
    )
    assert (
        _counter_value(
            SCENARIO_GATE_RESULTS_TOTAL,
            result="passed",
            scenario_kind="graph",
            trigger_source="manual",
        )
        == gate_results_before + 1
    )
    assert attached == [
        {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        }
    ]
    assert detached == [trace_token]
    assert [name for name, _attrs in tracer.calls] == [
        SPAN_JUDGE_RUN,
        SPAN_JUDGE_LLM_SCORE,
    ]

    run_attrs = tracer.calls[0][1] or {}
    assert run_attrs == {
        ATTR_RUN_ID: "run_test",
        ATTR_SCENARIO_ID: "test-scenario",
        ATTR_SCENARIO_KIND: "graph",
        ATTR_TENANT_ID: "tenant-test",
        ATTR_TRIGGER_SOURCE: "manual",
        ATTR_JUDGE_CONTRACT_VERSION: 1,
    }
    score_attrs = tracer.calls[1][1] or {}
    assert score_attrs[ATTR_RUN_ID] == "run_test"
    assert score_attrs[ATTR_SCENARIO_ID] == "test-scenario"
    assert score_attrs[ATTR_SCORE_DIMENSION] == "jailbreak"
    assert score_attrs[ATTR_JUDGE_METRIC_TYPE] == "score"
    assert score_attrs[ATTR_JUDGE_STATUS] == "pass"
    assert score_attrs[ATTR_JUDGE_THRESHOLD] == 0.7
    assert score_attrs[ATTR_JUDGE_GATE] is True
    assert score_attrs[ATTR_JUDGE_SCORE] == 1.0


@pytest.mark.asyncio
@patch("botcheck_judge.workers.judge_worker._patch_fail_closed", new_callable=AsyncMock)
async def test_judge_run_restores_inflight_gauge_after_error(
    mock_patch_fail_closed: AsyncMock,
    monkeypatch,
):
    scenario = _scenario(ScenarioType.RELIABILITY)
    raw_payload = _payload()

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _HTTPClient:
        async def get(self, url: str):
            assert url == "/scenarios/test-scenario"
            return _Response(scenario.model_dump(mode="json"))

    class _ClientCM:
        async def __aenter__(self):
            return _HTTPClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _boom(**kwargs):
        del kwargs
        raise RuntimeError("judge exploded")

    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.httpx.AsyncClient",
        lambda *args, **kwargs: _ClientCM(),
    )
    monkeypatch.setattr("botcheck_judge.workers.judge_worker.judge_conversation", _boom)
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.anthropic.AsyncAnthropic",
        lambda api_key: object(),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._fetch_provider_runtime_context",
        AsyncMock(return_value=_judge_runtime_context()),
    )
    monkeypatch.setattr("botcheck_judge.workers.judge_worker.settings.judge_model", "test-model")

    inflight_before = JUDGE_RUNS_INFLIGHT._value.get()
    llm_latency_before = _hist_count(
        JUDGE_LLM_LATENCY_SECONDS,
        model="test-model",
        trigger_source="manual",
    )

    with pytest.raises(RuntimeError, match="judge exploded"):
        await judge_run({}, payload=raw_payload)

    assert JUDGE_RUNS_INFLIGHT._value.get() == inflight_before
    assert (
        _hist_count(
            JUDGE_LLM_LATENCY_SECONDS,
            model="test-model",
            trigger_source="manual",
        )
        == llm_latency_before + 1
    )
    mock_patch_fail_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_judge_run_ai_payload_passes_ai_context_and_disables_multi_sample(monkeypatch):
    captured: dict = {}
    scenario = _scenario(ScenarioType.ADVERSARIAL)
    raw_payload = _payload(
        scenario_kind="ai",
        judge_contract_version=2,
        ai_context={
            "dataset_input": "Caller wants a condo in Queens.",
            "expected_output": "Recommend listings without booking a tour.",
            "persona_id": "persona_real_estate_1",
        },
    )

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _HTTPClient:
        async def get(self, url: str):
            assert url == "/scenarios/test-scenario"
            return _Response(scenario.model_dump(mode="json"))

        async def patch(self, url: str, json: dict):
            captured["patch_payload"] = json
            assert url == "/runs/run_test"
            return _Response({"ok": True})

    class _ClientCM:
        async def __aenter__(self):
            return _HTTPClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_client(*args, **kwargs):
        return _ClientCM()

    report = RunReport(
        run_id="run_test",
        scenario_id="test-scenario",
        scenario_version_hash="sha256:test",
        bot_endpoint="sip:bot@test.example.com",
        tenant_id="tenant-test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ms=1000,
        overall_status=RunStatus.PASS,
        gate_result=GateResult.PASSED,
        scores={
            "jailbreak": DimensionScore(
                metric_type=MetricType.SCORE,
                score=1.0,
                passed=None,
                status=RunStatus.PASS,
                threshold=0.7,
                gate=True,
                findings=[],
                reasoning="Objective satisfied",
            )
        },
        deterministic={},
        conversation=[],
        all_findings=[],
        judge_model="test-model",
        judge_version="test-version",
    )

    async def _fake_judge_conversation(**kwargs):
        captured["ai_context"] = kwargs.get("ai_context")
        captured["multi_sample_judge"] = kwargs.get("multi_sample_judge")
        captured["multi_sample_n"] = kwargs.get("multi_sample_n")
        return report, {"input_tokens": 11, "output_tokens": 7}

    monkeypatch.setattr("botcheck_judge.workers.judge_worker.httpx.AsyncClient", _fake_client)
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.judge_conversation",
        _fake_judge_conversation,
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._store_report_s3",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.anthropic.AsyncAnthropic",
        lambda api_key: object(),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._fetch_provider_runtime_context",
        AsyncMock(return_value=_judge_runtime_context()),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.settings.multi_sample_judge",
        True,
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.settings.multi_sample_judge_n",
        3,
    )

    result = await judge_run({}, payload=raw_payload)
    assert result["gate_result"] == "passed"
    assert captured["ai_context"]["dataset_input"] == raw_payload["ai_context"]["dataset_input"]
    assert captured["ai_context"]["expected_output"] == raw_payload["ai_context"]["expected_output"]
    assert captured["ai_context"]["persona_id"] == raw_payload["ai_context"]["persona_id"]
    assert captured["multi_sample_judge"] is False
    assert captured["multi_sample_n"] == 1
    assert captured["patch_payload"]["gate_result"] == "passed"


@pytest.mark.asyncio
async def test_judge_run_fetches_runtime_context_and_uses_stored_anthropic_key(monkeypatch):
    captured: dict[str, object] = {}
    patch_completed = False
    scenario = _scenario(ScenarioType.RELIABILITY)
    raw_payload = _payload()

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _HTTPClient:
        async def post(self, url: str, json: dict):
            if url == "/providers/internal/runtime-context":
                captured["runtime_context_payload"] = json
                return _Response(
                    {
                        "tenant_id": "tenant-test",
                        "runtime_scope": "judge",
                        "feature_flags": {},
                        "tts": None,
                        "stt": None,
                        "providers": [
                            {
                                "capability": "judge",
                                "vendor": "anthropic",
                                "model": "claude-sonnet-4-6",
                                "provider_id": "anthropic:claude-sonnet-4-6",
                                "credential_source": "db_encrypted",
                                "availability_status": "available",
                                "secret_fields": {"api_key": "stored-anthropic-key"},
                            }
                        ],
                    }
                )
            if url == "/providers/internal/usage":
                assert patch_completed is True
                captured["provider_usage_payload"] = json
                return _Response({"stored": True, "ledger_id": "provusage_test"})
            raise AssertionError(f"unexpected POST {url}")

        async def get(self, url: str):
            assert url == "/scenarios/test-scenario"
            return _Response(scenario.model_dump(mode="json"))

        async def patch(self, url: str, json: dict):
            nonlocal patch_completed
            assert url == "/runs/run_test"
            assert json["gate_result"] == "passed"
            patch_completed = True
            return _Response({"ok": True})

    class _ClientCM:
        async def __aenter__(self):
            return _HTTPClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    report = RunReport(
        run_id="run_test",
        scenario_id="test-scenario",
        scenario_version_hash="sha256:test",
        bot_endpoint="sip:bot@test.example.com",
        tenant_id="tenant-test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ms=1000,
        overall_status=RunStatus.PASS,
        gate_result=GateResult.PASSED,
        scores={},
        deterministic={},
        conversation=[],
        all_findings=[],
        judge_model="claude-sonnet-4-6",
        judge_version="test-version",
    )

    async def _fake_judge_conversation(**kwargs):
        captured["judge_model"] = kwargs.get("model")
        return report, {"input_tokens": 5, "output_tokens": 3}

    def _fake_anthropic_client(*, api_key: str):
        captured["anthropic_api_key"] = api_key
        return object()

    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.httpx.AsyncClient",
        lambda *args, **kwargs: _ClientCM(),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.judge_conversation",
        _fake_judge_conversation,
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker._store_report_s3",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.anthropic.AsyncAnthropic",
        _fake_anthropic_client,
    )
    monkeypatch.setattr("botcheck_judge.workers.judge_worker.settings.anthropic_api_key", "")
    monkeypatch.setattr(
        "botcheck_judge.workers.judge_worker.settings.judge_model",
        "claude-sonnet-4-6",
    )

    result = await judge_run({}, payload=raw_payload)

    assert result["gate_result"] == "passed"
    assert captured["anthropic_api_key"] == "stored-anthropic-key"
    assert captured["judge_model"] == "claude-sonnet-4-6"
    assert captured["runtime_context_payload"] == {
        "tenant_id": "tenant-test",
        "runtime_scope": "judge",
        "provider_bindings": [
            {
                "capability": "judge",
                "model": "claude-sonnet-4-6",
            }
        ],
    }
    assert captured["provider_usage_payload"] == {
        "tenant_id": "tenant-test",
        "provider_id": "anthropic:claude-sonnet-4-6",
        "usage_key": "judge-run:run_test:anthropic:claude-sonnet-4-6",
        "runtime_scope": "judge",
        "capability": "judge",
        "run_id": "run_test",
        "input_tokens": 5,
        "output_tokens": 3,
        "request_count": 1,
    }
    assert patch_completed is True


@pytest.mark.asyncio
@patch("botcheck_judge.workers.scheduler_worker.httpx.AsyncClient")
async def test_tick_schedules_calls_dispatch_due_with_scheduler_auth(mock_client):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "checked": 1,
        "dispatched": 1,
        "throttled": 0,
        "failed": 0,
        "now": "2026-02-27T00:00:00+00:00",
    }

    http = MagicMock()
    http.post = AsyncMock(return_value=response)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=http)
    client_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client.return_value = client_cm

    result = await tick_schedules({})
    assert result["dispatched"] == 1

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    http.post.assert_awaited_once_with(
        "/schedules/dispatch-due",
        json={"limit": 50},
    )


@pytest.mark.asyncio
@patch("botcheck_judge.workers.scheduler_worker.httpx.AsyncClient")
async def test_reap_orphan_runs_calls_reaper_endpoint_with_judge_auth(mock_client):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "dry_run": False,
        "checked": 3,
        "overdue": 2,
        "closed": 2,
        "room_active": 1,
        "room_missing": 1,
        "livekit_errors": 0,
        "sip_slots_released": 1,
        "close_errors": 0,
    }

    http = MagicMock()
    http.post = AsyncMock(return_value=response)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=http)
    client_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client.return_value = client_cm

    result = await reap_orphan_runs({})
    assert result["closed"] == 2

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    http.post.assert_awaited_once_with(
        "/runs/reaper/sweep",
        json={"dry_run": False, "limit": 200, "grace_s": 60.0},
    )


@pytest.mark.asyncio
async def test_reap_orphan_runs_disabled_returns_disabled(monkeypatch):
    monkeypatch.setattr("botcheck_judge.workers.scheduler_worker.settings.run_reaper_enabled", False)
    result = await reap_orphan_runs({})
    assert result == {"disabled": True}


@pytest.mark.asyncio
@patch("botcheck_judge.workers.scheduler_worker.httpx.AsyncClient")
async def test_dispatch_pack_run_calls_internal_api_with_scheduler_auth(mock_client):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "pack_run_id": "packrun_123",
        "found": True,
        "applied": True,
        "state": "running",
        "reason": "applied",
    }

    http = MagicMock()
    http.post = AsyncMock(return_value=response)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=http)
    client_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client.return_value = client_cm

    result = await dispatch_pack_run({}, payload={"pack_run_id": "packrun_123"})
    assert result["applied"] is True

    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    http.post.assert_awaited_once_with("/packs/internal/packrun_123/dispatch")
