from types import SimpleNamespace

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import PackRunItemRow, PackRunRow, RunRow, ScenarioKind
from sqlalchemy import select

from _packs_test_helpers import (
    _create_pack_and_snapshot,
    _link_run_to_pack_item,
    _livekit_mock,
    _upload_scenario,
)
from factories import (
    make_pack_upsert_payload,
    make_run_create_payload,
    make_run_fail_payload,
    make_run_patch_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)
from scenario_test_helpers import _set_scenario_kind


async def test_pack_runs_list_filters_by_state_and_pack_id(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    first_scenario = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-list-a",
        name="Pack Run List A",
    )
    second_scenario = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-list-b",
        name="Pack Run List B",
    )
    first_pack_id, first_pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="List Pack A",
        scenario_ids=[first_scenario],
    )
    _, second_pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="List Pack B",
        scenario_ids=[second_scenario],
    )

    dispatch_resp = await client.post(
        f"/packs/internal/{first_pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200

    list_resp = await client.get("/pack-runs/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    listed_ids = {entry["pack_run_id"] for entry in list_resp.json()}
    assert {first_pack_run_id, second_pack_run_id}.issubset(listed_ids)

    running_resp = await client.get("/pack-runs/?state=running", headers=user_auth_headers)
    assert running_resp.status_code == 200
    running = running_resp.json()
    assert [entry["pack_run_id"] for entry in running] == [first_pack_run_id]

    pack_filter_resp = await client.get(
        f"/pack-runs/?pack_id={first_pack_id}",
        headers=user_auth_headers,
    )
    assert pack_filter_resp.status_code == 200
    assert [entry["pack_run_id"] for entry in pack_filter_resp.json()] == [first_pack_run_id]

async def test_pack_run_children_show_pre_dispatch_failure_without_run(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-child-failure",
        name="Pack Run Child Failure",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Child Failure Pack",
        scenario_ids=[scenario_id],
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        item.state = "failed"
        item.error_code = "scenario_version_mismatch"
        item.error_detail = "Scenario changed after pack snapshot"
        await session.commit()

    resp = await client.get(f"/pack-runs/{pack_run_id}/runs", headers=user_auth_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["pack_run_id"] == pack_run_id
    assert payload["total"] == 1
    child = payload["items"][0]
    assert child["run_id"] is None
    assert child["state"] == "failed"
    assert child["error_code"] == "scenario_version_mismatch"
    assert child["duration_s"] is None
    assert child["failure_category"] == "dispatch_error"


async def test_pack_run_children_ai_dispatch_unavailable_marks_dispatch_error(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", False)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-ai-dispatch-disabled",
        name="Pack Run AI Dispatch Disabled",
    )
    await _set_scenario_kind(scenario_id, ScenarioKind.AI.value)
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="AI Dispatch Disabled Pack",
        scenario_ids=[scenario_id],
    )

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    dispatch_payload = dispatch_resp.json()
    assert dispatch_payload["applied"] is True
    assert dispatch_payload["state"] == "failed"

    children_resp = await client.get(
        f"/pack-runs/{pack_run_id}/runs",
        headers=user_auth_headers,
    )
    assert children_resp.status_code == 200
    payload = children_resp.json()
    assert payload["total"] == 1
    child = payload["items"][0]
    assert child["state"] == "failed"
    assert child["run_id"] is None
    assert child["error_code"] == "ai_scenario_dispatch_unavailable"
    assert child["failure_category"] == "dispatch_error"

    detail_resp = await client.get(f"/pack-runs/{pack_run_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["state"] == "failed"
    assert detail["gate_outcome"] == "blocked"
    assert detail["failed"] == 1
    assert detail["completed"] == 1

async def test_pack_run_children_failures_only_and_failure_priority_pagination(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_a = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-filter-a",
        name="Pack Run Filter A",
    )
    scenario_b = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-filter-b",
        name="Pack Run Filter B",
    )
    scenario_c = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-filter-c",
        name="Pack Run Filter C",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Children Filter Pack",
        scenario_ids=[scenario_a, scenario_b, scenario_c],
    )

    run_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_b),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    blocked_run_id = run_resp.json()["run_id"]

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 3
        items[0].state = "failed"
        items[0].error_code = "scenario_version_mismatch"
        items[1].state = "dispatched"
        items[1].run_id = blocked_run_id
        items[2].state = "complete"

        blocked_row = await session.get(RunRow, blocked_run_id)
        assert blocked_row is not None
        blocked_row.pack_run_id = pack_run_id
        blocked_row.state = "complete"
        blocked_row.gate_result = "blocked"
        await session.commit()

    resp = await client.get(
        f"/pack-runs/{pack_run_id}/runs?failures_only=true&sort_by=failures_first&limit=10",
        headers=user_auth_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 2
    assert [child["scenario_id"] for child in payload["items"]] == [scenario_b, scenario_a]

    second_page_resp = await client.get(
        f"/pack-runs/{pack_run_id}/runs?failures_only=true&sort_by=failures_first&limit=1&offset=1",
        headers=user_auth_headers,
    )
    assert second_page_resp.status_code == 200
    second_page = second_page_resp.json()
    assert second_page["total"] == 2
    assert len(second_page["items"]) == 1
    assert second_page["items"][0]["scenario_id"] == scenario_a

async def test_judge_patch_updates_pack_run_aggregate_and_heatmap(
    client,
    user_auth_headers,
    judge_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-judge-aggregate",
        name="Pack Run Judge Aggregate",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Judge Aggregate Pack",
        scenario_ids=[scenario_id],
    )
    run_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    run_id = run_resp.json()["run_id"]
    await _link_run_to_pack_item(
        pack_run_id=pack_run_id,
        run_id=run_id,
        item_state="dispatched",
        run_state="judging",
    )

    patch_resp = await client.patch(
        f"/runs/{run_id}",
        json=make_run_patch_payload(
            gate_result="blocked",
            overall_status="fail",
            cost_pence=137,
            failed_dimensions=["policy"],
            scores={
                "jailbreak": 0.8,
                "policy": {"metric_type": "score", "score": 0.4},
            },
        ),
        headers=judge_auth_headers,
    )
    assert patch_resp.status_code == 200

    detail_resp = await client.get(f"/pack-runs/{pack_run_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["state"] == "partial"
    assert detail["gate_outcome"] == "blocked"
    assert detail["completed"] == 1
    assert detail["blocked"] == 1
    assert detail["passed"] == 0
    assert detail["failed"] == 0
    assert detail["cost_pence"] == 137
    assert detail["dimension_heatmap"]["jailbreak"]["avg_score"] == 0.8
    assert detail["dimension_heatmap"]["policy"]["avg_score"] == 0.4
    assert detail["dimension_heatmap"]["policy"]["fail_count"] == 1

    children_resp = await client.get(
        f"/pack-runs/{pack_run_id}/runs",
        headers=user_auth_headers,
    )
    assert children_resp.status_code == 200
    child = children_resp.json()["items"][0]
    assert isinstance(child["duration_s"], (int, float))
    assert child["duration_s"] >= 0
    assert child["cost_pence"] == 137
    assert child["failure_category"] == "gate_blocked"

async def test_pack_run_detail_exposes_previous_heatmap_for_trend(
    client,
    user_auth_headers,
    judge_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-prev-heatmap",
        name="Pack Run Previous Heatmap",
    )
    create_pack_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Trend Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_pack_resp.status_code == 201
    pack_id = create_pack_resp.json()["pack_id"]

    first_run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert first_run_resp.status_code == 202
    first_pack_run_id = first_run_resp.json()["pack_run_id"]

    first_child_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert first_child_resp.status_code == 202
    first_child_run_id = first_child_resp.json()["run_id"]
    await _link_run_to_pack_item(
        pack_run_id=first_pack_run_id,
        run_id=first_child_run_id,
        item_state="dispatched",
        run_state="judging",
    )
    first_patch_resp = await client.patch(
        f"/runs/{first_child_run_id}",
        json=make_run_patch_payload(
            gate_result="passed",
            overall_status="pass",
            scores={"jailbreak": 0.4},
        ),
        headers=judge_auth_headers,
    )
    assert first_patch_resp.status_code == 200

    second_run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert second_run_resp.status_code == 202
    second_pack_run_id = second_run_resp.json()["pack_run_id"]

    second_child_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert second_child_resp.status_code == 202
    second_child_run_id = second_child_resp.json()["run_id"]
    await _link_run_to_pack_item(
        pack_run_id=second_pack_run_id,
        run_id=second_child_run_id,
        item_state="dispatched",
        run_state="judging",
    )
    second_patch_resp = await client.patch(
        f"/runs/{second_child_run_id}",
        json=make_run_patch_payload(
            gate_result="passed",
            overall_status="pass",
            scores={"jailbreak": 0.8},
        ),
        headers=judge_auth_headers,
    )
    assert second_patch_resp.status_code == 200

    detail_resp = await client.get(f"/pack-runs/{second_pack_run_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["dimension_heatmap"]["jailbreak"]["avg_score"] == 0.8
    assert detail["previous_pack_run_id"] == first_pack_run_id
    assert detail["previous_dimension_heatmap"]["jailbreak"]["avg_score"] == 0.4

async def test_fail_callback_updates_pack_run_failed_counters(
    client,
    user_auth_headers,
    harness_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-fail-aggregate",
        name="Pack Run Fail Aggregate",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Fail Aggregate Pack",
        scenario_ids=[scenario_id],
    )
    run_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    run_id = run_resp.json()["run_id"]
    await _link_run_to_pack_item(
        pack_run_id=pack_run_id,
        run_id=run_id,
        item_state="dispatched",
        run_state="running",
    )

    fail_resp = await client.post(
        f"/runs/{run_id}/fail",
        json=make_run_fail_payload(reason="Harness crashed"),
        headers=harness_auth_headers,
    )
    assert fail_resp.status_code == 200

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        assert pack_run.blocked == 0
        assert pack_run.state == "failed"
        assert pack_run.gate_outcome == "blocked"
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "failed"

    children_resp = await client.get(
        f"/pack-runs/{pack_run_id}/runs",
        headers=user_auth_headers,
    )
    assert children_resp.status_code == 200
    child = children_resp.json()["items"][0]
    assert child["run_id"] == run_id
    assert child["failure_category"] == "run_error"

async def test_judge_patch_blocked_non_gated_scenario_counts_as_passed(
    client,
    user_auth_headers,
    judge_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(
            make_scenario_yaml(
                scenario_id="pack-run-non-gated",
                name="Pack Run Non-Gated",
                overrides={"scoring": {"overall_gate": False}},
            )
        ),
        headers=user_auth_headers,
    )
    assert scenario_resp.status_code == 201
    scenario_id = scenario_resp.json()["id"]

    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Non-Gated Pack",
        scenario_ids=[scenario_id],
    )
    run_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    run_id = run_resp.json()["run_id"]
    await _link_run_to_pack_item(
        pack_run_id=pack_run_id,
        run_id=run_id,
        item_state="dispatched",
        run_state="judging",
    )

    patch_resp = await client.patch(
        f"/runs/{run_id}",
        json=make_run_patch_payload(
            gate_result="blocked",
            overall_status="fail",
        ),
        headers=judge_auth_headers,
    )
    assert patch_resp.status_code == 200

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.completed == 1
        assert pack_run.passed == 1
        assert pack_run.blocked == 0
        assert pack_run.failed == 0
        assert pack_run.state == "complete"
        assert pack_run.gate_outcome == "passed"

async def test_cancel_pack_run_from_pending_prevents_dispatch(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-pending",
        name="Pack Run Cancel Pending",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Cancel Pending Pack",
        scenario_ids=[scenario_id],
    )

    cancel_resp = await client.post(
        f"/pack-runs/{pack_run_id}/cancel",
        headers=user_auth_headers,
    )
    assert cancel_resp.status_code == 200
    cancel_payload = cancel_resp.json()
    assert cancel_payload["applied"] is True
    assert cancel_payload["state"] == "cancelled"
    assert cancel_payload["reason"] == "applied"

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    dispatch_payload = dispatch_resp.json()
    assert dispatch_payload["applied"] is False
    assert dispatch_payload["state"] == "cancelled"
    assert dispatch_payload["reason"] == "not_pending"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "cancelled"
        assert pack_run.gate_outcome == "cancelled"
        assert pack_run.dispatched == 0
        assert pack_run.completed == 1
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "cancelled"
        assert item.error_code == "pack_cancelled"
        assert item.run_id is None

async def test_mark_failed_pack_run_from_pending_marks_remaining_items_failed(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mark-failed-pending",
        name="Pack Run Mark Failed Pending",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Mark Failed Pending Pack",
        scenario_ids=[scenario_id],
    )

    mark_resp = await client.post(
        f"/pack-runs/{pack_run_id}/mark-failed",
        json={"reason": "Operator failed this pack run"},
        headers=user_auth_headers,
    )
    assert mark_resp.status_code == 200
    payload = mark_resp.json()
    assert payload["applied"] is True
    assert payload["state"] == "failed"
    assert payload["reason"] == "applied"

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["applied"] is False
    assert dispatch_resp.json()["state"] == "failed"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "failed"
        assert pack_run.gate_outcome == "blocked"
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "failed"
        assert item.error_code == "pack_marked_failed"
        assert item.error_detail == "Operator failed this pack run"

async def test_cancel_pack_run_is_idempotent_for_cancelled_pack_run(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-idempotent",
        name="Pack Run Cancel Idempotent",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Cancel Idempotent Pack",
        scenario_ids=[scenario_id],
    )

    first = await client.post(f"/pack-runs/{pack_run_id}/cancel", headers=user_auth_headers)
    assert first.status_code == 200
    assert first.json()["applied"] is True

    second = await client.post(f"/pack-runs/{pack_run_id}/cancel", headers=user_auth_headers)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["applied"] is False
    assert second_payload["state"] == "cancelled"
    assert second_payload["reason"] == "already_cancelled"

async def test_mark_failed_pack_run_returns_409_for_terminal_pack_run(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mark-failed-terminal",
        name="Pack Run Mark Failed Terminal",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Mark Failed Terminal Pack",
        scenario_ids=[scenario_id],
    )
    cancel_resp = await client.post(f"/pack-runs/{pack_run_id}/cancel", headers=user_auth_headers)
    assert cancel_resp.status_code == 200

    mark_resp = await client.post(
        f"/pack-runs/{pack_run_id}/mark-failed",
        headers=user_auth_headers,
    )
    assert mark_resp.status_code == 409
    assert "cannot mark pack run failed" in mark_resp.json()["detail"].lower()

async def test_cancel_pack_run_marks_remaining_pending_items_cancelled(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_a = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-remaining-a",
        name="Pack Run Cancel Remaining A",
    )
    scenario_b = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-remaining-b",
        name="Pack Run Cancel Remaining B",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Cancel Remaining Pending Pack",
        scenario_ids=[scenario_a, scenario_b],
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        pack_run.state = "running"
        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 2
        items[0].state = "dispatched"
        items[0].run_id = "run_pack_cancel_remaining_1"
        await session.commit()

    cancel_resp = await client.post(
        f"/pack-runs/{pack_run_id}/cancel",
        headers=user_auth_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["applied"] is True

    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "cancelled"
        assert pack_run.gate_outcome == "cancelled"
        assert pack_run.completed == 1

        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 2
        assert items[0].state == "dispatched"
        assert items[1].state == "cancelled"
        assert items[1].error_code == "pack_cancelled"
        assert items[1].error_detail == "Pack run cancelled before dispatch"

async def test_cancel_pack_run_from_running_marks_cancelled(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(
        "botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI",
        lambda *args, **kwargs: _livekit_mock(),
    )
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-running",
        name="Pack Run Cancel Running",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Cancel Running Pack",
        scenario_ids=[scenario_id],
    )

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["state"] == "running"

    cancel_resp = await client.post(
        f"/pack-runs/{pack_run_id}/cancel",
        headers=user_auth_headers,
    )
    assert cancel_resp.status_code == 200
    cancel_payload = cancel_resp.json()
    assert cancel_payload["applied"] is True
    assert cancel_payload["state"] == "cancelled"
    assert cancel_payload["reason"] == "applied"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "cancelled"
        assert pack_run.gate_outcome == "cancelled"
        assert pack_run.dispatched == 1

async def test_dispatch_stops_when_pack_run_cancelled_mid_fanout(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_a = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-mid-a",
        name="Pack Run Cancel Mid A",
    )
    scenario_b = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-mid-b",
        name="Pack Run Cancel Mid B",
    )
    _, pack_run_id = await _create_pack_and_snapshot(
        client,
        user_auth_headers,
        name="Cancel Mid Fanout Pack",
        scenario_ids=[scenario_a, scenario_b],
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    dispatch_calls = 0

    async def _fake_create_run_internal(*, body, **kwargs):
        nonlocal dispatch_calls
        dispatch_calls += 1
        if dispatch_calls == 1:
            async with factory() as session:
                row = await session.get(PackRunRow, pack_run_id)
                assert row is not None
                row.state = "cancelled"
                row.gate_outcome = "cancelled"
                await session.commit()
        return SimpleNamespace(run_id=f"run_pack_cancel_mid_{dispatch_calls}")

    monkeypatch.setattr("botcheck_api.packs.packs.create_run_internal", _fake_create_run_internal)

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    payload = dispatch_resp.json()
    assert payload["state"] == "cancelled"
    assert dispatch_calls == 1

    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "cancelled"
        assert pack_run.gate_outcome == "cancelled"
        assert pack_run.dispatched == 1

        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 2
        assert items[0].state == "dispatched"
        assert items[0].run_id == "run_pack_cancel_mid_1"
        assert items[1].state == "pending"
        assert items[1].run_id is None

async def test_cancel_pack_run_returns_409_for_terminal_pack_run(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-cancel-terminal",
        name="Pack Run Cancel Terminal",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Cancel Terminal Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    update_resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(
            make_scenario_yaml(
                scenario_id=scenario_id,
                name="Pack Run Cancel Terminal Updated",
            )
        ),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 201

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["state"] == "failed"

    cancel_resp = await client.post(
        f"/pack-runs/{pack_run_id}/cancel",
        headers=user_auth_headers,
    )
    assert cancel_resp.status_code == 409
    assert "cannot cancel" in cancel_resp.json()["detail"].lower()


async def test_pack_run_missing_routes_return_error_code(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    detail_resp = await client.get("/pack-runs/packrun_missing", headers=user_auth_headers)
    assert detail_resp.status_code == 404
    assert detail_resp.json()["error_code"] == "pack_run_not_found"

    children_resp = await client.get("/pack-runs/packrun_missing/runs", headers=user_auth_headers)
    assert children_resp.status_code == 404
    assert children_resp.json()["error_code"] == "pack_run_not_found"

    cancel_resp = await client.post("/pack-runs/packrun_missing/cancel", headers=user_auth_headers)
    assert cancel_resp.status_code == 404
    assert cancel_resp.json()["error_code"] == "pack_run_not_found"

    mark_failed_resp = await client.post(
        "/pack-runs/packrun_missing/mark-failed",
        json={"reason": "missing"},
        headers=user_auth_headers,
    )
    assert mark_failed_resp.status_code == 404
    assert mark_failed_resp.json()["error_code"] == "pack_run_not_found"
