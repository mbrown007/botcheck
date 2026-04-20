from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import anthropic
from arq.connections import RedisSettings as ArqRedisSettings
from botcheck_http_client import DirectHTTPBotClient, DirectHTTPTransportContext
from pydantic import BaseModel

from .. import database, metrics as api_metrics
from ..config import settings
from ..database import apply_tenant_rls_context
from ..models import (
    GraiEvalCaseRow,
    GraiEvalPromptRow,
    GraiEvalRunStatus,
    GraiEvalRunTerminalOutcome,
)
from ..providers.service import build_provider_runtime_context
from ..providers.usage_service import (
    grai_eval_pair_usage_key,
    observe_provider_usage_write_failure,
    record_provider_usage,
)
from ..retention import upload_artifact_bytes
from ..telemetry import setup_tracing
from .assertions import AssertionEvaluation, evaluate_assertion, render_prompt_text
from .observability import (
    classify_http_error,
    observe_artifact_upload,
    observe_assertion_rows,
    observe_dispatch,
    observe_http_error,
    observe_run_terminal,
)
from .store_service import (
    get_grai_eval_run_for_tenant,
    list_grai_eval_cases_for_suite,
    list_grai_eval_pair_progress,
    list_grai_eval_prompts_for_suite,
    list_grai_eval_run_destinations_for_tenant,
    replace_grai_eval_pair_results,
    set_grai_eval_run_progress,
)
from .service_models import (
    GRAI_EVAL_DISPATCH_ERROR_PREFIX,
    GraiEvalResultWritePayload,
    GraiEvalRunDestinationSnapshot,
)

logger = logging.getLogger("botcheck.api.grai.eval_worker")


@dataclass(slots=True)
class PairEvaluationResult:
    pair_failed: bool


@dataclass(slots=True)
class PairWorkItem:
    prompt: GraiEvalPromptRow
    case: GraiEvalCaseRow
    destination: GraiEvalRunDestinationSnapshot


class GraiEvalJobPayload(BaseModel):
    eval_run_id: str
    tenant_id: str


class _RequestRateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._interval_s = 0.0 if requests_per_second <= 0 else 1.0 / requests_per_second
        self._next_allowed_at = 0.0
        self._lock = asyncio.Lock()

    async def wait_turn(self) -> None:
        if self._interval_s <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_at:
                await asyncio.sleep(self._next_allowed_at - now)
            self._next_allowed_at = max(now, self._next_allowed_at) + self._interval_s


def _counts_from_progress(pair_failures: dict[tuple[str, str, int], bool]) -> tuple[int, int]:
    failed_count = sum(1 for failed in pair_failures.values() if failed)
    completed_count = len(pair_failures) - failed_count
    return completed_count, failed_count


_SAFE_TENANT_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _build_raw_artifact_key(
    *,
    eval_run_id: str,
    tenant_id: str,
    prompt_id: str,
    case_id: str,
    destination_index: int,
    now: datetime,
) -> str:
    tenant_prefix = _SAFE_TENANT_RE.sub("_", (tenant_id or "default").strip()) or "default"
    return (
        f"{tenant_prefix}/grai-evals/"
        f"{now.year}/{now.month:02d}/{now.day:02d}/{eval_run_id}/{destination_index}-{prompt_id}-{case_id}.json"
    )


def _result_payload(
    *,
    evaluation: AssertionEvaluation,
    tags_json: list[str],
    raw_s3_key: str | None,
) -> GraiEvalResultWritePayload:
    return GraiEvalResultWritePayload(
        assertion_type=evaluation.assertion_type,
        passed=evaluation.passed,
        score=evaluation.score,
        threshold=evaluation.threshold,
        weight=evaluation.weight,
        raw_value=evaluation.raw_value,
        failure_reason=evaluation.failure_reason,
        latency_ms=evaluation.latency_ms,
        tags_json=list(tags_json),
        raw_s3_key=raw_s3_key,
    )


