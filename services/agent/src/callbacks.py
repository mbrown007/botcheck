from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import httpx
import tenacity
from botcheck_scenarios import ConversationTurn, ScenarioDefinition

from .telemetry import inject_trace_context_into_headers

def api_headers(*, harness_secret: str) -> dict[str, str]:
    return inject_trace_context_into_headers({"Authorization": f"Bearer {harness_secret}"})


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception(is_retryable),
    reraise=True,
)
async def post_with_retry(
    path: str,
    payload: dict,
    *,
    botcheck_api_url: str,
    harness_secret: str,
) -> None:
    async with httpx.AsyncClient(
        base_url=botcheck_api_url,
        headers=api_headers(harness_secret=harness_secret),
    ) as client:
        resp = await client.post(path, json=payload)
        resp.raise_for_status()


async def fetch_scenario(
    scenario_id: str,
    *,
    botcheck_api_url: str,
    harness_secret: str,
) -> ScenarioDefinition:
    async with httpx.AsyncClient(
        base_url=botcheck_api_url,
        headers=api_headers(harness_secret=harness_secret),
    ) as client:
        resp = await client.get(f"/scenarios/{scenario_id}")
        resp.raise_for_status()
        return ScenarioDefinition.model_validate(resp.json())


async def fetch_run_transport_context(
    run_id: str,
    *,
    botcheck_api_url: str,
    harness_secret: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=botcheck_api_url,
        headers=api_headers(harness_secret=harness_secret),
    ) as client:
        resp = await client.get(f"/runs/{run_id}/transport-context")
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def fetch_provider_runtime_context(
    *,
    tenant_id: str,
    runtime_scope: str,
    tts_voice: str | None,
    stt_provider: str | None,
    stt_model: str | None,
    botcheck_api_url: str,
    harness_secret: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(
        base_url=botcheck_api_url,
        headers=api_headers(harness_secret=harness_secret),
        timeout=httpx.Timeout(5.0),
    ) as client:
        resp = await client.post(
            "/providers/internal/runtime-context",
            json={
                "tenant_id": tenant_id,
                "runtime_scope": runtime_scope,
                "tts_voice": tts_voice,
                "stt_provider": stt_provider,
                "stt_model": stt_model,
            },
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def post_playground_event(
    run_id: str,
    *,
    event_type: str,
    payload: dict[str, object],
    post_with_retry_fn,
    callbacks_total,
) -> None:
    try:
        await post_with_retry_fn(
            f"/runs/{run_id}/events",
            {
                "event_type": event_type,
                "payload": payload,
            },
        )
    except Exception:
        callbacks_total.labels(endpoint="playground_events", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="playground_events", outcome="success").inc()


async def report_turn(
    run_id: str,
    turn: ConversationTurn,
    *,
    visit: int | None,
    branch_condition_matched: str | None,
    branch_response_snippet: str | None,
    post_with_retry_fn,
    callbacks_total,
    turns_total,
) -> None:
    payload = turn.model_dump(mode="json")
    if isinstance(visit, int) and visit > 0:
        payload["visit"] = visit
    if isinstance(branch_condition_matched, str) and branch_condition_matched.strip():
        payload["branch_condition_matched"] = branch_condition_matched.strip()
    if isinstance(branch_response_snippet, str) and branch_response_snippet.strip():
        payload["branch_response_snippet"] = branch_response_snippet.strip()[:120]

    try:
        await post_with_retry_fn(
            f"/runs/{run_id}/turns",
            payload,
        )
    except Exception:
        callbacks_total.labels(endpoint="turns", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="turns", outcome="success").inc()
    turn_outcome = "timeout" if turn.speaker == "bot" and turn.text == "(timeout)" else "normal"
    turns_total.labels(speaker=turn.speaker, outcome=turn_outcome).inc()


async def complete_run(
    run_id: str,
    conversation: list[ConversationTurn],
    *,
    end_reason: str,
    end_source: str,
    post_with_retry_fn,
    callbacks_total,
) -> None:
    try:
        await post_with_retry_fn(
            f"/runs/{run_id}/complete",
            {
                "conversation": [t.model_dump(mode="json") for t in conversation],
                "end_reason": end_reason,
                "end_source": end_source,
            },
        )
    except Exception:
        callbacks_total.labels(endpoint="complete", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="complete", outcome="success").inc()


async def fail_run_with_details(
    run_id: str,
    reason: str,
    *,
    end_reason: str,
    error_code: str | None,
    loop_guard: dict[str, object] | None,
    post_with_retry_fn,
    callbacks_total,
) -> None:
    payload: dict[str, object] = {
        "reason": reason,
        "end_reason": end_reason,
        "end_source": "harness",
    }
    if loop_guard:
        payload["loop_guard"] = loop_guard
    if isinstance(error_code, str) and error_code.strip():
        payload["error_code"] = error_code.strip()
    try:
        await post_with_retry_fn(
            f"/runs/{run_id}/fail",
            payload,
        )
    except Exception:
        callbacks_total.labels(endpoint="fail", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="fail", outcome="success").inc()


async def post_run_heartbeat(
    run_id: str,
    *,
    seq: int,
    sent_at: datetime,
    turn_number: int | None,
    listener_state: str | None,
    post_with_retry_fn,
    callbacks_total,
) -> None:
    payload: dict[str, object] = {
        "sent_at": sent_at.astimezone(UTC).isoformat(),
        "seq": seq,
    }
    if isinstance(turn_number, int) and turn_number > 0:
        payload["turn_number"] = turn_number
    if isinstance(listener_state, str) and listener_state.strip():
        payload["listener_state"] = listener_state.strip().lower()[:64]
    try:
        await post_with_retry_fn(
            f"/runs/{run_id}/heartbeat",
            payload,
        )
    except Exception:
        callbacks_total.labels(endpoint="heartbeat", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="heartbeat", outcome="success").inc()


async def post_provider_circuit_state(
    *,
    source: Literal["agent", "judge", "api"],
    provider: str,
    service: str,
    component: str,
    state: Literal["open", "half_open", "closed"],
    observed_at: datetime | None,
    post_with_retry_fn,
    callbacks_total,
) -> None:
    payload: dict[str, object] = {
        "source": source,
        "provider": provider.strip().lower(),
        "service": service.strip().lower(),
        "component": component.strip().lower(),
        "state": state,
    }
    if observed_at is not None:
        payload["observed_at"] = observed_at.astimezone(UTC).isoformat()
    try:
        await post_with_retry_fn(
            "/internal/provider-circuits/state",
            payload,
        )
    except Exception:
        callbacks_total.labels(endpoint="provider_circuit", outcome="error").inc()
        raise
    callbacks_total.labels(endpoint="provider_circuit", outcome="success").inc()


async def upload_run_recording(
    run_id: str,
    *,
    wav_path,
    duration_ms: int,
    botcheck_api_url: str,
    harness_secret: str,
    timeout_s: float,
) -> None:
    payload = await asyncio.to_thread(wav_path.read_bytes)
    if not payload:
        return
    async with httpx.AsyncClient(
        base_url=botcheck_api_url,
        headers=api_headers(harness_secret=harness_secret),
        timeout=timeout_s,
    ) as client:
        resp = await client.put(
            f"/runs/{run_id}/recording",
            params={"format": "wav", "duration_ms": duration_ms},
            headers={"Content-Type": "audio/wav"},
            content=payload,
        )
        resp.raise_for_status()
