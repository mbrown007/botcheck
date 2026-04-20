from __future__ import annotations

import httpx

from botcheck_api import metrics as api_metrics
from botcheck_api.grai.observability import (
    classify_http_error,
    diagnostic_feature_names,
    observe_artifact_upload,
    observe_assertion_rows,
    observe_import,
    observe_report_request,
    observe_run_create,
    observe_run_enqueue,
    observe_run_terminal,
)
from botcheck_api.grai.service_models import GraiImportDiagnostic


def test_observe_import_records_counter_and_histogram() -> None:
    total_before = api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="success")._value.get()
    latency_before = api_metrics.GRAI_EVAL_IMPORT_LATENCY_SECONDS.labels(outcome="success")._sum.get()

    observe_import(outcome="success", elapsed_s=0.12)

    assert api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="success")._value.get() == total_before + 1
    assert (
        api_metrics.GRAI_EVAL_IMPORT_LATENCY_SECONDS.labels(outcome="success")._sum.get()
        > latency_before
    )


def test_observe_assertion_rows_increments_pass_and_fail_by_type() -> None:
    passed_before = api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(
        assertion_type="contains",
        outcome="passed",
    )._value.get()
    failed_before = api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(
        assertion_type="llm-rubric",
        outcome="failed",
    )._value.get()

    observe_assertion_rows(
        [
            {"assertion_type": "contains", "passed": True},
            {"assertion_type": "llm-rubric", "passed": False},
        ]
    )

    assert (
        api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(assertion_type="contains", outcome="passed")._value.get()
        == passed_before + 1
    )
    assert (
        api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(assertion_type="llm-rubric", outcome="failed")._value.get()
        == failed_before + 1
    )


def test_observability_helpers_cover_artifact_enqueue_report_and_terminal_paths() -> None:
    artifact_before = api_metrics.GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL.labels(outcome="error")._value.get()
    enqueue_total_before = api_metrics.GRAI_EVAL_RUN_ENQUEUE_TOTAL.labels(outcome="success")._value.get()
    enqueue_sum_before = api_metrics.GRAI_EVAL_RUN_ENQUEUE_LATENCY_SECONDS.labels(outcome="success")._sum.get()
    create_before = api_metrics.GRAI_EVAL_RUN_CREATE_TOTAL.labels(outcome="success")._value.get()
    terminal_before = api_metrics.GRAI_EVAL_RUNS_TOTAL.labels(outcome="cancelled")._value.get()
    report_before = api_metrics.GRAI_EVAL_REPORT_REQUESTS_TOTAL.labels(
        endpoint="report",
        outcome="success",
    )._value.get()

    observe_artifact_upload(outcome="error")
    observe_run_enqueue(outcome="success", elapsed_s=0.03)
    observe_run_create(outcome="success")
    observe_run_terminal(outcome="cancelled")
    observe_report_request(endpoint="report", outcome="success", elapsed_s=0.04)

    assert api_metrics.GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL.labels(outcome="error")._value.get() == artifact_before + 1
    assert api_metrics.GRAI_EVAL_RUN_ENQUEUE_TOTAL.labels(outcome="success")._value.get() == enqueue_total_before + 1
    assert api_metrics.GRAI_EVAL_RUN_ENQUEUE_LATENCY_SECONDS.labels(outcome="success")._sum.get() > enqueue_sum_before
    assert api_metrics.GRAI_EVAL_RUN_CREATE_TOTAL.labels(outcome="success")._value.get() == create_before + 1
    assert api_metrics.GRAI_EVAL_RUNS_TOTAL.labels(outcome="cancelled")._value.get() == terminal_before + 1
    assert (
        api_metrics.GRAI_EVAL_REPORT_REQUESTS_TOTAL.labels(endpoint="report", outcome="success")._value.get()
        == report_before + 1
    )


def test_classify_http_error_maps_timeout_and_status_classes() -> None:
    timeout = classify_http_error(TimeoutError("late"))
    response = httpx.Response(status_code=502)
    request = httpx.Request("POST", "https://bot.internal/http")
    status = classify_http_error(httpx.HTTPStatusError("bad", request=request, response=response))

    assert timeout == "timeout"
    assert status == "http_status"


def test_classify_http_error_maps_transport_error() -> None:
    exc = httpx.ConnectError("connection refused")
    assert classify_http_error(exc) == "transport_error"


def test_classify_http_error_fallback_uses_type_name() -> None:
    exc = ValueError("unexpected value")
    assert classify_http_error(exc) == "valueerror"


def test_observe_assertion_rows_emits_error_for_none_passed() -> None:
    before = api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(
        assertion_type="llm-rubric",
        outcome="error",
    )._value.get()

    observe_assertion_rows([{"assertion_type": "llm-rubric", "passed": None}])

    assert (
        api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(assertion_type="llm-rubric", outcome="error")._value.get()
        == before + 1
    )


def test_diagnostic_feature_names_deduplicates_and_sorts() -> None:
    diags = [
        GraiImportDiagnostic(feature_name="routing", message="ok", path="f"),
        GraiImportDiagnostic(feature_name="routing", message="dup", path="f"),
        GraiImportDiagnostic(feature_name="policy", message="ok", path="f"),
    ]
    assert diagnostic_feature_names(diags) == ["policy", "routing"]


def test_diagnostic_feature_names_strips_whitespace() -> None:
    diags = [
        GraiImportDiagnostic(feature_name="  routing  ", message="ok", path="f"),
        GraiImportDiagnostic(feature_name="routing", message="dup", path="f"),
    ]
    assert diagnostic_feature_names(diags) == ["routing"]


def test_diagnostic_feature_names_skips_none_and_blank() -> None:
    diags = [
        GraiImportDiagnostic(feature_name=None, message="no name", path="f"),
        GraiImportDiagnostic(feature_name="   ", message="blank", path="f"),
        GraiImportDiagnostic(feature_name="policy", message="ok", path="f"),
    ]
    assert diagnostic_feature_names(diags) == ["policy"]
