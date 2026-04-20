from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from botcheck_api import database, metrics as api_metrics
from botcheck_api.config import settings
from botcheck_api.grai.service_models import GraiEvalRunDestinationSnapshot
from botcheck_api.grai.eval_worker import PairEvaluationResult, _evaluate_pair, run_grai_eval
from botcheck_api.models import GraiEvalRunStatus


def _run_row() -> SimpleNamespace:
    return SimpleNamespace(
        eval_run_id="gerun_worker",
        tenant_id="default",
        suite_id="gesuite_worker",
        transport_profile_id="dest_http_worker",
        endpoint_at_start="https://bot.internal/chat",
        headers_at_start={"Authorization": "Bearer worker-token"},
        direct_http_config_at_start={"request_text_field": "message", "response_text_field": "response"},
        status=GraiEvalRunStatus.PENDING.value,
        total_pairs=1,
    )


def _run_row_with_total_pairs(total_pairs: int) -> SimpleNamespace:
    row = _run_row()
    row.total_pairs = total_pairs
    return row


def _prompt(prompt_id: str) -> SimpleNamespace:
    return SimpleNamespace(prompt_id=prompt_id, prompt_text="Answer clearly: {{question}}")


def _case(case_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        case_id=case_id,
        description=f"Case {case_id}",
        vars_json={"question": "What is the refund policy?"},
        assert_json=[
            {
                "assertion_type": "contains",
                "raw_value": "refund",
                "threshold": 0.8,
                "weight": 1.0,
            }
        ],
        tags_json=["billing"],
        metadata_json={},
    )


def _destination(destination_index: int, transport_profile_id: str) -> GraiEvalRunDestinationSnapshot:
    return GraiEvalRunDestinationSnapshot(
        destination_index=destination_index,
        transport_profile_id=transport_profile_id,
        label=transport_profile_id,
        protocol="http",
        endpoint_at_start=f"https://{transport_profile_id}.internal/chat",
        headers_at_start={"Authorization": f"Bearer {transport_profile_id}"},
        direct_http_config_at_start={"request_text_field": "message", "response_text_field": "response"},
    )


@pytest.mark.asyncio
async def test_run_grai_eval_marks_complete_when_pairs_pass(monkeypatch) -> None:
    persist_mock = AsyncMock()
    evaluate_pair_mock = AsyncMock(return_value=PairEvaluationResult(pair_failed=False))
    client = SimpleNamespace(aclose=AsyncMock())

    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._load_run_state",
        AsyncMock(
            return_value=(
                _run_row(),
                [_prompt("geprompt_1")],
                [_case("gecase_1")],
                [_destination(0, "dest_http_worker")],
                {},
            )
        ),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._persist_progress", persist_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker._is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr("botcheck_api.grai.eval_worker._evaluate_pair", evaluate_pair_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.DirectHTTPBotClient", lambda context: client)
    monkeypatch.setattr(database, "AsyncSessionLocal", object())
    monkeypatch.setattr(settings, "eval_concurrency_limit", 1)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await run_grai_eval({}, payload={"eval_run_id": "gerun_worker", "tenant_id": "default"})

    assert result == {
        "status": "complete",
        "terminal_outcome": "passed",
        "eval_run_id": "gerun_worker",
        "dispatched_count": 1,
        "completed_count": 1,
        "failed_count": 0,
    }
    assert evaluate_pair_mock.await_count == 1
    assert client.aclose.await_count == 1
    assert persist_mock.await_args_list[-1].kwargs["status"] == "complete"
    assert persist_mock.await_args_list[-1].kwargs["terminal_outcome"] == "passed"


@pytest.mark.asyncio
async def test_run_grai_eval_stops_after_cancel_between_batches(monkeypatch) -> None:
    persist_mock = AsyncMock()
    evaluate_pair_mock = AsyncMock(return_value=PairEvaluationResult(pair_failed=False))
    client = SimpleNamespace(aclose=AsyncMock())

    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._load_run_state",
        AsyncMock(
            return_value=(
                _run_row_with_total_pairs(2),
                [_prompt("geprompt_1")],
                [_case("gecase_1"), _case("gecase_2")],
                [_destination(0, "dest_http_worker")],
                {},
            )
        ),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._persist_progress", persist_mock)
    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._is_cancelled",
        AsyncMock(side_effect=[False, True]),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._evaluate_pair", evaluate_pair_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.DirectHTTPBotClient", lambda context: client)
    monkeypatch.setattr(database, "AsyncSessionLocal", object())
    monkeypatch.setattr(settings, "eval_concurrency_limit", 1)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await run_grai_eval({}, payload={"eval_run_id": "gerun_worker", "tenant_id": "default"})

    assert result == {
        "status": "cancelled",
        "terminal_outcome": "cancelled",
        "eval_run_id": "gerun_worker",
        "dispatched_count": 1,
        "completed_count": 1,
        "failed_count": 0,
    }
    assert evaluate_pair_mock.await_count == 1
    assert client.aclose.await_count == 1
    assert persist_mock.await_args_list[-1].kwargs["status"] == "cancelled"
    assert persist_mock.await_args_list[-1].kwargs["terminal_outcome"] == "cancelled"


