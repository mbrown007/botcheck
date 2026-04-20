"""Run state, scoring, heartbeat, and event helper functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Literal

import logging

from botcheck_scenarios import ErrorCode
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..capacity import DEFAULT_SIP_CAPACITY_SCOPE, build_sip_slot_key
from ..models import CacheStatus, RunRow, RunState
from ..redaction import redact_turn_payload
from .store_service import append_run_event
from .service_models import EndReason, HeartbeatStatus, RunScore

logger = logging.getLogger("botcheck.api.runs")

VALID_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PENDING: {RunState.RUNNING, RunState.FAILED, RunState.ERROR},
    RunState.RUNNING: {RunState.JUDGING, RunState.FAILED, RunState.ERROR},
    RunState.JUDGING: {RunState.COMPLETE, RunState.FAILED, RunState.ERROR},
    RunState.COMPLETE: set(),
    RunState.FAILED: set(),
    RunState.ERROR: set(),
}


def normalize_cache_status(
    value: str | None,
    *,
    default: Literal["warm", "warming", "partial", "cold"] | None = None,
) -> Literal["warm", "warming", "partial", "cold"] | None:
    normalized = str(value or "").strip().lower()
    if normalized in {
        CacheStatus.WARM.value,
        CacheStatus.WARMING.value,
        CacheStatus.PARTIAL.value,
        CacheStatus.COLD.value,
    }:
        return normalized  # type: ignore[return-value]
    return default


def parse_run_state(value: str) -> RunState:
    try:
        return RunState(value)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Unknown run state: {value}") from exc


def validate_run_transition(current: RunState, new_state: RunState) -> None:
    if current == new_state:
        return
    if new_state not in VALID_TRANSITIONS[current]:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid transition: {current.value} -> {new_state.value}",
        )


async def transition_run_state(
    db: AsyncSession,
    run: RunRow,
    new_state: RunState,
    event_type: str,
    detail: dict[str, object] | None = None,
) -> None:
    current = parse_run_state(run.state)
    validate_run_transition(current, new_state)
    if current == new_state:
        return
    now = datetime.now(UTC)
    run.state = new_state.value
    if new_state == RunState.RUNNING and run.run_started_at is None:
        run.run_started_at = now
    run.updated_at = now
    event_detail: dict[str, object] = {
        "from": current.value,
        "to": new_state.value,
    }
    if detail:
        event_detail.update(detail)
    await append_run_event(db, run.run_id, event_type, event_detail)
    api_metrics.RUN_STATE_TRANSITIONS_TOTAL.labels(
        from_state=current.value,
        to_state=new_state.value,
        source=str(event_detail.get("source", "unknown")),
    ).inc()
    _observe_run_transition_latency_metrics(run, current=current, new_state=new_state, now=now)


def _run_created_detail(run: RunRow) -> dict[str, object]:
    for raw_event in (run.events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() != "run_created":
            continue
        detail = raw_event.get("detail")
        if isinstance(detail, dict):
            return detail
    return {}


def _run_scenario_kind(run: RunRow) -> str:
    detail = _run_created_detail(run)
    kind = str(detail.get("scenario_kind") or "").strip().lower()
    return kind or "graph"


def _run_sip_trunk_id(run: RunRow) -> str:
    detail = _run_created_detail(run)
    trunk_id = str(detail.get("sip_trunk_id") or "").strip()
    return trunk_id or "unknown"


def _observe_run_transition_latency_metrics(
    run: RunRow,
    *,
    current: RunState,
    new_state: RunState,
    now: datetime,
) -> None:
    observed_at = normalize_run_datetime(now)
    created_at = normalize_run_datetime(run.created_at)

    if current == RunState.PENDING and new_state == RunState.RUNNING and run.transport == "sip":
        api_metrics.SIP_ANSWER_LATENCY_SECONDS.labels(
            trunk_id=_run_sip_trunk_id(run)
        ).observe(max(0.0, (observed_at - created_at).total_seconds()))

    if current == RunState.JUDGING and new_state in {
        RunState.COMPLETE,
        RunState.FAILED,
        RunState.ERROR,
    }:
        api_metrics.RUN_E2E_LATENCY_SECONDS.labels(
            scenario_kind=_run_scenario_kind(run),
            trigger_source=str(run.trigger_source or "manual"),
        ).observe(max(0.0, (observed_at - created_at).total_seconds()))


def parse_error_code(value: str | None, *, strict: bool = True) -> str | None:
    if value is None:
        return None
    try:
        return ErrorCode(value).value
    except ValueError:
        if not strict:
            return ErrorCode.INTERNAL.value
        raise HTTPException(status_code=422, detail=f"Invalid error_code: {value}")


def normalize_score_value(value: float | RunScore, dim: str) -> dict[str, Any]:
    if isinstance(value, (int, float)):
        return {
            "metric_type": "score",
            "score": float(value),
        }

    payload = value.model_dump(mode="json", exclude_none=True)
    metric_type = str(payload.get("metric_type", "score")).lower()
    if metric_type not in {"score", "flag"}:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid metric_type for score '{dim}': {metric_type}",
        )
    payload["metric_type"] = metric_type

    if metric_type == "score":
        if "score" not in payload:
            raise HTTPException(
                status_code=422,
                detail=f"Missing score value for score metric '{dim}'",
            )
        return payload

    passed = payload.get("passed")
    if passed is None:
        if "score" in payload:
            threshold = float(payload.get("threshold", 0.5))
            passed = float(payload["score"]) >= threshold
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Missing passed value for flag metric '{dim}'",
            )
    payload["passed"] = bool(passed)
    payload["score"] = 1.0 if payload["passed"] else 0.0
    return payload


def normalize_scores(scores: dict[str, float | RunScore]) -> dict[str, dict[str, Any]]:
    return {dim: normalize_score_value(value, dim) for dim, value in scores.items()}


def deserialize_scores(raw_scores: dict[str, Any] | None) -> dict[str, RunScore]:
    if not raw_scores:
        return {}
    scores: dict[str, RunScore] = {}
    for dim, raw in raw_scores.items():
        try:
            if isinstance(raw, (int, float)):
                scores[dim] = RunScore(metric_type="score", score=float(raw))
                continue
            if isinstance(raw, dict):
                payload = dict(raw)
                metric_type = str(payload.get("metric_type", "score")).lower()
                if metric_type not in {"score", "flag"}:
                    metric_type = "score"
                payload["metric_type"] = metric_type
                if metric_type == "flag" and "passed" in payload and "score" not in payload:
                    payload["score"] = 1.0 if bool(payload["passed"]) else 0.0
                scores[dim] = RunScore.model_validate(payload)
                continue
            logger.warning("Skipping invalid score payload for dimension %s", dim)
        except Exception:
            logger.warning("Skipping invalid score payload for dimension %s", dim, exc_info=True)
    return scores


def parse_end_reason(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return EndReason(value).value
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid end_reason: {value}") from exc


def derive_end_reason(conversation: list[dict]) -> str:
    if any(str(turn.get("text", "")) == "(timeout)" for turn in conversation):
        return EndReason.TIMEOUT.value
    return EndReason.MAX_TURNS_REACHED.value


def parse_end_source(value: object) -> str:
    if value is None:
        return "harness"
    text = str(value).strip().lower()
    if not text:
        raise HTTPException(status_code=422, detail="Invalid end_source")
    if len(text) > 64:
        raise HTTPException(status_code=422, detail="Invalid end_source")
    return text


def parse_loop_guard_event_detail(
    value: object,
    *,
    end_reason: str,
    end_source: str,
) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    guard = str(value.get("guard") or "").strip().lower()
    if guard not in {
        EndReason.PER_TURN_LOOP_LIMIT.value,
        EndReason.MAX_TURNS_REACHED.value,
    }:
        return None

    detail: dict[str, object] = {
        "source": "harness_fail",
        "guard": guard,
        "end_reason": end_reason,
        "end_source": end_source,
    }
    turn_id = str(value.get("turn_id") or "").strip()
    if turn_id:
        detail["turn_id"] = turn_id
    visit = parse_turn_visit(value.get("visit"))
    if visit is not None:
        detail["visit"] = visit
    effective_cap = parse_turn_number(value.get("effective_cap"))
    if effective_cap is not None:
        detail["effective_cap"] = effective_cap
    max_visits = parse_turn_number(value.get("max_visits"))
    if max_visits is not None:
        detail["max_visits"] = max_visits
    return detail


def parse_turn_number(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def parse_turn_visit(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def derive_turn_visit(conversation: list[dict], *, turn_id: str) -> int:
    return 1 + sum(1 for t in conversation if str(t.get("turn_id")) == turn_id)


def normalize_branch_snippet(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    bounded = trimmed[:120]
    redacted = redact_turn_payload({"text": bounded}).get("text")
    if isinstance(redacted, str):
        return redacted[:120]
    return bounded


async def release_run_sip_slot_if_held(
    db: AsyncSession,
    run: RunRow,
    *,
    redis_pool: object | None,
    slot_ttl_s: int,
    release_sip_slot: Callable[..., Awaitable[object]],
    reason: str,
) -> bool:
    if run.transport != "sip" or not run.sip_slot_held:
        return False
    await release_sip_slot(
        redis_pool=redis_pool,
        slot_ttl_s=slot_ttl_s,
        slot_key=sip_slot_key_for_run(run),
    )
    api_metrics.SIP_SLOTS_ACTIVE.dec()
    run.sip_slot_held = False
    await append_run_event(
        db,
        run.run_id,
        "sip_slot_released",
        {"reason": reason},
    )
    return True


def build_taken_path_steps(events: list[dict[str, object]] | None) -> list[dict[str, object]]:
    if not events:
        return []

    seen: set[tuple[str, int, int]] = set()
    steps: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "turn_executed":
            continue
        detail = event.get("detail")
        if not isinstance(detail, dict):
            continue
        turn_id = str(detail.get("turn_id") or "").strip()
        visit = parse_turn_visit(detail.get("visit"))
        turn_number = parse_turn_number(detail.get("turn_number"))
        if not turn_id or visit is None or turn_number is None:
            continue
        key = (turn_id, visit, turn_number)
        if key in seen:
            continue
        seen.add(key)
        steps.append(
            {
                "turn_id": turn_id,
                "visit": visit,
                "turn_number": turn_number,
            }
        )

    steps.sort(key=lambda step: int(step["turn_number"]))
    return steps


async def append_path_event_dedup(
    *,
    db: AsyncSession,
    run: RunRow,
    event_type: Literal["turn_executed", "branch_decision"],
    turn_id: str,
    visit: int,
    turn_number: int,
    detail: dict[str, object] | None = None,
) -> bool:
    dedupe_key = f"{event_type}:{turn_id}:{visit}:{turn_number}"
    for event in run.events or []:
        if not isinstance(event, dict) or event.get("type") != event_type:
            continue
        event_detail = event.get("detail")
        if not isinstance(event_detail, dict):
            continue
        if event_detail.get("dedupe_key") == dedupe_key:
            return False
        if (
            event_detail.get("turn_id") == turn_id
            and event_detail.get("visit") == visit
            and event_detail.get("turn_number") == turn_number
        ):
            return False

    payload: dict[str, object] = {
        "turn_id": turn_id,
        "visit": visit,
        "turn_number": turn_number,
        "dedupe_key": dedupe_key,
    }
    if detail:
        payload.update(detail)
    await append_run_event(db, run.run_id, event_type, payload)
    return True


def parse_recording_format(value: object) -> str:
    if value is None:
        return "wav"
    text = str(value).strip().lower()
    if text not in {"wav"}:
        raise HTTPException(status_code=422, detail=f"Unsupported recording format: {text}")
    return text


def build_recording_s3_key(*, run_id: str, tenant_id: str, fmt: str) -> str:
    now = datetime.now(UTC)
    return f"{tenant_id}/recordings/{now.year}/{now.month:02d}/{now.day:02d}/{run_id}.{fmt}"


def is_tts_cache_s3_key(key: str | None) -> bool:
    if not key:
        return False
    parts = key.split("/")
    return len(parts) >= 3 and parts[1] == "tts-cache"


def normalize_run_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def run_started_at_or_created_at(run: RunRow) -> datetime:
    started = run.run_started_at or run.created_at
    return normalize_run_datetime(started)


def run_elapsed_seconds(run: RunRow, *, now: datetime) -> float:
    started = run_started_at_or_created_at(run)
    return max(0.0, (normalize_run_datetime(now) - started).total_seconds())


def run_effective_max_duration_s(run: RunRow, *, default_s: float = 300.0) -> float:
    snapshot = run.max_duration_s_at_start
    if isinstance(snapshot, (int, float)) and snapshot > 0:
        return float(snapshot)
    return float(default_s)


def run_last_heartbeat_age_s(run: RunRow, *, now: datetime) -> float | None:
    if run.last_heartbeat_at is None:
        return None
    return max(
        0.0,
        (normalize_run_datetime(now) - normalize_run_datetime(run.last_heartbeat_at)).total_seconds(),
    )


def sip_slot_key_for_run(run: RunRow) -> str:
    scope = DEFAULT_SIP_CAPACITY_SCOPE
    value = getattr(run, "capacity_scope_at_start", None)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            scope = candidate
    return build_sip_slot_key(tenant_id=run.tenant_id, capacity_scope=scope)


def apply_run_heartbeat(
    run: RunRow,
    *,
    seq: int,
    received_at: datetime,
) -> HeartbeatStatus:
    state = parse_run_state(run.state)
    if state == RunState.RUNNING:
        current_seq = run.last_heartbeat_seq
        if isinstance(current_seq, int) and seq <= current_seq:
            return HeartbeatStatus.DUPLICATE_OR_STALE
        run.last_heartbeat_seq = seq
        run.last_heartbeat_at = normalize_run_datetime(received_at)
        run.updated_at = datetime.now(UTC)
        return HeartbeatStatus.UPDATED
    if state in {
        RunState.JUDGING,
        RunState.COMPLETE,
        RunState.FAILED,
        RunState.ERROR,
    }:
        return HeartbeatStatus.IGNORED_TERMINAL
    raise HTTPException(status_code=409, detail=f"Cannot record heartbeat while run is {state.value}")
