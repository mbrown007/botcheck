from __future__ import annotations

import logging

from botcheck_observability.circuit_breaker import (
    PROVIDER_CIRCUIT_REJECTIONS_TOTAL,
    PROVIDER_CIRCUIT_STATE,
    PROVIDER_CIRCUIT_TRANSITIONS_TOTAL,
    set_provider_circuit_state,
)
from botcheck_observability.helpers import (
    counter as _counter,
    gauge as _gauge,
    histogram as _histogram,
)
from botcheck_observability.provider import LLM_TOKENS_TOTAL, PROVIDER_API_CALLS_TOTAL
from prometheus_client import start_http_server

from .config import settings

logger = logging.getLogger("botcheck.judge.metrics")
_METRICS_SERVER_STARTED = False


JUDGE_RUNS_TOTAL = _counter(
    "botcheck_judge_runs_total",
    "Judge run outcomes by trigger source.",
    ["outcome", "trigger_source", "error_code"],
)

JUDGE_RUN_DURATION_SECONDS = _histogram(
    "botcheck_judge_run_duration_seconds",
    "Judge run duration in seconds.",
    ["outcome", "trigger_source"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80),
)

JUDGE_LLM_LATENCY_SECONDS = _histogram(
    "botcheck_judge_llm_latency_seconds",
    "Judge LLM scoring latency in seconds.",
    ["model", "trigger_source"],
    buckets=(0.5, 1, 2, 3, 5, 8, 12, 20, 30),
)

JUDGE_RUNS_INFLIGHT = _gauge(
    "botcheck_judge_runs_inflight",
    "Current number of in-flight judge runs.",
    [],
)

SCENARIO_GATE_RESULTS_TOTAL = _counter(
    "botcheck_scenario_gate_results_total",
    "Scenario gate results by scenario kind and trigger source.",
    ["result", "scenario_kind", "trigger_source"],
)

TTS_CACHE_WARM_LATENCY_SECONDS = _histogram(
    "botcheck_tts_cache_warm_latency_seconds",
    "TTS cache warm job duration in seconds.",
    ["outcome"],  # warm, partial, cold, error
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 120, 180, 300, 600),
)

VOICE_QUALITY_RUNS_TOTAL = _counter(
    "botcheck_voice_quality_runs_total",
    "Voice-quality classification from deterministic timing thresholds.",
    ["result", "trigger_source"],
)

VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL = _counter(
    "botcheck_voice_quality_threshold_breaches_total",
    "Voice-quality threshold breaches by metric and severity.",
    ["metric", "severity", "trigger_source"],
)

VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS = _gauge(
    "botcheck_voice_quality_p95_response_gap_milliseconds",
    "Latest computed p95 TTFW in milliseconds from harness stop to bot first word.",
    ["trigger_source"],
)

VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT = _histogram(
    "botcheck_voice_quality_interruption_recovery_pct",
    "Observed interruption recovery percentage.",
    ["trigger_source"],
    buckets=(0.001, 50, 70, 80, 85, 90, 95, 98, 100),
)

VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT = _histogram(
    "botcheck_voice_quality_turn_taking_efficiency_pct",
    "% of bot responses where TTFW was within the configured pause threshold.",
    ["trigger_source"],
    buckets=(0.001, 50, 70, 80, 85, 90, 95, 98, 100),
)

def observe_voice_quality_thresholds(
    *,
    trigger_source: str,
    p95_response_gap_ms: int | None,
    interruption_recovery_pct: float | None,
    turn_taking_efficiency_pct: float | None,
    timing_gate_p95_response_gap_ms: int,
    timing_warn_p95_response_gap_ms: int,
    timing_gate_interruption_recovery_pct: float,
    timing_warn_interruption_recovery_pct: float,
    timing_gate_turn_taking_efficiency_pct: float,
    timing_warn_turn_taking_efficiency_pct: float,
) -> str:
    failures = 0
    warnings = 0

    if p95_response_gap_ms is not None:
        VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS.labels(
            trigger_source=trigger_source
        ).set(float(p95_response_gap_ms))
        if p95_response_gap_ms > timing_gate_p95_response_gap_ms:
            failures += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="p95_response_gap_ms",
                severity="gate",
                trigger_source=trigger_source,
            ).inc()
        elif p95_response_gap_ms > timing_warn_p95_response_gap_ms:
            warnings += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="p95_response_gap_ms",
                severity="warn",
                trigger_source=trigger_source,
            ).inc()

    if interruption_recovery_pct is not None:
        VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT.labels(
            trigger_source=trigger_source
        ).observe(interruption_recovery_pct)
        if interruption_recovery_pct < timing_gate_interruption_recovery_pct:
            failures += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="interruption_recovery_pct",
                severity="gate",
                trigger_source=trigger_source,
            ).inc()
        elif interruption_recovery_pct < timing_warn_interruption_recovery_pct:
            warnings += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="interruption_recovery_pct",
                severity="warn",
                trigger_source=trigger_source,
            ).inc()

    if turn_taking_efficiency_pct is not None:
        VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT.labels(
            trigger_source=trigger_source
        ).observe(turn_taking_efficiency_pct)
        if turn_taking_efficiency_pct < timing_gate_turn_taking_efficiency_pct:
            failures += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="turn_taking_efficiency_pct",
                severity="gate",
                trigger_source=trigger_source,
            ).inc()
        elif turn_taking_efficiency_pct < timing_warn_turn_taking_efficiency_pct:
            warnings += 1
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL.labels(
                metric="turn_taking_efficiency_pct",
                severity="warn",
                trigger_source=trigger_source,
            ).inc()

    result = "pass"
    if failures:
        result = "fail"
    elif warnings:
        result = "warn"

    VOICE_QUALITY_RUNS_TOTAL.labels(
        result=result,
        trigger_source=trigger_source,
    ).inc()
    return result


def start_metrics_server_if_enabled() -> None:
    global _METRICS_SERVER_STARTED
    if not settings.metrics_enabled or _METRICS_SERVER_STARTED:
        return
    start_http_server(addr=settings.metrics_host, port=settings.metrics_port)
    _METRICS_SERVER_STARTED = True
    logger.info(
        "Judge metrics endpoint started on %s:%s",
        settings.metrics_host,
        settings.metrics_port,
    )