def _failed_assertion_payloads(
    *,
    assertions: list[dict[str, Any]],
    failure_reason: str,
    tags_json: list[str],
    raw_s3_key: str | None,
) -> list[GraiEvalResultWritePayload]:
    rows: list[GraiEvalResultWritePayload] = []
    for assertion in assertions:
        rows.append(
            GraiEvalResultWritePayload(
                assertion_type=str(assertion.get("assertion_type") or "unknown"),
                passed=False,
                score=None,
                threshold=(
                    float(assertion["threshold"]) if assertion.get("threshold") is not None else None
                ),
                weight=float(assertion["weight"]) if assertion.get("weight") is not None else 1.0,
                raw_value=(
                    str(assertion["raw_value"]) if assertion.get("raw_value") is not None else None
                ),
                failure_reason=failure_reason,
                latency_ms=None,
                tags_json=list(tags_json),
                raw_s3_key=raw_s3_key,
            )
        )
    return rows


async def _upload_pair_artifact(
    *,
    eval_run_id: str,
    tenant_id: str,
    prompt_id: str,
    case_id: str,
    destination_index: int,
    payload: dict[str, object],
) -> str | None:
    if not settings.s3_endpoint_url or not settings.s3_access_key or not settings.s3_secret_key:
        observe_artifact_upload(outcome="skipped")
        return None
    key = _build_raw_artifact_key(
        eval_run_id=eval_run_id,
        tenant_id=tenant_id,
        prompt_id=prompt_id,
        case_id=case_id,
        destination_index=destination_index,
        now=datetime.now(UTC),
    )
    try:
        await upload_artifact_bytes(
            settings,
            key=key,
            body=json.dumps(payload, ensure_ascii=True, sort_keys=True).encode(),
            content_type="application/json",
        )
    except Exception:
        observe_artifact_upload(outcome="error")
        logger.exception(
            "grai_eval_artifact_upload_failed",
            extra={"eval_run_id": eval_run_id, "prompt_id": prompt_id, "case_id": case_id},
        )
        return None
    observe_artifact_upload(outcome="success")
    return key


@asynccontextmanager
async def _session_for_tenant(tenant_id: str, *, readonly: bool = False) -> AsyncIterator[Any]:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as session:
        await apply_tenant_rls_context(session, tenant_id)
        try:
            yield session
            if not readonly:
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _load_run_state(
    payload: GraiEvalJobPayload,
) -> tuple[
    Any | None,
    list[GraiEvalPromptRow],
    list[GraiEvalCaseRow],
    list[GraiEvalRunDestinationSnapshot],
    dict[tuple[str, str, int], bool],
]:
    async with _session_for_tenant(payload.tenant_id, readonly=True) as session:
        run_row = await get_grai_eval_run_for_tenant(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
        )
        if run_row is None:
            return None, [], [], [], {}
        prompts = await list_grai_eval_prompts_for_suite(
            session,
            suite_id=run_row.suite_id,
            tenant_id=payload.tenant_id,
        )
        cases = await list_grai_eval_cases_for_suite(
            session,
            suite_id=run_row.suite_id,
            tenant_id=payload.tenant_id,
        )
        destinations = await list_grai_eval_run_destinations_for_tenant(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
        )
        if not destinations:
            destinations = [
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id=run_row.transport_profile_id,
                    label=run_row.transport_profile_id,
                    protocol="http",
                    endpoint_at_start=run_row.endpoint_at_start,
                    headers_at_start=dict(run_row.headers_at_start or {}),
                    direct_http_config_at_start=(
                        dict(run_row.direct_http_config_at_start)
                        if run_row.direct_http_config_at_start is not None
                        else None
                    ),
                )
            ]
        progress = await list_grai_eval_pair_progress(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
        )
        return run_row, prompts, cases, destinations, progress


def _runtime_binding_for_capability(
    runtime_context: dict[str, object] | None,
    *,
    capability: str,
) -> dict[str, object] | None:
    if not isinstance(runtime_context, dict):
        return None
    providers = runtime_context.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if str(provider.get("capability") or "").strip().lower() == capability:
            return provider
    return None


def _default_vendor_for_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith("gpt-"):
        return "openai"
    return ""


async def _load_eval_judge_runtime_context(tenant_id: str) -> dict[str, object]:
    async with _session_for_tenant(tenant_id, readonly=True) as session:
        return await build_provider_runtime_context(
            session,
            tenant_id=tenant_id,
            runtime_scope="judge",
            provider_bindings=[
                {
                    "capability": "judge",
                    "model": settings.grai_eval_judge_model,
                }
            ],
        )


