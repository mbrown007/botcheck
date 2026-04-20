"""Pack-run business logic."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import yaml
from botcheck_scenarios import ScenarioDefinition
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_packs as packs_repo
from .. import repo_runs as runs_repo
from .. import repo_scenarios as scenarios_repo
from ..models import PackRunItemRow, PackRunRow, PackRunState, RunRow, RunState
from .service_models import (
    PackRunCancelResult,
    PackRunChildAggregateResult,
    PackRunDispatchStartResult,
    PackRunMarkFailedResult,
    PackRunSnapshot,
)


async def create_pack_run_snapshot(
    db: AsyncSession,
    *,
    pack_id: str,
    tenant_id: str,
    destination_id: str | None,
    transport_profile_id: str | None,
    dial_target: str | None,
    trigger_source: str,
    schedule_id: str | None,
    triggered_by: str | None,
    idempotency_key: str | None = None,
) -> PackRunSnapshot:
    pack = await packs_repo.get_scenario_pack_row_for_tenant(db, pack_id, tenant_id)
    if pack is None:
        raise LookupError("Pack not found")

    items = await packs_repo.list_scenario_pack_item_rows_for_pack(db, pack.pack_id)
    if not items:
        raise ValueError("Pack has no scenarios")

    scenario_ids = [item.scenario_id for item in items]
    scenario_rows = await scenarios_repo.list_scenario_rows_by_ids_for_tenant(
        db,
        tenant_id,
        scenario_ids,
    )
    version_by_scenario_id = {row.scenario_id: row.version_hash for row in scenario_rows}
    missing = sorted(set(scenario_ids) - set(version_by_scenario_id))
    if missing:
        raise RuntimeError(f"Pack references missing scenario IDs: {missing}")

    pack_run_id = f"packrun_{uuid4().hex[:12]}"
    pack_run_row = PackRunRow(
        pack_run_id=pack_run_id,
        pack_id=pack.pack_id,
        tenant_id=tenant_id,
        destination_id=destination_id,
        transport_profile_id=transport_profile_id,
        dial_target=dial_target,
        state=PackRunState.PENDING.value,
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        triggered_by=triggered_by,
        idempotency_key=idempotency_key,
        gate_outcome="error",
        total_scenarios=len(items),
        dispatched=0,
        completed=0,
        passed=0,
        blocked=0,
        failed=0,
    )
    await packs_repo.add_pack_run_row(db, pack_run_row)

    for item in items:
        pack_run_item = PackRunItemRow(
            pack_run_item_id=f"pritem_{uuid4().hex[:12]}",
            pack_run_id=pack_run_id,
            tenant_id=tenant_id,
            scenario_id=item.scenario_id,
            scenario_version_hash=version_by_scenario_id[item.scenario_id],
            order_index=item.order_index,
            state="pending",
            run_id=None,
            error_code=None,
            error_detail=None,
        )
        await packs_repo.add_pack_run_item_row(db, pack_run_item)

    return PackRunSnapshot(
        pack_run_id=pack_run_id,
        pack_id=pack.pack_id,
        tenant_id=tenant_id,
        destination_id=destination_id,
        transport_profile_id=transport_profile_id,
        dial_target=dial_target,
        state=PackRunState.PENDING.value,
        total_scenarios=len(items),
    )


async def start_pack_run_dispatch(
    db: AsyncSession,
    *,
    pack_run_id: str,
) -> PackRunDispatchStartResult:
    row = await packs_repo.get_pack_run_row(db, pack_run_id)
    if row is None:
        return PackRunDispatchStartResult(
            found=False,
            applied=False,
            state=PackRunState.FAILED.value,
            reason="not_found",
            tenant_id=None,
        )

    if row.state != PackRunState.PENDING.value:
        return PackRunDispatchStartResult(
            found=True,
            applied=False,
            state=row.state,
            reason="not_pending",
            tenant_id=row.tenant_id,
        )

    packs_repo.update_pack_run_state(row, PackRunState.RUNNING.value)
    return PackRunDispatchStartResult(
        found=True,
        applied=True,
        state=row.state,
        reason="applied",
        tenant_id=row.tenant_id,
    )


async def get_active_pack_run_by_idempotency(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str,
    idempotency_key: str,
) -> PackRunRow | None:
    return await packs_repo.get_active_pack_run_by_idempotency(
        db,
        tenant_id=tenant_id,
        pack_id=pack_id,
        idempotency_key=idempotency_key,
    )


async def cancel_pack_run(
    db: AsyncSession,
    *,
    pack_run_id: str,
    tenant_id: str,
) -> PackRunCancelResult:
    row = await packs_repo.get_pack_run_row_for_tenant(db, pack_run_id, tenant_id)
    if row is None:
        return PackRunCancelResult(
            found=False,
            applied=False,
            state=PackRunState.FAILED.value,
            reason="not_found",
            tenant_id=None,
        )

    if row.state == PackRunState.CANCELLED.value:
        return PackRunCancelResult(
            found=True,
            applied=False,
            state=row.state,
            reason="already_cancelled",
            tenant_id=row.tenant_id,
        )

    if row.state in {
        PackRunState.COMPLETE.value,
        PackRunState.PARTIAL.value,
        PackRunState.FAILED.value,
    }:
        return PackRunCancelResult(
            found=True,
            applied=False,
            state=row.state,
            reason="terminal",
            tenant_id=row.tenant_id,
        )

    if row.state in {PackRunState.PENDING.value, PackRunState.RUNNING.value}:
        item_rows = await packs_repo.list_pack_run_item_rows_for_pack_run(db, pack_run_id)
        for item in item_rows:
            if item.state != "pending":
                continue
            item.state = "cancelled"
            item.error_code = "pack_cancelled"
            item.error_detail = "Pack run cancelled before dispatch"
            row.completed += 1
        packs_repo.update_pack_run_state(row, PackRunState.CANCELLED.value)
        row.gate_outcome = "cancelled"
        return PackRunCancelResult(
            found=True,
            applied=True,
            state=row.state,
            reason="applied",
            tenant_id=row.tenant_id,
        )

    return PackRunCancelResult(
        found=True,
        applied=False,
        state=row.state,
        reason="invalid_state",
        tenant_id=row.tenant_id,
    )


async def mark_pack_run_failed(
    db: AsyncSession,
    *,
    pack_run_id: str,
    tenant_id: str,
    reason: str,
) -> PackRunMarkFailedResult:
    row = await packs_repo.get_pack_run_row_for_tenant(db, pack_run_id, tenant_id)
    if row is None:
        return PackRunMarkFailedResult(
            found=False,
            applied=False,
            state=PackRunState.FAILED.value,
            reason="not_found",
            tenant_id=None,
        )

    if row.state == PackRunState.FAILED.value:
        return PackRunMarkFailedResult(
            found=True,
            applied=False,
            state=row.state,
            reason="already_failed",
            tenant_id=row.tenant_id,
        )

    if row.state in {
        PackRunState.COMPLETE.value,
        PackRunState.PARTIAL.value,
        PackRunState.CANCELLED.value,
    }:
        return PackRunMarkFailedResult(
            found=True,
            applied=False,
            state=row.state,
            reason="terminal",
            tenant_id=row.tenant_id,
        )

    if row.state in {PackRunState.PENDING.value, PackRunState.RUNNING.value}:
        item_rows = await packs_repo.list_pack_run_item_rows_for_pack_run(db, pack_run_id)
        terminal_item_states = {"complete", "blocked", "failed", "cancelled"}
        for item in item_rows:
            if item.state in terminal_item_states:
                continue
            item.state = "failed"
            item.error_code = "pack_marked_failed"
            item.error_detail = reason
            row.completed += 1
            row.failed += 1

        packs_repo.update_pack_run_state(row, PackRunState.FAILED.value)
        row.gate_outcome = "blocked"
        return PackRunMarkFailedResult(
            found=True,
            applied=True,
            state=row.state,
            reason="applied",
            tenant_id=row.tenant_id,
        )

    return PackRunMarkFailedResult(
        found=True,
        applied=False,
        state=row.state,
        reason="invalid_state",
        tenant_id=row.tenant_id,
    )


async def get_pack_run_for_tenant(
    db: AsyncSession,
    *,
    pack_run_id: str,
    tenant_id: str,
) -> PackRunRow | None:
    return await packs_repo.get_pack_run_row_for_tenant(db, pack_run_id, tenant_id)


async def list_pack_runs_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str | None = None,
    state: str | None = None,
    limit: int = 100,
) -> list[PackRunRow]:
    return await packs_repo.list_pack_run_rows_for_tenant(
        db,
        tenant_id,
        pack_id=pack_id,
        state=state,
        limit=limit,
    )


async def get_previous_pack_run_for_tenant_pack(
    db: AsyncSession,
    *,
    tenant_id: str,
    pack_id: str,
    created_before: datetime,
    pack_run_id: str,
) -> PackRunRow | None:
    return await packs_repo.get_previous_pack_run_row_for_tenant_pack(
        db,
        tenant_id=tenant_id,
        pack_id=pack_id,
        created_before=created_before,
        pack_run_id=pack_run_id,
    )


async def list_pack_run_items(
    db: AsyncSession,
    *,
    pack_run_id: str,
) -> list[PackRunItemRow]:
    return await packs_repo.list_pack_run_item_rows_for_pack_run(db, pack_run_id)


async def aggregate_pack_run_child_terminal_state(
    db: AsyncSession,
    *,
    run: RunRow,
) -> PackRunChildAggregateResult:
    if not run.pack_run_id:
        return PackRunChildAggregateResult(
            found=False,
            applied=False,
            pack_run_id=None,
            item_state=None,
            pack_run_state=None,
            reason="run_not_linked",
        )
    pack_run = await packs_repo.get_pack_run_row_for_tenant(db, run.pack_run_id, run.tenant_id)
    if pack_run is None:
        return PackRunChildAggregateResult(
            found=False,
            applied=False,
            pack_run_id=run.pack_run_id,
            item_state=None,
            pack_run_state=None,
            reason="pack_run_not_found",
        )
    item = await packs_repo.get_pack_run_item_row_for_run_id(db, run.run_id)
    if item is None:
        return PackRunChildAggregateResult(
            found=False,
            applied=False,
            pack_run_id=pack_run.pack_run_id,
            item_state=None,
            pack_run_state=pack_run.state,
            reason="pack_run_item_not_found",
        )

    terminal_item_states = {"complete", "blocked", "failed", "cancelled"}
    if item.state in terminal_item_states:
        return PackRunChildAggregateResult(
            found=True,
            applied=False,
            pack_run_id=pack_run.pack_run_id,
            item_state=item.state,
            pack_run_state=pack_run.state,
            reason="item_already_terminal",
        )

    run_state = str(run.state or "").strip().lower()
    if run_state not in {
        RunState.COMPLETE.value,
        RunState.FAILED.value,
        RunState.ERROR.value,
    }:
        return PackRunChildAggregateResult(
            found=True,
            applied=False,
            pack_run_id=pack_run.pack_run_id,
            item_state=item.state,
            pack_run_state=pack_run.state,
            reason="run_not_terminal",
        )

    blocked_delta = 0
    failed_delta = 0
    passed_delta = 0

    if run_state in {RunState.FAILED.value, RunState.ERROR.value}:
        item_state = "failed"
        failed_delta = 1
    else:
        gate_result = str(run.gate_result or "").strip().lower()
        if gate_result == "blocked":
            is_gated = True
            scenario_row = await scenarios_repo.get_scenario_row_for_tenant(
                db,
                run.scenario_id,
                run.tenant_id,
            )
            if scenario_row is not None:
                try:
                    raw = yaml.safe_load(scenario_row.yaml_content)
                    scenario = ScenarioDefinition.model_validate(raw)
                    is_gated = bool(scenario.scoring.overall_gate)
                except Exception:
                    is_gated = True
            if is_gated:
                item_state = "blocked"
                blocked_delta = 1
            else:
                item_state = "complete"
                passed_delta = 1
        elif gate_result in {"passed", "not_applicable", ""}:
            item_state = "complete"
            passed_delta = 1
        else:
            item_state = "failed"
            failed_delta = 1

    item.state = item_state
    if item_state == "failed":
        item.error_code = run.error_code
        item.error_detail = run.summary or item.error_detail

    pack_run.completed += 1
    pack_run.blocked += blocked_delta
    pack_run.failed += failed_delta
    pack_run.passed += passed_delta

    if pack_run.completed >= pack_run.total_scenarios:
        if pack_run.state == PackRunState.CANCELLED.value:
            pack_run.gate_outcome = "cancelled"
        elif pack_run.blocked > 0:
            pack_run.state = PackRunState.PARTIAL.value
            pack_run.gate_outcome = "blocked"
        elif pack_run.failed > 0:
            pack_run.state = PackRunState.FAILED.value
            pack_run.gate_outcome = "blocked"
        else:
            pack_run.state = PackRunState.COMPLETE.value
            pack_run.gate_outcome = "passed"

    return PackRunChildAggregateResult(
        found=True,
        applied=True,
        pack_run_id=pack_run.pack_run_id,
        item_state=item_state,
        pack_run_state=pack_run.state,
        reason="applied",
    )
