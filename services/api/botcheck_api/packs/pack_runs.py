from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import UserContext, require_viewer
from ..config import settings
from ..database import get_db
from ..exceptions import ApiProblem, PACK_RUN_NOT_FOUND, SCENARIO_PACKS_DISABLED
from ..models import PackRunRow, PackRunState, RunRow
from ..runs.store_service import list_runs_by_ids
from ..scenarios.store_service import list_ai_scenarios
from .pack_run_schemas import (
    DimensionHeatmapEntry,
    PackRunCancelResponse,
    PackRunChildSummaryResponse,
    PackRunChildrenResponse,
    PackRunDetailResponse,
    PackRunMarkFailedRequest,
    PackRunMarkFailedResponse,
    PackRunSummaryResponse,
)
from .service import (
    cancel_pack_run as cancel_pack_run_record,
    get_pack_run_for_tenant,
    get_previous_pack_run_for_tenant_pack,
    get_scenario_pack,
    list_pack_run_items,
    list_pack_runs_for_tenant,
    mark_pack_run_failed as mark_pack_run_failed_record,
)

router = APIRouter()


def _require_packs_enabled() -> None:
    if not settings.feature_packs_enabled:
        raise ApiProblem(
            status=503,
            error_code=SCENARIO_PACKS_DISABLED,
            detail="Scenario packs are disabled",
        )


def _summary_response(row: PackRunRow) -> PackRunSummaryResponse:
    return PackRunSummaryResponse(
        pack_run_id=row.pack_run_id,
        pack_id=row.pack_id,
        destination_id=row.destination_id,
        transport_profile_id=row.transport_profile_id,
        dial_target=row.dial_target,
        state=row.state,
        trigger_source=row.trigger_source,
        schedule_id=row.schedule_id,
        triggered_by=row.triggered_by,
        gate_outcome=row.gate_outcome,
        total_scenarios=row.total_scenarios,
        dispatched=row.dispatched,
        completed=row.completed,
        passed=row.passed,
        blocked=row.blocked,
        failed=row.failed,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _score_from_payload(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        raw = value.get("score")
        if isinstance(raw, (int, float)):
            return float(raw)
    return None


def _build_dimension_heatmap(runs: list[RunRow]) -> dict[str, DimensionHeatmapEntry]:
    aggregates: dict[str, dict[str, float | int]] = {}
    for run in runs:
        raw_scores = run.scores or {}
        if isinstance(raw_scores, dict):
            for dimension, raw_score in raw_scores.items():
                key = str(dimension).strip()
                if not key:
                    continue
                parsed = _score_from_payload(raw_score)
                if parsed is None:
                    continue
                entry = aggregates.setdefault(key, {"sum": 0.0, "count": 0, "fail_count": 0})
                entry["sum"] = float(entry["sum"]) + parsed
                entry["count"] = int(entry["count"]) + 1

        failed_dimensions = run.failed_dimensions or []
        for dimension in {str(value).strip() for value in failed_dimensions if str(value).strip()}:
            entry = aggregates.setdefault(dimension, {"sum": 0.0, "count": 0, "fail_count": 0})
            entry["fail_count"] = int(entry["fail_count"]) + 1

    heatmap: dict[str, DimensionHeatmapEntry] = {}
    for dimension in sorted(aggregates):
        aggregate = aggregates[dimension]
        count = int(aggregate["count"])
        avg_score = round(float(aggregate["sum"]) / count, 4) if count > 0 else None
        heatmap[dimension] = DimensionHeatmapEntry(
            avg_score=avg_score,
            fail_count=int(aggregate["fail_count"]),
        )
    return heatmap


def _rollup_cost_pence(runs: list[RunRow], expected_count: int) -> int | None:
    if expected_count <= 0:
        return 0
    if len(runs) != expected_count:
        return None
    if any(run.cost_pence is None for run in runs):
        return None
    return sum(int(run.cost_pence or 0) for run in runs)


def _child_is_failure(child: PackRunChildSummaryResponse) -> bool:
    run_state = (child.run_state or "").lower()
    item_state = (child.state or "").lower()
    gate_result = (child.gate_result or "").lower()
    return (
        gate_result == "blocked"
        or run_state == "failed"
        or run_state == "error"
        or item_state == "failed"
    )


def _child_failure_priority(child: PackRunChildSummaryResponse) -> int:
    run_state = (child.run_state or "").lower()
    item_state = (child.state or "").lower()
    gate_result = (child.gate_result or "").lower()
    if gate_result == "blocked":
        return 0
    if run_state == "failed" or run_state == "error" or item_state == "failed":
        return 1
    if run_state == "running" or item_state == "dispatched" or item_state == "pending":
        return 2
    if run_state == "complete" or item_state == "complete":
        return 3
    return 4


def _derive_failure_category(
    *,
    item_state: str,
    run_state: str | None,
    gate_result: str | None,
    run_id: str | None,
) -> Literal["dispatch_error", "run_error", "gate_blocked"] | None:
    normalized_gate = (gate_result or "").strip().lower()
    normalized_run = (run_state or "").strip().lower()
    normalized_item = (item_state or "").strip().lower()
    if normalized_gate == "blocked":
        return "gate_blocked"
    if normalized_run in {"failed", "error"}:
        return "run_error"
    if normalized_item == "failed" and not (run_id or "").strip():
        return "dispatch_error"
    return None


def _child_duration_s(run: RunRow | None) -> float | None:
    if run is None:
        return None
    start = run.run_started_at or run.created_at
    end = run.updated_at or run.created_at
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    return round(max(0.0, seconds), 3)


def _quantile_ms(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) * quantile) + 0.999999) - 1))
    return round(float(ordered[index]), 3)