@pytest.mark.asyncio
async def test_run_grai_eval_fails_job_when_pair_result_write_raises(monkeypatch) -> None:
    persist_mock = AsyncMock()
    client = SimpleNamespace(aclose=AsyncMock())
    write_error = RuntimeError("result write failed")

    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._load_run_state",
        AsyncMock(
            return_value=(
                _run_row(),
                [_prompt("geprompt_1")],
                [_case("gecase_1")],
                [_destination(0, "dest_http_worker")],
                {},
            )
        ),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._persist_progress", persist_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker._is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._evaluate_pair",
        AsyncMock(side_effect=write_error),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker.DirectHTTPBotClient", lambda context: client)
    monkeypatch.setattr(database, "AsyncSessionLocal", object())
    monkeypatch.setattr(settings, "eval_concurrency_limit", 1)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    with pytest.raises(RuntimeError, match="result write failed"):
        await run_grai_eval({}, payload={"eval_run_id": "gerun_worker", "tenant_id": "default"})

    assert client.aclose.await_count == 1
    assert persist_mock.await_args_list[-1].kwargs == {
        "status": "failed",
        "terminal_outcome": "execution_failed",
        "dispatched_count": 1,
        "completed_count": 0,
        "failed_count": 0,
    }


@pytest.mark.asyncio
async def test_run_grai_eval_marks_assertion_failed_when_pairs_fail(monkeypatch) -> None:
    persist_mock = AsyncMock()
    evaluate_pair_mock = AsyncMock(return_value=PairEvaluationResult(pair_failed=True))
    client = SimpleNamespace(aclose=AsyncMock())

    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._load_run_state",
        AsyncMock(
            return_value=(
                _run_row(),
                [_prompt("geprompt_1")],
                [_case("gecase_1")],
                [_destination(0, "dest_http_worker")],
                {},
            )
        ),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._persist_progress", persist_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker._is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr("botcheck_api.grai.eval_worker._evaluate_pair", evaluate_pair_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.DirectHTTPBotClient", lambda context: client)
    monkeypatch.setattr(database, "AsyncSessionLocal", object())
    monkeypatch.setattr(settings, "eval_concurrency_limit", 1)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await run_grai_eval({}, payload={"eval_run_id": "gerun_worker", "tenant_id": "default"})

    assert result == {
        "status": "failed",
        "terminal_outcome": "assertion_failed",
        "eval_run_id": "gerun_worker",
        "dispatched_count": 1,
        "completed_count": 0,
        "failed_count": 1,
    }
    assert persist_mock.await_args_list[-1].kwargs["status"] == "failed"
    assert persist_mock.await_args_list[-1].kwargs["terminal_outcome"] == "assertion_failed"


@pytest.mark.asyncio
async def test_evaluate_pair_records_assertion_and_artifact_metrics_when_s3_disabled(monkeypatch) -> None:
    @asynccontextmanager
    async def session_stub(_tenant_id: str, *, readonly: bool = False):
        del readonly
        yield object()

    replace_mock = AsyncMock()
    client = SimpleNamespace(
        respond=AsyncMock(return_value=SimpleNamespace(text="You can request a refund within 30 days.", latency_ms=321))
    )
    rate_limiter = SimpleNamespace(wait_turn=AsyncMock())
    payload = SimpleNamespace(eval_run_id="gerun_worker", tenant_id="default")
    run_row = _run_row()
    pair = SimpleNamespace(prompt=_prompt("geprompt_metric"), case=_case("gecase_metric"))
    pair.destination = _destination(1, "dest_http_metric")

    passed_before = api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(
        assertion_type="contains",
        outcome="passed",
    )._value.get()
    skipped_before = api_metrics.GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL.labels(outcome="skipped")._value.get()

    monkeypatch.setattr("botcheck_api.grai.eval_worker._session_for_tenant", session_stub)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.replace_grai_eval_pair_results", replace_mock)
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_access_key", "")
    monkeypatch.setattr(settings, "s3_secret_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await _evaluate_pair(
        payload=payload,
        run_row=run_row,
        pair=pair,
        client=client,
        rate_limiter=rate_limiter,
        anthropic_client=None,
        llm_model="claude-sonnet-4-6",
        judge_provider_id=None,
    )

    assert result.pair_failed is False
    assert rate_limiter.wait_turn.await_count == 1
    assert replace_mock.await_count == 1
    assert (
        api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(assertion_type="contains", outcome="passed")._value.get()
        == passed_before + 1
    )
    assert api_metrics.GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL.labels(outcome="skipped")._value.get() == skipped_before + 1