def _build_eval_judge_client(
    runtime_context: dict[str, object] | None,
) -> tuple[anthropic.AsyncAnthropic, str, str, str | None]:
    binding = _runtime_binding_for_capability(runtime_context, capability="judge")
    # Discard binding if the provider is not actually available.
    if str((binding or {}).get("availability_status") or "") != "available":
        logger.error(
            "grai.eval_judge.provider_unavailable: no available judge provider binding; "
            "API calls will fail with auth error",
            extra={
                "availability_status": (binding or {}).get("availability_status"),
                "provider_id": (binding or {}).get("provider_id"),
            },
        )
        binding = None
    model = str((binding or {}).get("model") or settings.grai_eval_judge_model).strip()
    vendor = str(
        (binding or {}).get("vendor") or _default_vendor_for_model(model) or "anthropic"
    ).strip().lower()
    provider_id = str((binding or {}).get("provider_id") or "").strip() or None
    secret_fields = (binding or {}).get("secret_fields")
    api_key = ""
    if isinstance(secret_fields, dict):
        api_key = str(secret_fields.get("api_key") or "").strip()
    if vendor != "anthropic":
        raise RuntimeError(f"Grai eval judge provider vendor '{vendor}' is not yet supported")
    # Always construct the client (matching judge_worker pattern); an empty key will
    # raise an Anthropic auth error at the first API call rather than a NoneType crash.
    return anthropic.AsyncAnthropic(api_key=api_key), vendor, model, provider_id


async def _is_cancelled(payload: GraiEvalJobPayload) -> bool:
    async with _session_for_tenant(payload.tenant_id, readonly=True) as session:
        row = await get_grai_eval_run_for_tenant(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
        )
        return row is None or row.status == GraiEvalRunStatus.CANCELLED.value


async def _persist_progress(
    payload: GraiEvalJobPayload,
    *,
    status: str,
    terminal_outcome: GraiEvalRunTerminalOutcome | None,
    dispatched_count: int,
    completed_count: int,
    failed_count: int,
) -> None:
    async with _session_for_tenant(payload.tenant_id) as session:
        await set_grai_eval_run_progress(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
            status=status,
            terminal_outcome=terminal_outcome,
            dispatched_count=dispatched_count,
            completed_count=completed_count,
            failed_count=failed_count,
        )


