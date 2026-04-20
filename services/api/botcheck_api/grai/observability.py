from __future__ import annotations

import asyncio
import httpx
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from .. import metrics as api_metrics
from .service_models import GraiImportDiagnostic


def observe_import(*, outcome: str, elapsed_s: float) -> None:
    api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome=outcome).inc()
    api_metrics.GRAI_EVAL_IMPORT_LATENCY_SECONDS.labels(outcome=outcome).observe(elapsed_s)


def observe_report_request(*, endpoint: str, outcome: str, elapsed_s: float) -> None:
    api_metrics.GRAI_EVAL_REPORT_REQUESTS_TOTAL.labels(endpoint=endpoint, outcome=outcome).inc()
    api_metrics.GRAI_EVAL_REPORT_ASSEMBLY_LATENCY_SECONDS.labels(
        endpoint=endpoint,
        outcome=outcome,
    ).observe(elapsed_s)


def observe_run_create(*, outcome: str) -> None:
    api_metrics.GRAI_EVAL_RUN_CREATE_TOTAL.labels(outcome=outcome).inc()


def observe_run_enqueue(*, outcome: str, elapsed_s: float) -> None:
    api_metrics.GRAI_EVAL_RUN_ENQUEUE_TOTAL.labels(outcome=outcome).inc()
    api_metrics.GRAI_EVAL_RUN_ENQUEUE_LATENCY_SECONDS.labels(outcome=outcome).observe(elapsed_s)


def observe_run_terminal(*, outcome: str) -> None:
    api_metrics.GRAI_EVAL_RUNS_TOTAL.labels(outcome=outcome).inc()


def observe_dispatch(*, outcome: str, elapsed_s: float) -> None:
    api_metrics.GRAI_EVAL_DISPATCH_LATENCY_SECONDS.labels(outcome=outcome).observe(elapsed_s)


def classify_http_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_status"
    if isinstance(exc, httpx.TransportError):
        return "transport_error"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    return type(exc).__name__.lower()


def observe_http_error(exc: BaseException) -> None:
    api_metrics.GRAI_EVAL_HTTP_ERRORS_TOTAL.labels(error_class=classify_http_error(exc)).inc()


def observe_assertion_rows(rows: Iterable[Mapping[str, Any] | BaseModel]) -> None:
    for row in rows:
        if isinstance(row, BaseModel):
            row = row.model_dump()
        assertion_type = str(row.get("assertion_type") or "unknown").strip() or "unknown"
        passed = row.get("passed")
        if passed is True:
            outcome = "passed"
        elif passed is None:
            outcome = "error"
        else:
            outcome = "failed"
        api_metrics.GRAI_EVAL_ASSERTIONS_TOTAL.labels(
            assertion_type=assertion_type,
            outcome=outcome,
        ).inc()


def observe_artifact_upload(*, outcome: str) -> None:
    api_metrics.GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL.labels(outcome=outcome).inc()


def diagnostic_feature_names(diagnostics: Iterable[GraiImportDiagnostic]) -> list[str]:
    names = sorted(
        {
            item.feature_name.strip()
            for item in diagnostics
            if item.feature_name and item.feature_name.strip()
        }
    )
    return names
