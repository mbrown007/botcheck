from __future__ import annotations

import time
from typing import Callable

from botcheck_observability.circuit_breaker import (
    PROVIDER_CIRCUIT_REJECTIONS_TOTAL,
    PROVIDER_CIRCUIT_STATE,
    PROVIDER_CIRCUIT_TRANSITIONS_TOTAL,
)
from botcheck_observability.helpers import (
    counter as _counter,
    gauge as _gauge,
    histogram as _histogram,
)
from botcheck_observability.provider import (
    LLM_TOKENS_TOTAL,
    PROVIDER_API_CALLS_TOTAL,
    STT_SECONDS_TOTAL,
    TELEPHONY_MINUTES_TOTAL,
    TTS_CHARACTERS_TOTAL,
    TTS_PREVIEW_REQUESTS_TOTAL,
)
from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


HTTP_REQUESTS_TOTAL = _counter(
    "botcheck_api_http_requests_total",
    "Total HTTP requests handled by the API service.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = _histogram(
    "botcheck_api_http_request_duration_seconds",
    "HTTP request duration for API endpoints.",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

RUNS_CREATED_TOTAL = _counter(
    "botcheck_runs_created_total",
    "Total runs created by source and transport.",
    ["trigger_source", "transport"],
)

RUN_STATE_TRANSITIONS_TOTAL = _counter(
    "botcheck_run_state_transitions_total",
    "Total run state transitions.",
    ["from_state", "to_state", "source"],
)

RUN_TURNS_RECORDED_TOTAL = _counter(
    "botcheck_run_turns_recorded_total",
    "Total conversation turns recorded by speaker.",
    ["speaker"],
)

JUDGE_ENQUEUE_TOTAL = _counter(
    "botcheck_judge_enqueue_total",
    "Judge enqueue attempts and outcomes.",
    ["outcome"],
)

RUN_FAILURES_TOTAL = _counter(
    "botcheck_run_failures_total",
    "Run failures by source and error code.",
    ["source", "error_code"],
)

JUDGE_PATCH_TOTAL = _counter(
    "botcheck_judge_patch_total",
    "Judge patch calls by gate/error result.",
    ["gate_result", "error_code"],
)

SIP_DISPATCH_TOTAL = _counter(
    "botcheck_sip_dispatch_total",
    "SIP dispatch attempts and outcomes.",
    ["outcome"],  # success, throttled, error
)

SIP_DISPATCH_ERRORS_TOTAL = _counter(
    "botcheck_sip_dispatch_errors_total",
    "SIP dispatch failures broken down by error class.",
    ["error_class"],
    # error_class values:
    #   allowlist_unconfigured – SIP_DESTINATION_ALLOWLIST is empty
    #   allowlist_rejected     – endpoint host not in allowlist
    #   credential_error       – SIP credentials failed to load
    #   livekit_api_error      – LiveKit SIP API call raised an exception
)

SIP_SLOTS_ACTIVE = _gauge(
    "botcheck_sip_slots_active",
    "Current number of active (slot-held) outbound SIP calls.",
    [],
)

SIP_ANSWER_LATENCY_SECONDS = _histogram(
    "botcheck_sip_answer_latency_seconds",
    "Latency from run creation to first active harness signal for SIP runs.",
    ["trunk_id"],
    buckets=(0.5, 1, 2, 3, 5, 8, 12, 20, 30, 45, 60),
)

SCHEDULES_DISPATCH_TOTAL = _counter(
    "botcheck_schedules_dispatch_total",
    "Total schedule dispatch attempts and outcomes.",
    ["outcome"],  # dispatched, throttled, failed
)

SCHEDULE_RUN_OUTCOMES_TOTAL = _counter(
    "botcheck_schedule_run_outcomes_total",
    "Terminal outcomes for scheduled scenario runs.",
    ["outcome", "schedule_id", "target_type"],  # success, failed, error
)

SCHEDULE_RETRY_TOTAL = _counter(
    "botcheck_schedule_retry_total",
    "Automatic schedule retry attempts and outcomes.",
    ["outcome"],  # dispatched, skipped, failed
)

SCHEDULE_CONSECUTIVE_FAILURES = _gauge(
    "botcheck_schedule_consecutive_failures",
    "Current consecutive terminal failure streak per schedule.",
    ["schedule_id", "target_type"],
)

AUTH_ATTEMPTS_TOTAL = _counter(
    "botcheck_auth_attempts_total",
    "Total authentication attempts by outcome and stage.",
    ["stage", "outcome"],  # stage: login, totp; outcome: success, failure, rate_limited, locked
)

AUTH_TOTP_ACTIONS_TOTAL = _counter(
    "botcheck_auth_totp_actions_total",
    "Total TOTP enrollment and management actions.",
    ["action", "outcome"],  # action: enroll_start, enroll_confirm, reset; outcome: success, failure
)

RUN_HEARTBEATS_TOTAL = _counter(
    "botcheck_run_heartbeats_total",
    "Run heartbeat callback outcomes.",
    ["outcome"],  # updated, duplicate_or_stale, ignored_terminal, invalid_state
)

RUN_HEARTBEAT_LAG_SECONDS = _histogram(
    "botcheck_run_heartbeat_lag_seconds",
    "Lag between agent heartbeat sent_at and API receive timestamp.",
    ["outcome"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

RUN_REAPER_ACTIONS_TOTAL = _counter(
    "botcheck_run_reaper_actions_total",
    "Run reaper reconciliation outcomes.",
    ["outcome"],  # not_overdue, heartbeat_stale, room_active, room_missing, closed, livekit_error, close_error
)

RUN_QUEUE_DEPTH = _gauge(
    "botcheck_run_queue_depth",
    "Current ARQ queue depth by queue name.",
    ["queue"],
)

RUN_E2E_LATENCY_SECONDS = _histogram(
    "botcheck_run_e2e_latency_seconds",
    "End-to-end latency from run creation to terminal judge patch.",
    ["scenario_kind", "trigger_source"],
    buckets=(1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180, 300, 600),
)

GRAI_EVAL_RUN_CREATE_TOTAL = _counter(
    "botcheck_grai_eval_run_create_total",
    "Grai eval run creation attempts by outcome.",
    ["outcome"],
)

GRAI_EVAL_IMPORT_TOTAL = _counter(
    "botcheck_grai_eval_import_total",
    "Grai eval promptfoo import attempts by outcome.",
    ["outcome"],
)

GRAI_EVAL_IMPORT_LATENCY_SECONDS = _histogram(
    "botcheck_grai_eval_import_latency_seconds",
    "Latency to compile and persist imported grai eval suites.",
    ["outcome"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

GRAI_EVAL_RUN_ENQUEUE_TOTAL = _counter(
    "botcheck_grai_eval_run_enqueue_total",
    "Grai eval run enqueue attempts by outcome.",
    ["outcome"],
)

GRAI_EVAL_RUN_ENQUEUE_LATENCY_SECONDS = _histogram(
    "botcheck_grai_eval_run_enqueue_latency_seconds",
    "ARQ enqueue latency for grai eval runs.",
    ["outcome"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

GRAI_EVAL_RUNS_INFLIGHT = _gauge(
    "botcheck_grai_eval_runs_inflight",
    "Number of grai eval runs currently executing.",
    [],
)

GRAI_EVAL_RUNS_TOTAL = _counter(
    "botcheck_grai_eval_runs_total",
    "Terminal grai eval run outcomes.",
    ["outcome"],
)

GRAI_EVAL_DISPATCH_LATENCY_SECONDS = _histogram(
    "botcheck_grai_eval_dispatch_latency_seconds",
    "Latency to execute one grai eval prompt/case pair.",
    ["outcome"],
    buckets=(0.05, 0.1, 0.2, 0.4, 0.8, 1.2, 2, 3, 5, 8, 12, 20, 30, 45, 60),
)

GRAI_EVAL_HTTP_ERRORS_TOTAL = _counter(
    "botcheck_grai_eval_http_errors_total",
    "Grai eval HTTP execution errors by class.",
    ["error_class"],
)

GRAI_EVAL_ASSERTIONS_TOTAL = _counter(
    "botcheck_grai_eval_assertions_total",
    "Per-assertion grai eval outcomes by type.",
    ["assertion_type", "outcome"],
)

GRAI_EVAL_ARTIFACT_UPLOAD_TOTAL = _counter(
    "botcheck_grai_eval_artifact_upload_total",
    "Grai eval raw artifact upload outcomes.",
    ["outcome"],
)

GRAI_EVAL_REPORT_REQUESTS_TOTAL = _counter(
    "botcheck_grai_eval_report_requests_total",
    "Grai eval report and results requests by endpoint and outcome.",
    ["endpoint", "outcome"],
)

GRAI_EVAL_REPORT_ASSEMBLY_LATENCY_SECONDS = _histogram(
    "botcheck_grai_eval_report_assembly_latency_seconds",
    "Latency to assemble grai eval report and paginated result responses.",
    ["endpoint", "outcome"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

PROVIDER_USAGE_LEDGER_WRITES_TOTAL = _counter(
    "botcheck_provider_usage_ledger_writes_total",
    "Provider usage ledger write attempts by outcome, scope, capability, and source.",
    ["outcome", "runtime_scope", "capability", "source"],
)

PROVIDER_QUOTA_DECISIONS_TOTAL = _counter(
    "botcheck_provider_quota_decisions_total",
    "Provider quota preflight decisions by outcome, scope, capability, and source.",
    ["outcome", "runtime_scope", "capability", "source"],
)

def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def route_path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    return request.url.path


async def instrument_http(
    request: Request,
    call_next: Callable[[Request], Response],
) -> Response:
    if request.url.path == "/metrics":
        return await call_next(request)
    method = request.method
    path = route_path_label(request)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - started
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path=path,
            status_code=str(status_code),
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(elapsed)