async def _evaluate_pair(
    *,
    payload: GraiEvalJobPayload,
    run_row: Any,
    pair: PairWorkItem,
    client: DirectHTTPBotClient,
    rate_limiter: _RequestRateLimiter,
    anthropic_client: anthropic.AsyncAnthropic | None,
    llm_model: str,
    judge_provider_id: str | None,
) -> PairEvaluationResult:
    prompt_text = render_prompt_text(pair.prompt.prompt_text, dict(pair.case.vars_json or {}))
    raw_ctx = (pair.case.metadata_json or {}).get("http_request_context")
    request_context = dict(raw_ctx) if isinstance(raw_ctx, dict) else {}
    started = time.monotonic()
    raw_s3_key: str | None = None
    evaluations: list[AssertionEvaluation] = []
    try:
        await rate_limiter.wait_turn()
        response = await client.respond(
            prompt=prompt_text,
            conversation=[],
            session_id=(
                f"{payload.eval_run_id}:{pair.destination.destination_index}:"
                f"{pair.prompt.prompt_id}:{pair.case.case_id}"
            ),
            request_context=request_context,
        )
        evaluations = [
            await evaluate_assertion(
                assertion=dict(assertion),
                prompt_text=prompt_text,
                case_description=pair.case.description,
                vars_json=dict(pair.case.vars_json or {}),
                response_text=response.text,
                latency_ms=response.latency_ms,
                anthropic_client=anthropic_client,
                llm_model=llm_model,
            )
            for assertion in list(pair.case.assert_json or [])
        ]
        raw_s3_key = await _upload_pair_artifact(
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
            prompt_id=pair.prompt.prompt_id,
            case_id=pair.case.case_id,
            destination_index=pair.destination.destination_index,
            payload={
                "destination_index": pair.destination.destination_index,
                "transport_profile_id": pair.destination.transport_profile_id,
                "destination_label": pair.destination.label,
                "prompt_id": pair.prompt.prompt_id,
                "case_id": pair.case.case_id,
                "prompt_text": prompt_text,
                "vars_json": dict(pair.case.vars_json or {}),
                "metadata_json": dict(pair.case.metadata_json or {}),
                "request_context": request_context,
                "response_text": response.text,
                "assertions": [
                    {
                        "assertion_type": evaluation.assertion_type,
                        "passed": evaluation.passed,
                        "score": evaluation.score,
                        "threshold": evaluation.threshold,
                        "weight": evaluation.weight,
                        "failure_reason": evaluation.failure_reason,
                    }
                    for evaluation in evaluations
                ],
            },
        )
        rows = [
            _result_payload(
                evaluation=evaluation,
                tags_json=list(pair.case.tags_json or []),
                raw_s3_key=raw_s3_key,
            )
            for evaluation in evaluations
        ]
        pair_failed = any(not evaluation.passed for evaluation in evaluations)
        observe_dispatch(outcome="success", elapsed_s=time.monotonic() - started)
    except Exception as exc:
        observe_dispatch(outcome="error", elapsed_s=time.monotonic() - started)
        if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, asyncio.TimeoutError, TimeoutError)):
            observe_http_error(exc)
        logger.warning(
            "grai_eval_pair_dispatch_failed",
            extra={
                "eval_run_id": payload.eval_run_id,
                "prompt_id": pair.prompt.prompt_id,
                "case_id": pair.case.case_id,
                "error_class": classify_http_error(exc),
            },
        )
        rows = _failed_assertion_payloads(
            assertions=list(pair.case.assert_json or []),
            failure_reason=f"{GRAI_EVAL_DISPATCH_ERROR_PREFIX}{exc}",
            tags_json=list(pair.case.tags_json or []),
            raw_s3_key=raw_s3_key,
        )
        pair_failed = True
    observe_assertion_rows(rows)

    async with _session_for_tenant(payload.tenant_id) as session:
        await replace_grai_eval_pair_results(
            session,
            eval_run_id=payload.eval_run_id,
            tenant_id=payload.tenant_id,
            suite_id=run_row.suite_id,
            prompt_id=pair.prompt.prompt_id,
            case_id=pair.case.case_id,
            destination_index=pair.destination.destination_index,
            rows=rows,
        )

    usage_input_tokens = sum(max(0, int(evaluation.input_tokens)) for evaluation in evaluations)
    usage_output_tokens = sum(max(0, int(evaluation.output_tokens)) for evaluation in evaluations)
    usage_request_count = sum(max(0, int(evaluation.request_count)) for evaluation in evaluations)
    effective_provider_id = str(judge_provider_id or "").strip()
    if (usage_input_tokens or usage_output_tokens or usage_request_count) and effective_provider_id:
        try:
            async with _session_for_tenant(payload.tenant_id) as session:
                await record_provider_usage(
                    session,
                    tenant_id=payload.tenant_id,
                    provider_id=effective_provider_id,
                    usage_key=grai_eval_pair_usage_key(
                        eval_run_id=payload.eval_run_id,
                        provider_id=effective_provider_id,
                        destination_index=pair.destination.destination_index,
                        prompt_id=pair.prompt.prompt_id,
                        case_id=pair.case.case_id,
                    ),
                    runtime_scope="judge",
                    capability="judge",
                    eval_run_id=payload.eval_run_id,
                    input_tokens=usage_input_tokens,
                    output_tokens=usage_output_tokens,
                    request_count=usage_request_count,
                    source="grai_eval_worker",
                )
        except Exception:
            observe_provider_usage_write_failure(
                runtime_scope="judge",
                capability="judge",
                source="grai_eval_worker",
            )
            logger.warning(
                "provider.usage.write_failed",
                extra={
                    "tenant_id": payload.tenant_id,
                    "provider_id": effective_provider_id,
                    "runtime_scope": "judge",
                    "capability": "judge",
                    "eval_run_id": payload.eval_run_id,
                },
                exc_info=True,
            )
    return PairEvaluationResult(pair_failed=pair_failed)


