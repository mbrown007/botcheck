from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from botcheck_observability.trace_contract import current_w3c_trace_context

from ..audit import write_audit_event
from ..models import RunRow, RunState
from ..scenarios import store_service as scenarios_store_service
from . import store_service as runs_store_service
from .service_state import build_taken_path_steps, parse_run_state

JUDGE_CONTRACT_VERSION = 1
AI_JUDGE_CONTRACT_VERSION = 2


def _first_harness_utterance(conversation: list[dict[str, Any]]) -> str | None:
    for turn in conversation:
        if str(turn.get("speaker") or "").strip().lower() != "harness":
            continue
        text = str(turn.get("text") or "").strip()
        if text:
            return text
    return None


def _extract_ai_context_snapshot_from_events(
    events: list[dict[str, object]] | None,
) -> dict[str, str | None] | None:
    if not events:
        return None
    for event in events:
        if str(event.get("type") or "").strip() != "run_created":
            continue
        detail = event.get("detail")
        if not isinstance(detail, dict):
            continue
        raw_ctx = detail.get("ai_context")
        if not isinstance(raw_ctx, dict):
            continue
        dataset_input = str(raw_ctx.get("dataset_input") or "").strip()
        expected_output = str(raw_ctx.get("expected_output") or "").strip()
        persona_id = str(raw_ctx.get("persona_id") or "").strip()
        if not dataset_input or not expected_output or not persona_id:
            continue
        persona_name_raw = raw_ctx.get("persona_name")
        scenario_objective_raw = raw_ctx.get("scenario_objective")
        persona_name = (
            str(persona_name_raw).strip() if isinstance(persona_name_raw, str) else None
        ) or None
        scenario_objective = (
            str(scenario_objective_raw).strip()
            if isinstance(scenario_objective_raw, str)
            else None
        ) or None
        return {
            "dataset_input": dataset_input,
            "expected_output": expected_output,
            "persona_id": persona_id,
            "persona_name": persona_name,
            "scenario_objective": scenario_objective,
        }
    return None


async def build_ai_judge_context(
    *,
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
    conversation: list[dict[str, Any]],
    run_events: list[dict[str, object]] | None,
) -> dict[str, str | None]:
    snapshot = _extract_ai_context_snapshot_from_events(run_events)
    if snapshot is not None:
        return snapshot

    ai_scenario = await scenarios_store_service.get_ai_scenario_by_scenario_id(
        db,
        scenario_id=scenario_id,
        tenant_id=tenant_id,
    )
    records = (
        await scenarios_store_service.list_ai_scenario_records(
            db,
            ai_scenario_id=ai_scenario.ai_scenario_id,
            tenant_id=tenant_id,
        )
        if ai_scenario is not None
        else []
    )
    active_records = sorted(
        [record for record in records if bool(record.is_active)],
        key=lambda record: record.order_index,
    )
    selected = active_records[0] if active_records else (records[0] if records else None)

    persona_id = (ai_scenario.persona_id if ai_scenario is not None else "").strip() or "persona_unknown"
    persona_name: str | None = None
    if ai_scenario is not None:
        persona = await scenarios_store_service.get_ai_persona(
            db,
            persona_id=ai_scenario.persona_id,
            tenant_id=tenant_id,
        )
        if persona is not None:
            persona_name = persona.display_name

    dataset_input = (
        (selected.input_text if selected is not None else "").strip()
        or (_first_harness_utterance(conversation) or "").strip()
        or f"AI scenario context unavailable for {scenario_id}"
    )
    expected_output = (
        (selected.expected_output if selected is not None else "").strip()
        or "Evaluate objective completion and policy compliance from transcript evidence."
    )
    scenario_objective = None
    if ai_scenario is not None:
        scenario_objective = (
            (ai_scenario.evaluation_objective or "").strip()
            or (ai_scenario.scenario_brief or "").strip()
            or (ai_scenario.scoring_profile or "").strip()
            or (ai_scenario.dataset_source or "").strip()
            or None
        )

    return {
        "dataset_input": dataset_input,
        "expected_output": expected_output,
        "persona_id": persona_id,
        "persona_name": persona_name,
        "scenario_objective": scenario_objective,
    }