@pytest.mark.asyncio
async def test_evaluate_pair_passes_case_http_request_context_to_client(monkeypatch) -> None:
    @asynccontextmanager
    async def session_stub(_tenant_id: str, *, readonly: bool = False):
        del readonly
        yield object()

    replace_mock = AsyncMock()
    client = SimpleNamespace(
        respond=AsyncMock(return_value=SimpleNamespace(text="Investigate checkout latency and error rate first.", latency_ms=210))
    )
    rate_limiter = SimpleNamespace(wait_turn=AsyncMock())
    payload = SimpleNamespace(eval_run_id="gerun_worker", tenant_id="default")
    run_row = _run_row()
    pair = SimpleNamespace(prompt=_prompt("geprompt_metric"), case=_case("gecase_metric"))
    pair.case.metadata_json = {
        "http_request_context": {
            "dashboard_context": {
                "uid": "checkout-incident",
                "time_range": {"from": "now-15m", "to": "now"},
            },
            "selected_context": [
                {"type": "metric", "id": "http_requests_total", "display_name": "Checkout Errors"}
            ],
        }
    }
    pair.destination = _destination(1, "dest_http_metric")

    monkeypatch.setattr("botcheck_api.grai.eval_worker._session_for_tenant", session_stub)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.replace_grai_eval_pair_results", replace_mock)
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_access_key", "")
    monkeypatch.setattr(settings, "s3_secret_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await _evaluate_pair(
        payload=payload,
        run_row=run_row,
        pair=pair,
        client=client,
        rate_limiter=rate_limiter,
        anthropic_client=None,
        llm_model="claude-sonnet-4-6",
        judge_provider_id=None,
    )

    assert result.pair_failed is True
    assert client.respond.await_count == 1
    assert client.respond.await_args.kwargs["request_context"] == {
        "dashboard_context": {
            "uid": "checkout-incident",
            "time_range": {"from": "now-15m", "to": "now"},
        },
        "selected_context": [
            {"type": "metric", "id": "http_requests_total", "display_name": "Checkout Errors"}
        ],
    }


@pytest.mark.asyncio
async def test_run_grai_eval_dispatches_each_pair_to_each_destination(monkeypatch) -> None:
    persist_mock = AsyncMock()
    evaluate_pair_mock = AsyncMock(return_value=PairEvaluationResult(pair_failed=False))
    client_a = SimpleNamespace(aclose=AsyncMock())
    client_b = SimpleNamespace(aclose=AsyncMock())
    created_contexts: list[str] = []

    def _client_factory(*, context):
        created_contexts.append(context.transport_profile_id)
        if context.transport_profile_id == "dest_http_a":
            return client_a
        return client_b

    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker._load_run_state",
        AsyncMock(
            return_value=(
                _run_row_with_total_pairs(2),
                [_prompt("geprompt_1")],
                [_case("gecase_1")],
                [
                    _destination(0, "dest_http_a"),
                    _destination(1, "dest_http_b"),
                ],
                {},
            )
        ),
    )
    monkeypatch.setattr("botcheck_api.grai.eval_worker._persist_progress", persist_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker._is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr("botcheck_api.grai.eval_worker._evaluate_pair", evaluate_pair_mock)
    monkeypatch.setattr("botcheck_api.grai.eval_worker.DirectHTTPBotClient", _client_factory)
    monkeypatch.setattr(database, "AsyncSessionLocal", object())
    monkeypatch.setattr(settings, "eval_concurrency_limit", 2)
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = await run_grai_eval({}, payload={"eval_run_id": "gerun_worker", "tenant_id": "default"})

    assert result == {
        "status": "complete",
        "terminal_outcome": "passed",
        "eval_run_id": "gerun_worker",
        "dispatched_count": 2,
        "completed_count": 2,
        "failed_count": 0,
    }
    assert created_contexts == ["dest_http_a", "dest_http_b"]
    assert evaluate_pair_mock.await_count == 2
    assert client_a.aclose.await_count == 1
    assert client_b.aclose.await_count == 1