async def run_grai_eval(ctx: dict[str, object], *, payload: dict[str, object]) -> dict[str, object]:
    job = GraiEvalJobPayload.model_validate(payload)
    if database.AsyncSessionLocal is None:
        await database.init_db()

    run_row, prompts, cases, destinations, progress = await _load_run_state(job)
    if run_row is None:
        logger.warning("grai eval run missing", extra={"eval_run_id": job.eval_run_id})
        return {"status": "missing", "eval_run_id": job.eval_run_id}

    completed_count, failed_count = _counts_from_progress(progress)
    dispatched_count = completed_count + failed_count

    if run_row.status == GraiEvalRunStatus.CANCELLED.value:
        return {
            "status": GraiEvalRunStatus.CANCELLED.value,
            "terminal_outcome": GraiEvalRunTerminalOutcome.CANCELLED.value,
            "eval_run_id": job.eval_run_id,
            "dispatched_count": dispatched_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
        }

    processed_pairs = set(progress)
    pending_pairs = [
        PairWorkItem(prompt=prompt, case=case, destination=destination)
        for prompt in prompts
        for case in cases
        for destination in destinations
        if (prompt.prompt_id, case.case_id, destination.destination_index) not in processed_pairs
    ]
    concurrency_limit = max(1, settings.eval_concurrency_limit)
    rate_limiter = _RequestRateLimiter(settings.eval_requests_per_second)
    try:
        runtime_context: dict[str, object] | None = await _load_eval_judge_runtime_context(
            job.tenant_id
        )
    except Exception:
        logger.warning(
            "eval_judge_runtime_context_load_failed",
            extra={"eval_run_id": job.eval_run_id, "tenant_id": job.tenant_id},
            exc_info=True,
        )
        runtime_context = None
    anthropic_client, judge_vendor, judge_model, judge_provider_id = _build_eval_judge_client(
        runtime_context
    )
    clients = {
        destination.destination_index: DirectHTTPBotClient(
            context=DirectHTTPTransportContext(
                run_id=job.eval_run_id,
                transport_profile_id=destination.transport_profile_id,
                endpoint=destination.endpoint_at_start,
                headers=dict(destination.headers_at_start or {}),
                direct_http_config=dict(destination.direct_http_config_at_start or {}),
            )
        )
        for destination in destinations
    }

    with api_metrics.GRAI_EVAL_RUNS_INFLIGHT.track_inprogress():
        logger.info(
            "grai_eval_run_started",
            extra={
                "eval_run_id": job.eval_run_id,
                "tenant_id": job.tenant_id,
                "pending_pairs": len(pending_pairs),
                "dispatched_count": dispatched_count,
                "completed_count": completed_count,
                "failed_count": failed_count,
                "judge_provider_id": judge_provider_id,
                "judge_vendor": judge_vendor,
                "judge_model": judge_model,
            },
        )
        await _persist_progress(
            job,
            status=GraiEvalRunStatus.RUNNING.value,
            terminal_outcome=None,
            dispatched_count=dispatched_count,
            completed_count=completed_count,
            failed_count=failed_count,
        )
        try:
            for batch_start in range(0, len(pending_pairs), concurrency_limit):
                if await _is_cancelled(job):
                    await _persist_progress(
                        job,
                        status=GraiEvalRunStatus.CANCELLED.value,
                        terminal_outcome=GraiEvalRunTerminalOutcome.CANCELLED,
                        dispatched_count=dispatched_count,
                        completed_count=completed_count,
                        failed_count=failed_count,
                    )
                    observe_run_terminal(outcome="cancelled")
                    logger.info(
                        "grai_eval_run_cancelled",
                        extra={
                            "eval_run_id": job.eval_run_id,
                            "tenant_id": job.tenant_id,
                            "dispatched_count": dispatched_count,
                            "completed_count": completed_count,
                            "failed_count": failed_count,
                        },
                    )
                    return {
                        "status": GraiEvalRunStatus.CANCELLED.value,
                        "terminal_outcome": GraiEvalRunTerminalOutcome.CANCELLED.value,
                        "eval_run_id": job.eval_run_id,
                        "dispatched_count": dispatched_count,
                        "completed_count": completed_count,
                        "failed_count": failed_count,
                    }

                batch = pending_pairs[batch_start : batch_start + concurrency_limit]
                dispatched_count += len(batch)
                await _persist_progress(
                    job,
                    status=GraiEvalRunStatus.RUNNING.value,
                    terminal_outcome=None,
                    dispatched_count=dispatched_count,
                    completed_count=completed_count,
                    failed_count=failed_count,
                )
                results = await asyncio.gather(
                    *[
                        _evaluate_pair(
                                payload=job,
                                run_row=run_row,
                                pair=pair,
                                client=clients[pair.destination.destination_index],
                                rate_limiter=rate_limiter,
                                anthropic_client=anthropic_client,
                                llm_model=judge_model,
                                judge_provider_id=judge_provider_id,
                            )
                        for pair in batch
                    ],
                    return_exceptions=True,
                )
                batch_error: BaseException | None = None
                for result in results:
                    if isinstance(result, BaseException):
                        if batch_error is None:
                            batch_error = result
                    elif result.pair_failed:
                        failed_count += 1
                    else:
                        completed_count += 1
                if batch_error is not None:
                    raise batch_error
                if await _is_cancelled(job):
                    await _persist_progress(
                        job,
                        status=GraiEvalRunStatus.CANCELLED.value,
                        terminal_outcome=GraiEvalRunTerminalOutcome.CANCELLED,
                        dispatched_count=dispatched_count,
                        completed_count=completed_count,
                        failed_count=failed_count,
                    )
                    observe_run_terminal(outcome="cancelled")
                    logger.info(
                        "grai_eval_run_cancelled",
                        extra={
                            "eval_run_id": job.eval_run_id,
                            "tenant_id": job.tenant_id,
                            "dispatched_count": dispatched_count,
                            "completed_count": completed_count,
                            "failed_count": failed_count,
                        },
                    )
                    return {
                        "status": GraiEvalRunStatus.CANCELLED.value,
                        "terminal_outcome": GraiEvalRunTerminalOutcome.CANCELLED.value,
                        "eval_run_id": job.eval_run_id,
                        "dispatched_count": dispatched_count,
                        "completed_count": completed_count,
                        "failed_count": failed_count,
                    }
                await _persist_progress(
                    job,
                    status=GraiEvalRunStatus.RUNNING.value,
                    terminal_outcome=None,
                    dispatched_count=dispatched_count,
                    completed_count=completed_count,
                    failed_count=failed_count,
                )

            terminal_status = (
                GraiEvalRunStatus.FAILED.value if failed_count else GraiEvalRunStatus.COMPLETE.value
            )
            terminal_outcome_enum = (
                GraiEvalRunTerminalOutcome.ASSERTION_FAILED
                if failed_count
                else GraiEvalRunTerminalOutcome.PASSED
            )
            await _persist_progress(
                job,
                status=terminal_status,
                terminal_outcome=terminal_outcome_enum,
                dispatched_count=dispatched_count,
                completed_count=completed_count,
                failed_count=failed_count,
            )
            observe_run_terminal(outcome=terminal_status)
            logger.info(
                "grai_eval_run_finished",
                extra={
                    "eval_run_id": job.eval_run_id,
                    "tenant_id": job.tenant_id,
                    "status": terminal_status,
                    "dispatched_count": dispatched_count,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "judge_provider_id": judge_provider_id,
                    "judge_vendor": judge_vendor,
                    "judge_model": judge_model,
                },
            )
            return {
                "status": terminal_status,
                "terminal_outcome": terminal_outcome_enum.value,
                "eval_run_id": job.eval_run_id,
                "dispatched_count": dispatched_count,
                "completed_count": completed_count,
                "failed_count": failed_count,
            }
        except Exception:
            await _persist_progress(
                job,
                status=GraiEvalRunStatus.FAILED.value,
                terminal_outcome=GraiEvalRunTerminalOutcome.EXECUTION_FAILED,
                dispatched_count=dispatched_count,
                completed_count=completed_count,
                failed_count=failed_count,
            )
            observe_run_terminal(outcome="error")
            logger.exception(
                "grai_eval_run_failed",
                extra={
                    "eval_run_id": job.eval_run_id,
                    "tenant_id": job.tenant_id,
                    "dispatched_count": dispatched_count,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "judge_provider_id": judge_provider_id,
                    "judge_vendor": judge_vendor,
                    "judge_model": judge_model,
                },
            )
            raise
        finally:
            await asyncio.gather(*(client.aclose() for client in clients.values()))


async def on_startup(ctx: dict[str, object]) -> None:
    setup_tracing("botcheck-grai-eval-worker")
    await database.init_db()


async def on_shutdown(ctx: dict[str, object]) -> None:
    await database.close_db()


def _redis_settings() -> ArqRedisSettings:
    parsed = urlparse(settings.redis_url)
    return ArqRedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
    )


class WorkerSettings:
    functions = [run_grai_eval]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = _redis_settings()
    queue_name = "arq:eval"
    max_jobs = 1
    job_timeout = settings.eval_job_timeout_s