async def build_judge_job_payload(
    db: AsyncSession,
    *,
    run: RunRow,
    tool_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scenario_data = await scenarios_store_service.get_scenario(db, run.scenario_id, run.tenant_id)
    scenario = scenario_data[0] if scenario_data else None
    if scenario is None:
        raise ValueError("Scenario not found for run")
    version_hash = scenario_data[1]

    conversation = run.conversation or []
    if not conversation:
        raise ValueError("Run has no stored conversation to judge")

    scenario_kind = (
        await scenarios_store_service.get_scenario_kind(db, run.scenario_id, run.tenant_id)
    ) or "graph"
    scenario_has_branching = any(turn.branching is not None for turn in scenario.turns)
    taken_path_steps = build_taken_path_steps(run.events or [])
    started_at = run.created_at.isoformat() if run.created_at else datetime.now(UTC).isoformat()

    judge_contract_version = JUDGE_CONTRACT_VERSION
    ai_context: dict[str, str | None] | None = None
    if scenario_kind == "ai":
        judge_contract_version = AI_JUDGE_CONTRACT_VERSION
        ai_context = await build_ai_judge_context(
            db=db,
            scenario_id=run.scenario_id,
            tenant_id=run.tenant_id,
            conversation=conversation,
            run_events=run.events or [],
        )

    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "scenario_id": run.scenario_id,
        "scenario_version_hash": version_hash,
        "tenant_id": run.tenant_id,
        "trigger_source": run.trigger_source or "manual",
        "started_at": started_at,
        "conversation": conversation,
        "tool_context": tool_context or [],
        "scenario_has_branching": scenario_has_branching,
        "taken_path_steps": taken_path_steps,
        "scenario_kind": scenario_kind,
        "judge_contract_version": judge_contract_version,
    }
    if ai_context is not None:
        payload["ai_context"] = ai_context
    payload.update(current_w3c_trace_context())
    return payload


@dataclass
class RejudgeRunResult:
    run_id: str
    previous_state: str
    state: str
    tool_context_replayed: bool


async def rejudge_run(
    db: AsyncSession,
    *,
    run_id: str,
    actor_id: str,
    arq_pool: Any,
    reason: str | None = None,
) -> RejudgeRunResult:
    if arq_pool is None:
        raise ValueError("Judge queue unavailable")

    run = await runs_store_service.get_run(db, run_id)
    if run is None:
        raise ValueError("Run not found")

    current_state = parse_run_state(run.state)
    if current_state not in {RunState.COMPLETE, RunState.FAILED, RunState.ERROR}:
        raise ValueError(f"Run must be terminal to rejudge (current state: {current_state.value})")

    payload = await build_judge_job_payload(db, run=run, tool_context=[])
    # Rejudge must start a new root span — no parent context from the original
    # run's trace. Strip W3C headers so judge_worker opens judge.run as a root.
    payload.pop("traceparent", None)
    payload.pop("tracestate", None)
    await arq_pool.enqueue_job(
        "judge_run",
        payload=payload,
        _queue_name="arq:judge",
    )

    run.state = RunState.JUDGING.value
    await runs_store_service.append_run_event(
        db,
        run.run_id,
        "judge_reenqueued",
        {
            "source": "admin_rejudge",
            "reason": reason,
            "previous_state": current_state.value,
            "tool_context_replayed": False,
        },
    )
    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id=actor_id,
        actor_type="operator",
        action="run.rejudge",
        resource_type="run",
        resource_id=run.run_id,
        detail={
            "previous_state": current_state.value,
            "reason": reason,
            "tool_context_replayed": False,
        },
    )
    return RejudgeRunResult(
        run_id=run.run_id,
        previous_state=current_state.value,
        state=RunState.JUDGING.value,
        tool_context_replayed=False,
    )