def _run_ai_latency_summary(run: RunRow | None) -> dict[str, list[float]] | None:
    if run is None or not isinstance(run.conversation, list):
        return None
    reply_gap_values: list[float] = []
    bot_turn_duration_values: list[float] = []
    harness_playback_values: list[float] = []
    conversation = run.conversation
    for index, raw_turn in enumerate(conversation):
        if not isinstance(raw_turn, dict):
            continue
        speaker = str(raw_turn.get("speaker") or "").strip().lower()
        start_ms = raw_turn.get("audio_start_ms")
        end_ms = raw_turn.get("audio_end_ms")
        if isinstance(start_ms, (int, float)) and isinstance(end_ms, (int, float)) and end_ms >= start_ms:
            duration_ms = float(end_ms) - float(start_ms)
            if speaker == "bot":
                bot_turn_duration_values.append(duration_ms)
            elif speaker == "harness":
                harness_playback_values.append(duration_ms)

        if speaker != "bot" or index + 1 >= len(conversation):
            continue
        next_turn = conversation[index + 1]
        if not isinstance(next_turn, dict):
            continue
        next_speaker = str(next_turn.get("speaker") or "").strip().lower()
        next_start_ms = next_turn.get("audio_start_ms")
        if (
            next_speaker == "harness"
            and isinstance(end_ms, (int, float))
            and isinstance(next_start_ms, (int, float))
            and next_start_ms >= end_ms
        ):
            reply_gap_values.append(float(next_start_ms) - float(end_ms))

    if not reply_gap_values and not bot_turn_duration_values and not harness_playback_values:
        return None
    return {
        "reply_gap_values": reply_gap_values,
        "bot_turn_duration_values": bot_turn_duration_values,
        "harness_playback_values": harness_playback_values,
    }


def _aggregate_pack_ai_latency(children: list[PackRunChildSummaryResponse], run_by_id: dict[str, RunRow]) -> dict[str, float | int | None] | None:
    reply_gap_values: list[float] = []
    bot_turn_duration_values: list[float] = []
    harness_playback_values: list[float] = []
    ai_runs = 0

    for child in children:
        if not child.ai_scenario_id or not child.run_id:
            continue
        run = run_by_id.get(child.run_id)
        summary = _run_ai_latency_summary(run)
        if summary is None:
            continue
        ai_runs += 1
        reply_gap_values.extend(summary["reply_gap_values"])
        bot_turn_duration_values.extend(summary["bot_turn_duration_values"])
        harness_playback_values.extend(summary["harness_playback_values"])

    if ai_runs == 0:
        return None
    return {
        "ai_runs": ai_runs,
        "reply_gap_p95_ms": _quantile_ms(reply_gap_values, 0.95),
        "bot_turn_duration_p95_ms": _quantile_ms(bot_turn_duration_values, 0.95),
        "harness_playback_p95_ms": _quantile_ms(harness_playback_values, 0.95),
    }


