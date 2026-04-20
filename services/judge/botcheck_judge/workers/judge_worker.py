"""
ARQ worker: judge_run

Thin glue between the ARQ job queue and judge_conversation().

Job payload:
  {
    "run_id": "run_abc123",
    "scenario_id": "jailbreak-dan-prompt",
    "scenario_version_hash": "sha256:...",
    "scenario_kind": "graph",
    "judge_contract_version": 1,
    "tenant_id": "acme",
    "traceparent": "00-...",
    "tracestate": "vendor=test",
    "started_at": "<ISO datetime>",
    "conversation": [ <ConversationTurn dicts> ]
  }
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import aioboto3
import anthropic
import httpx
from arq.connections import RedisSettings as ArqRedisSettings
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
    TRACEPARENT_HEADER,
    TRACESTATE_HEADER,
    attach_trace_context_from_carrier,
    detach_trace_context,
)
from pydantic import BaseModel, Field, model_validator

from botcheck_scenarios import (
    ConversationTurn,
    classify_judge_error,
    RunReport,
    ScenarioDefinition,
    ScoringDimension,
    resolve_rubric,
)

from opentelemetry import trace as otel_trace

from ..config import settings
from ..judge import judge_conversation
from ._provider_binding import binding_for_capability
from .generator_task import generate_scenarios
from ..metrics import (
    JUDGE_LLM_LATENCY_SECONDS,
    JUDGE_RUN_DURATION_SECONDS,
    JUDGE_RUNS_INFLIGHT,
    JUDGE_RUNS_TOTAL,
    LLM_TOKENS_TOTAL,
    PROVIDER_API_CALLS_TOTAL,
    SCENARIO_GATE_RESULTS_TOTAL,
    observe_voice_quality_thresholds,
    start_metrics_server_if_enabled,
)
from ..telemetry import init_llm_instrumentation, instrument_httpx, setup_tracing

_tracer = otel_trace.get_tracer("botcheck.judge")

logger = logging.getLogger("botcheck.judge.worker")

SAFETY_DIMENSIONS = {
    ScoringDimension.JAILBREAK,
    ScoringDimension.DISCLOSURE,
    ScoringDimension.PII_HANDLING,
    ScoringDimension.POLICY,
    ScoringDimension.ROLE_INTEGRITY,
}


class ToolContextEntry(BaseModel):
    """Optional tool invocation metadata correlated to transcript turns."""

    tool_name: str
    turn_id: str | None = None
    turn_number: int | None = Field(default=None, ge=1)
    status: Literal["success", "error", "timeout"] = "success"
    request: dict[str, Any] | str | None = None
    response: dict[str, Any] | str | None = None
    error: str | None = None
    timestamp_ms: int | None = Field(default=None, ge=0)


class PathStep(BaseModel):
    turn_id: str
    visit: int = Field(ge=1)
    turn_number: int = Field(ge=1)


class AIJudgeContext(BaseModel):
    """Objective-scoring context for AI scenarios."""

    dataset_input: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    persona_id: str = Field(min_length=1)
    persona_name: str | None = None
    scenario_objective: str | None = None


class JudgeJobPayload(BaseModel):
    """Canonical ARQ job payload for the judge worker."""

    run_id: str
    scenario_id: str
    scenario_version_hash: str = ""
    scenario_kind: Literal["graph", "ai"] = "graph"
    judge_contract_version: int = Field(default=1, ge=1)
    tenant_id: str = ""
    trigger_source: str = "manual"
    traceparent: str | None = None
    tracestate: str | None = None
    started_at: datetime
    conversation: list[ConversationTurn]
    tool_context: list[ToolContextEntry] | None = None
    scenario_has_branching: bool = False
    taken_path_steps: list[PathStep] = Field(default_factory=list)
    ai_context: AIJudgeContext | None = None

    @model_validator(mode="after")
    def validate_turn_order(self) -> "JudgeJobPayload":
        last_turn_number = 0
        for turn in self.conversation:
            if turn.turn_number <= last_turn_number:
                raise ValueError(
                    "judge payload conversation turn_number values must be strictly increasing"
                )
            last_turn_number = turn.turn_number
        return self

    @model_validator(mode="after")
    def validate_branching_path_contract(self) -> "JudgeJobPayload":
        if self.scenario_has_branching and not self.taken_path_steps:
            raise ValueError(
                "Branching scenarios require non-empty 'taken_path_steps' in judge payload."
            )
        return self

    @model_validator(mode="after")
    def validate_kind_contract(self) -> "JudgeJobPayload":
        if self.scenario_kind == "ai" and self.judge_contract_version < 2:
            raise ValueError("AI scenarios require judge_contract_version >= 2.")
        if self.scenario_kind == "ai" and self.ai_context is None:
            raise ValueError("AI scenarios require non-empty 'ai_context' in judge payload.")
        return self


def _trace_attrs(job_payload: JudgeJobPayload) -> dict[str, str | int]:
    return {
        ATTR_RUN_ID: job_payload.run_id,
        ATTR_SCENARIO_ID: job_payload.scenario_id,
        ATTR_SCENARIO_KIND: job_payload.scenario_kind,
        ATTR_TENANT_ID: job_payload.tenant_id,
        ATTR_TRIGGER_SOURCE: job_payload.trigger_source,
        ATTR_JUDGE_CONTRACT_VERSION: job_payload.judge_contract_version,
    }


def _trace_attr_value(value: object | None) -> object | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _emit_llm_score_spans(job_payload: JudgeJobPayload, report: RunReport) -> None:
    base_attrs = _trace_attrs(job_payload)
    for dimension_name, dimension in report.scores.items():
        attrs: dict[str, object] = {
            **base_attrs,
            ATTR_SCORE_DIMENSION: dimension_name,
        }
        for attr_name, raw_value in (
            (ATTR_JUDGE_METRIC_TYPE, getattr(dimension, "metric_type", None)),
            (ATTR_JUDGE_STATUS, getattr(dimension, "status", None)),
            (ATTR_JUDGE_THRESHOLD, getattr(dimension, "threshold", None)),
            (ATTR_JUDGE_GATE, getattr(dimension, "gate", None)),
            (ATTR_JUDGE_PASSED, getattr(dimension, "passed", None)),
            (ATTR_JUDGE_SCORE, getattr(dimension, "score", None)),
        ):
            value = _trace_attr_value(raw_value)
            if value is not None:
                attrs[attr_name] = value
        with _tracer.start_as_current_span(SPAN_JUDGE_LLM_SCORE, attributes=attrs):
            pass


def _api_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.judge_secret}"}


async def _fetch_provider_runtime_context(
    *,
    tenant_id: str,
    judge_model: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
        timeout=httpx.Timeout(5.0),
    ) as http:
        resp = await http.post(
            "/providers/internal/runtime-context",
            json={
                "tenant_id": tenant_id,
                "runtime_scope": "judge",
                "provider_bindings": [
                    {
                        "capability": "judge",
                        "model": judge_model,
                    }
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def _post_provider_usage(
    *,
    tenant_id: str,
    provider_id: str,
    usage_key: str,
    run_id: str,
    input_tokens: int,
    output_tokens: int,
    request_count: int,
) -> None:
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
        timeout=httpx.Timeout(5.0),
    ) as http:
        resp = await http.post(
            "/providers/internal/usage",
            json={
                "tenant_id": tenant_id,
                "provider_id": provider_id,
                "usage_key": usage_key,
                "runtime_scope": "judge",
                "capability": "judge",
                "run_id": run_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "request_count": request_count,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("stored"):
            raise RuntimeError(
                f"Usage write was not stored for usage_key={usage_key!r}: "
                f"ledger_id={payload.get('ledger_id')!r}"
            )


def _binding_for_capability(
    runtime_context: dict[str, object] | None,
    *,
    capability: str,
) -> dict[str, object] | None:
    return binding_for_capability(runtime_context, capability=capability)


def _default_vendor_for_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith("gpt-"):
        return "openai"
    return ""


def _build_report_s3_key(*, run_id: str, tenant_id: str, now: datetime) -> str:
    tenant_prefix = (tenant_id or "default").strip() or "default"
    return (
        f"{tenant_prefix}/reports/"
        f"{now.year}/{now.month:02d}/{now.day:02d}/{run_id}.json"
    )


async def _store_report_s3(report_json: str, run_id: str, tenant_id: str) -> str | None:
    """Upload the report JSON to S3/MinIO. Returns the S3 key, or None on failure."""
    now = datetime.now(UTC)
    key = _build_report_s3_key(run_id=run_id, tenant_id=tenant_id, now=now)
    try:
        session = aioboto3.Session(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        async with session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
        ) as s3:
            await s3.put_object(
                Bucket=settings.s3_bucket_prefix,
                Key=key,
                Body=report_json.encode(),
                ContentType="application/json",
            )
        logger.info("Report stored at s3://%s/%s", settings.s3_bucket_prefix, key)
        return key
    except Exception:
        logger.exception("S3 upload failed for run %s — continuing without artifact", run_id)
        return None


def _classify_judge_error(exc: Exception) -> str:
    return classify_judge_error(exc).value


def _requires_safety_contract(scenario: ScenarioDefinition) -> bool:
    rubric = resolve_rubric(scenario.type, scenario.scoring.rubric)
    return any(r.dimension in SAFETY_DIMENSIONS for r in rubric)


def _validate_safety_input_contract(
    *,
    scenario: ScenarioDefinition,
    job_payload: JudgeJobPayload,
    raw_payload: dict[str, Any],
) -> None:
    if not _requires_safety_contract(scenario):
        return

    if "tool_context" not in raw_payload:
        raise ValueError(
            "Safety scenarios require 'tool_context' key in judge payload "
            "(empty list is allowed when no tools are used)."
        )
    if job_payload.tool_context is None:
        raise ValueError("Safety scenarios require 'tool_context' to be a list.")

    speakers = {turn.speaker for turn in job_payload.conversation}
    if "harness" not in speakers or "bot" not in speakers:
        raise ValueError(
            "Safety scenarios require full conversation context with both harness and bot turns."
        )

    valid_turn_numbers = {turn.turn_number for turn in job_payload.conversation}
    for entry in job_payload.tool_context:
        if entry.turn_number is None:
            continue
        if entry.turn_number not in valid_turn_numbers:
            raise ValueError(
                f"tool_context entry for '{entry.tool_name}' references unknown turn_number "
                f"{entry.turn_number}"
            )


async def _patch_fail_closed(run_id: str, exc: Exception) -> None:
    error_code = _classify_judge_error(exc)
    reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    async with httpx.AsyncClient(
        base_url=settings.botcheck_api_url,
        headers=_api_headers(),
    ) as http:
        resp = await http.patch(
            f"/runs/{run_id}",
            json={
                "state": "error",
                "gate_result": "blocked",
                "overall_status": "error",
                "failed_dimensions": ["judge_error", error_code],
                "error_code": error_code,
                "summary": f"Judge error: {reason}",
            },
        )
        resp.raise_for_status()


async def judge_run(ctx: dict, *, payload: dict) -> dict:
    """ARQ job: score a completed run and write the report."""
    raw_run_id = ""
    if isinstance(payload, dict):
        raw_run_id = str(payload.get("run_id") or "").strip()
    try:
        job_payload = JudgeJobPayload.model_validate(payload)
    except Exception as exc:
        logger.exception("Invalid judge payload for run %s", raw_run_id or "<unknown>")
        if raw_run_id:
            try:
                await _patch_fail_closed(raw_run_id, exc)
            except Exception:
                logger.exception("Failed to apply fail-closed patch for run %s", raw_run_id)
        raise
    run_id = job_payload.run_id
    tenant_id = job_payload.tenant_id
    trigger_source = job_payload.trigger_source
    logger.info("Judging run %s", run_id)
    trace_context_token = attach_trace_context_from_carrier(
        {
            TRACEPARENT_HEADER: job_payload.traceparent or "",
            TRACESTATE_HEADER: job_payload.tracestate or "",
        }
    )
    try:
        with _tracer.start_as_current_span(
            SPAN_JUDGE_RUN,
            attributes=_trace_attrs(job_payload),
        ):
            t0 = time.monotonic()
            with JUDGE_RUNS_INFLIGHT.track_inprogress():
                try:
                    started_at = job_payload.started_at
                    completed_at = datetime.now(UTC)

                    async with httpx.AsyncClient(
                        base_url=settings.botcheck_api_url,
                        headers=_api_headers(),
                    ) as http:
                        resp = await http.get(f"/scenarios/{job_payload.scenario_id}")
                        resp.raise_for_status()
                        scenario = ScenarioDefinition.model_validate(resp.json())

                    _validate_safety_input_contract(
                        scenario=scenario,
                        job_payload=job_payload,
                        raw_payload=payload,
                    )
                    conversation = job_payload.conversation
                    tool_context = [
                        entry.model_dump(mode="json") for entry in (job_payload.tool_context or [])
                    ]
                    taken_path_steps = [
                        step.model_dump(mode="json")
                        for step in (job_payload.taken_path_steps or [])
                    ]
                    ai_context = (
                        job_payload.ai_context.model_dump(mode="json")
                        if job_payload.ai_context is not None
                        else None
                    )
                    use_multi_sample = (
                        settings.multi_sample_judge and job_payload.scenario_kind != "ai"
                    )
                    multi_sample_n = settings.multi_sample_judge_n if use_multi_sample else 1
                    runtime_context: dict[str, object] | None = None
                    try:
                        runtime_context = await _fetch_provider_runtime_context(
                            tenant_id=tenant_id,
                            judge_model=settings.judge_model,
                        )
                    except Exception:
                        logger.error(
                            "judge_provider_runtime_context_fetch_failed",
                            extra={
                                "run_id": run_id,
                                "tenant_id": tenant_id,
                                "judge_model": settings.judge_model,
                            },
                            exc_info=True,
                        )
                    judge_binding = _binding_for_capability(runtime_context, capability="judge")
                    # Discard binding if the provider is not actually available.
                    actual_availability_status = str(
                        (judge_binding or {}).get("availability_status") or ""
                    )
                    if actual_availability_status != "available":
                        judge_binding = None
                    if runtime_context is None or judge_binding is None:
                        logger.error(
                            "judge_provider_binding_unavailable",
                            extra={
                                "run_id": run_id,
                                "tenant_id": tenant_id,
                                "reason": "runtime_context_unavailable"
                                if runtime_context is None
                                else "no_available_binding",
                                "availability_status": actual_availability_status or None,
                            },
                        )
                        raise RuntimeError("Judge provider runtime binding unavailable")
                    judge_credential_source = str(
                        judge_binding.get("credential_source") or "none"
                    ).strip()
                    judge_model = str(
                        judge_binding.get("model") or settings.judge_model
                    ).strip() or settings.judge_model
                    judge_vendor = str(
                        judge_binding.get("vendor")
                        or _default_vendor_for_model(judge_model)
                        or "anthropic"
                    ).strip().lower()
                    judge_provider_id = str(judge_binding.get("provider_id") or "").strip()
                    if judge_vendor != "anthropic":
                        raise RuntimeError(
                            f"Judge provider vendor '{judge_vendor}' is not yet supported"
                        )
                    effective_judge_provider_id = judge_provider_id or f"{judge_vendor}:{judge_model}"
                    if not judge_provider_id:
                        logger.warning(
                            "judge_provider_id_not_resolved_using_synthesized_fallback",
                            extra={
                                "run_id": run_id,
                                "tenant_id": tenant_id,
                                "effective_judge_provider_id": effective_judge_provider_id,
                            },
                        )
                    judge_secret_fields = judge_binding.get("secret_fields")
                    judge_api_key = ""
                    if isinstance(judge_secret_fields, dict):
                        judge_api_key = str(judge_secret_fields.get("api_key") or "").strip()
                    if not judge_api_key:
                        logger.error(
                            "judge_provider_binding_missing_api_key",
                            extra={
                                "run_id": run_id,
                                "tenant_id": tenant_id,
                                "provider_id": effective_judge_provider_id,
                            },
                        )
                        raise RuntimeError("Judge provider runtime binding missing api_key")

                    llm_started = time.monotonic()
                    try:
                        report, usage = await judge_conversation(
                            run_id=run_id,
                            scenario=scenario,
                            conversation=conversation,
                            tool_context=tool_context,
                            anthropic_client=anthropic.AsyncAnthropic(api_key=judge_api_key),
                            model=judge_model,
                            started_at=started_at,
                            completed_at=completed_at,
                            scenario_version_hash=job_payload.scenario_version_hash,
                            tenant_id=tenant_id,
                            judge_version=settings.judge_version,
                            taken_path_steps=taken_path_steps,
                            ai_context=ai_context,
                            multi_sample_judge=use_multi_sample,
                            multi_sample_n=multi_sample_n,
                        )
                        JUDGE_LLM_LATENCY_SECONDS.labels(
                            model=judge_model,
                            trigger_source=trigger_source,
                        ).observe(time.monotonic() - llm_started)
                        provider = judge_vendor
                        model = judge_model
                        LLM_TOKENS_TOTAL.labels(
                            provider=provider, model=model, token_type="input"
                        ).inc(usage.get("input_tokens", 0))
                        LLM_TOKENS_TOTAL.labels(
                            provider=provider, model=model, token_type="output"
                        ).inc(usage.get("output_tokens", 0))

                        calls_count = (
                            multi_sample_n
                            if use_multi_sample and scenario.type == "adversarial"
                            else 1
                        )
                        PROVIDER_API_CALLS_TOTAL.labels(
                            provider=provider, service="scoring", model=model, outcome="success"
                        ).inc(calls_count)
                    except Exception:
                        PROVIDER_API_CALLS_TOTAL.labels(
                            provider=judge_vendor,
                            service="scoring",
                            model=judge_model,
                            outcome="error",
                        ).inc()
                        JUDGE_LLM_LATENCY_SECONDS.labels(
                            model=judge_model,
                            trigger_source=trigger_source,
                        ).observe(time.monotonic() - llm_started)
                        raise

                    _emit_llm_score_spans(job_payload, report)
                    SCENARIO_GATE_RESULTS_TOTAL.labels(
                        result=report.gate_result.value,
                        scenario_kind=job_payload.scenario_kind,
                        trigger_source=trigger_source,
                    ).inc()

                    voice_quality_result = observe_voice_quality_thresholds(
                        trigger_source=trigger_source,
                        p95_response_gap_ms=report.deterministic.p95_response_gap_ms,
                        interruption_recovery_pct=report.deterministic.interruption_recovery_pct,
                        turn_taking_efficiency_pct=report.deterministic.turn_taking_efficiency_pct,
                        timing_gate_p95_response_gap_ms=scenario.config.timing_gate_p95_response_gap_ms,
                        timing_warn_p95_response_gap_ms=scenario.config.timing_warn_p95_response_gap_ms,
                        timing_gate_interruption_recovery_pct=scenario.config.timing_gate_interruption_recovery_pct,
                        timing_warn_interruption_recovery_pct=scenario.config.timing_warn_interruption_recovery_pct,
                        timing_gate_turn_taking_efficiency_pct=scenario.config.timing_gate_turn_taking_efficiency_pct,
                        timing_warn_turn_taking_efficiency_pct=scenario.config.timing_warn_turn_taking_efficiency_pct,
                    )

                    report_json = report.model_dump_json()
                    s3_key = await _store_report_s3(report_json, run_id, tenant_id)

                    duration_ms = int((time.monotonic() - t0) * 1000)
                    scores = {
                        dim: dimension.model_dump(mode="json")
                        for dim, dimension in report.scores.items()
                    }
                    findings = [finding.model_dump(mode="json") for finding in report.all_findings]
                    async with httpx.AsyncClient(
                        base_url=settings.botcheck_api_url,
                        headers=_api_headers(),
                    ) as http:
                        patch_resp = await http.patch(
                            f"/runs/{run_id}",
                            json={
                                "gate_result": report.gate_result.value,
                                "overall_status": report.overall_status.value,
                                "failed_dimensions": report.failed_gate_dimensions,
                                "summary": report.summary_line,
                                "scores": scores,
                                "findings": findings,
                                "report_s3_key": s3_key,
                            },
                        )
                        patch_resp.raise_for_status()
                    try:
                        # Key format must stay in sync with usage_service.judge_run_usage_key
                        # in botcheck_api (separate package; can't import directly).
                        await _post_provider_usage(
                            tenant_id=tenant_id,
                            provider_id=effective_judge_provider_id,
                            usage_key=f"judge-run:{run_id}:{effective_judge_provider_id}",
                            run_id=run_id,
                            input_tokens=int(usage.get("input_tokens", 0) or 0),
                            output_tokens=int(usage.get("output_tokens", 0) or 0),
                            request_count=int(calls_count),
                        )
                    except Exception:
                        logger.warning(
                            "provider.usage.write_failed",
                            extra={
                                "tenant_id": tenant_id,
                                "provider_id": effective_judge_provider_id,
                                "runtime_scope": "judge",
                                "capability": "judge",
                                "run_id": run_id,
                            },
                            exc_info=True,
                        )

                    logger.info(
                        "judge.complete",
                        extra={
                            "run_id": run_id,
                            "tenant_id": tenant_id,
                            "scenario_id": job_payload.scenario_id,
                            "gate_result": report.gate_result.value,
                            "overall_status": report.overall_status.value,
                            "failed_gate_dimensions": report.failed_gate_dimensions,
                            "duration_ms": duration_ms,
                            "judge_model": judge_model,
                            "judge_provider_id": judge_provider_id or None,
                            "judge_credential_source": judge_credential_source,
                            "judge_version": settings.judge_version,
                            "s3_key": s3_key,
                            "voice_quality_result": voice_quality_result,
                        },
                    )

                    elapsed = time.monotonic() - t0
                    JUDGE_RUNS_TOTAL.labels(
                        outcome="success",
                        trigger_source=trigger_source,
                        error_code="none",
                    ).inc()
                    JUDGE_RUN_DURATION_SECONDS.labels(
                        outcome="success",
                        trigger_source=trigger_source,
                    ).observe(elapsed)
                    logger.info("Run %s judged: %s", run_id, report.gate_result.value)
                    return {"gate_result": report.gate_result.value, "summary": report.summary_line}
                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    error_code = _classify_judge_error(exc)
                    JUDGE_RUNS_TOTAL.labels(
                        outcome="error",
                        trigger_source=trigger_source,
                        error_code=error_code,
                    ).inc()
                    JUDGE_RUN_DURATION_SECONDS.labels(
                        outcome="error",
                        trigger_source=trigger_source,
                    ).observe(elapsed)
                    SCENARIO_GATE_RESULTS_TOTAL.labels(
                        result="blocked",
                        scenario_kind=job_payload.scenario_kind,
                        trigger_source=trigger_source,
                    ).inc()
                    logger.exception("Judge failed for run %s", run_id)
                    try:
                        await _patch_fail_closed(run_id, exc)
                    except Exception:
                        logger.exception("Failed to apply fail-closed patch for run %s", run_id)
                    raise
    finally:
        detach_trace_context(trace_context_token)


async def on_startup(ctx: dict) -> None:
    setup_tracing("botcheck-judge")
    instrument_httpx()
    init_llm_instrumentation()
    start_metrics_server_if_enabled()


def _redis_settings() -> ArqRedisSettings:
    p = urlparse(settings.redis_url)
    return ArqRedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int(p.path.lstrip("/") or 0),
    )


class WorkerSettings:
    functions = [judge_run, generate_scenarios]
    cron_jobs = []
    on_startup = on_startup
    redis_settings = _redis_settings()
    queue_name = "arq:judge"
    max_jobs = 10
    job_timeout = 300