@router.get("/", response_model=list[PackRunSummaryResponse])
async def list_pack_runs(
    pack_id: str | None = None,
    state: PackRunState | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    rows = await list_pack_runs_for_tenant(
        db,
        tenant_id=user.tenant_id,
        pack_id=pack_id,
        state=state.value if state is not None else None,
        limit=limit,
    )
    return [_summary_response(row) for row in rows]


@router.get("/{pack_run_id}", response_model=PackRunDetailResponse)
async def get_pack_run(
    pack_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    row = await get_pack_run_for_tenant(db, pack_run_id=pack_run_id, tenant_id=user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )

    items = await list_pack_run_items(db, pack_run_id=row.pack_run_id)
    run_ids = [item.run_id for item in items if item.run_id]
    runs = await list_runs_by_ids(db, run_ids=run_ids, tenant_id=user.tenant_id)
    heatmap = _build_dimension_heatmap(runs)
    cost_pence = _rollup_cost_pence(runs, expected_count=len(run_ids))
    pack = await get_scenario_pack(db, row.pack_id, user.tenant_id)
    previous_row = await get_previous_pack_run_for_tenant_pack(
        db,
        tenant_id=user.tenant_id,
        pack_id=row.pack_id,
        created_before=row.created_at,
        pack_run_id=row.pack_run_id,
    )
    previous_heatmap: dict[str, DimensionHeatmapEntry] = {}
    if previous_row is not None:
        previous_items = await list_pack_run_items(db, pack_run_id=previous_row.pack_run_id)
        previous_run_ids = [item.run_id for item in previous_items if item.run_id]
        previous_runs = await list_runs_by_ids(
            db,
            run_ids=previous_run_ids,
            tenant_id=user.tenant_id,
        )
        previous_heatmap = _build_dimension_heatmap(previous_runs)

    return PackRunDetailResponse(
        **_summary_response(row).model_dump(),
        pack_name=pack.name if pack is not None else None,
        dimension_heatmap=heatmap,
        previous_pack_run_id=previous_row.pack_run_id if previous_row is not None else None,
        previous_dimension_heatmap=previous_heatmap,
        cost_pence=cost_pence,
    )


@router.get("/{pack_run_id}/runs", response_model=PackRunChildrenResponse)
async def list_pack_run_children(
    pack_run_id: str,
    state: str | None = None,
    gate_result: str | None = None,
    failures_only: bool = False,
    sort_by: Literal["failures_first", "order", "state", "gate_result", "scenario_id"] = "order",
    sort_dir: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    row = await get_pack_run_for_tenant(db, pack_run_id=pack_run_id, tenant_id=user.tenant_id)
    if row is None:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )

    item_rows = await list_pack_run_items(db, pack_run_id=row.pack_run_id)
    run_ids = [item.run_id for item in item_rows if item.run_id]
    runs = await list_runs_by_ids(db, run_ids=run_ids, tenant_id=user.tenant_id)
    run_by_id = {run.run_id: run for run in runs}
    ai_scenario_rows = await list_ai_scenarios(db, tenant_id=user.tenant_id)
    ai_scenario_ids_by_scenario_id = {
        ai_scenario.scenario_id: ai_scenario.ai_scenario_id for ai_scenario in ai_scenario_rows
    }

    children: list[PackRunChildSummaryResponse] = []
    for item in item_rows:
        run = run_by_id.get(item.run_id or "")
        run_state = run.state if run is not None else None
        gate_result = run.gate_result if run is not None else None
        children.append(
            PackRunChildSummaryResponse(
                pack_run_item_id=item.pack_run_item_id,
                scenario_id=item.scenario_id,
                ai_scenario_id=ai_scenario_ids_by_scenario_id.get(item.scenario_id),
                order_index=item.order_index,
                scenario_version_hash=item.scenario_version_hash,
                state=item.state,
                run_id=item.run_id,
                run_state=run_state,
                gate_result=gate_result,
                overall_status=run.overall_status if run is not None else None,
                error_code=(run.error_code if run is not None else item.error_code),
                error_detail=item.error_detail,
                failure_category=_derive_failure_category(
                    item_state=item.state,
                    run_state=run_state,
                    gate_result=gate_result,
                    run_id=item.run_id,
                ),
                summary=run.summary if run is not None else None,
                duration_s=_child_duration_s(run),
                cost_pence=run.cost_pence if run is not None else None,
                created_at=run.created_at if run is not None else None,
            )
        )

    if state:
        candidate = state.strip().lower()
        children = [
            child
            for child in children
            if child.state == candidate or (child.run_state or "").lower() == candidate
        ]
    if gate_result:
        candidate_gate = gate_result.strip().lower()
        children = [
            child for child in children if (child.gate_result or "").lower() == candidate_gate
        ]
    if failures_only:
        children = [child for child in children if _child_is_failure(child)]

    reverse = sort_dir == "desc"
    if sort_by == "failures_first":
        children.sort(
            key=lambda child: (
                _child_failure_priority(child),
                child.order_index,
                child.scenario_id,
            ),
            reverse=reverse,
        )
    elif sort_by == "state":
        children.sort(
            key=lambda child: ((child.run_state or child.state), child.order_index),
            reverse=reverse,
        )
    elif sort_by == "gate_result":
        children.sort(
            key=lambda child: ((child.gate_result or ""), child.order_index),
            reverse=reverse,
        )
    elif sort_by == "scenario_id":
        children.sort(
            key=lambda child: (child.scenario_id, child.order_index),
            reverse=reverse,
        )
    else:
        children.sort(key=lambda child: child.order_index, reverse=reverse)

    ai_latency_summary = _aggregate_pack_ai_latency(children, run_by_id)
    total = len(children)
    paged = children[offset : offset + limit]
    return PackRunChildrenResponse(
        pack_run_id=row.pack_run_id,
        total=total,
        ai_latency_summary=ai_latency_summary,
        items=paged,
    )


@router.post("/{pack_run_id}/cancel", response_model=PackRunCancelResponse)
async def cancel_pack_run(
    pack_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    result = await cancel_pack_run_record(
        db,
        pack_run_id=pack_run_id,
        tenant_id=user.tenant_id,
    )
    if not result.found:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )
    if not result.applied and result.reason == "terminal":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel pack run in state {result.state}",
        )
    if result.applied:
        await write_audit_event(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            actor_type="user",
            action="pack.run.cancelled",
            resource_type="pack_run",
            resource_id=pack_run_id,
            detail={"state": result.state},
        )
    await db.commit()
    return PackRunCancelResponse(
        pack_run_id=pack_run_id,
        applied=result.applied,
        state=result.state,
        reason=result.reason,
    )


@router.post("/{pack_run_id}/mark-failed", response_model=PackRunMarkFailedResponse)
async def mark_pack_run_failed(
    pack_run_id: str,
    body: PackRunMarkFailedRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_packs_enabled()
    reason = ((body.reason if body is not None else "") or "").strip() or "Pack run marked failed by operator"
    result = await mark_pack_run_failed_record(
        db,
        pack_run_id=pack_run_id,
        tenant_id=user.tenant_id,
        reason=reason,
    )
    if not result.found:
        raise ApiProblem(
            status=404,
            error_code=PACK_RUN_NOT_FOUND,
            detail="Pack run not found",
        )
    if not result.applied and result.reason in {"terminal", "invalid_state"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot mark pack run failed in state {result.state}",
        )
    if result.applied:
        await write_audit_event(
            db,
            tenant_id=user.tenant_id,
            actor_id=user.sub,
            actor_type="user",
            action="pack.run.marked_failed",
            resource_type="pack_run",
            resource_id=pack_run_id,
            detail={"state": result.state, "reason": reason},
        )
    await db.commit()
    return PackRunMarkFailedResponse(
        pack_run_id=pack_run_id,
        applied=result.applied,
        state=result.state,
        reason=result.reason,
    )
