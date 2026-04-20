from unittest.mock import AsyncMock, patch

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.exceptions import ApiProblem, HARNESS_UNAVAILABLE
from botcheck_api.main import app
from botcheck_api.models import PackRunItemRow, PackRunRow, RunRow, ScenarioKind
from sqlalchemy import select

from _packs_test_helpers import _livekit_mock, _upload_scenario
from factories import (
    make_conversation_turn,
    make_pack_upsert_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)
from scenario_test_helpers import _set_scenario_kind


def _persona_payload(name: str = "Pack Dispatch Persona") -> dict:
    return {
        "name": name,
        "system_prompt": "Act as a realistic customer caller.",
        "style": "neutral",
        "voice": "alloy",
        "is_active": True,
    }


def _ai_scenario_payload(
    *,
    scenario_id: str,
    persona_id: str,
    ai_scenario_id: str,
) -> dict:
    return {
        "ai_scenario_id": ai_scenario_id,
        "scenario_id": scenario_id,
        "persona_id": persona_id,
        "name": "Pack Run AI Dispatch",
        "scenario_brief": "Caller wants confirmation and support for a delayed flight.",
        "scenario_facts": {"booking_ref": "ABC123", "airline": "Ryanair"},
        "evaluation_objective": "Confirm the delay and explain next steps clearly.",
        "opening_strategy": "wait_for_bot_greeting",
        "is_active": True,
        "scoring_profile": "call-success",
        "dataset_source": "manual",
        "config": {"sample_count": 3},
    }


def _http_destination_payload(**overrides) -> dict:
    payload = {
        "name": "Pack HTTP Transport",
        "protocol": "http",
        "endpoint": "https://bot.internal/chat",
        "headers": {"Authorization": "Bearer pack-token"},
        "direct_http_config": {
            "method": "POST",
            "request_content_type": "json",
            "request_text_field": "message",
            "request_history_field": "history",
            "request_session_id_field": "session_id",
            "response_text_field": "response.text",
            "timeout_s": 15,
            "max_retries": 1,
        },
        "is_active": True,
    }
    payload.update(overrides)
    return payload


async def test_run_pack_enqueues_scheduler_job_and_creates_snapshot(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-scenario",
        name="Pack Run Scenario",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    payload = run_resp.json()
    assert payload["state"] == "pending"
    assert payload["total_scenarios"] == 1
    pack_run_id = payload["pack_run_id"]

    enqueue = app.state.arq_pool.enqueue_job
    assert enqueue.await_count >= 1
    args, kwargs = enqueue.call_args
    assert args[0] == "dispatch_pack_run"
    assert kwargs["_queue_name"] == "arq:scheduler"
    assert kwargs["payload"]["pack_run_id"] == pack_run_id

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "pending"
        assert pack_run.total_scenarios == 1
        item_rows = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().all()
        assert len(item_rows) == 1
        assert item_rows[0].scenario_id == scenario_id
        assert item_rows[0].state == "pending"
        assert item_rows[0].scenario_version_hash


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_internal_dispatch_runs_ai_scenario_item_when_enabled(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-ai-dispatch",
        name="Pack Run AI Dispatch",
    )
    persona_resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(),
        headers=user_auth_headers,
    )
    assert persona_resp.status_code == 201
    persona_id = persona_resp.json()["persona_id"]
    ai_resp = await client.post(
        "/scenarios/ai-scenarios",
        json=_ai_scenario_payload(
            scenario_id=scenario_id,
            persona_id=persona_id,
            ai_scenario_id="ai_pack_run_dispatch",
        ),
        headers=user_auth_headers,
    )
    assert ai_resp.status_code == 201
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Pack AI Dispatch",
            scenario_ids=[],
            items=[{"ai_scenario_id": "ai_pack_run_dispatch"}],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    payload = dispatch_resp.json()
    assert payload["applied"] is True
    assert payload["state"] == "running"

    children_resp = await client.get(f"/pack-runs/{pack_run_id}/runs", headers=user_auth_headers)
    assert children_resp.status_code == 200
    payload = children_resp.json()
    children = payload["items"]
    assert len(children) == 1
    assert children[0]["ai_scenario_id"] == "ai_pack_run_dispatch"
    assert children[0]["failure_category"] is None

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "running"
        assert pack_run.completed == 0
        assert pack_run.failed == 0
        assert pack_run.dispatched == 1
        items = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().all()
        assert len(items) == 1
        assert items[0].state == "dispatched"
        assert items[0].run_id is not None
        assert items[0].error_code is None
        run = await session.get(RunRow, items[0].run_id)
        assert run is not None
        run.conversation = [
            make_conversation_turn(
                turn_id="t_bot_1",
                turn_number=1,
                speaker="bot",
                text="Hello, thanks for calling.",
                audio_start_ms=0,
                audio_end_ms=350,
            ),
            make_conversation_turn(
                turn_id="t_harness_1",
                turn_number=2,
                speaker="harness",
                text="My Ryanair flight is delayed.",
                audio_start_ms=620,
                audio_end_ms=1020,
            ),
        ]
        await session.commit()

    latency_resp = await client.get(f"/pack-runs/{pack_run_id}/runs", headers=user_auth_headers)
    assert latency_resp.status_code == 200
    latency_payload = latency_resp.json()
    assert latency_payload["ai_latency_summary"]["ai_runs"] == 1
    assert latency_payload["ai_latency_summary"]["reply_gap_p95_ms"] == 270.0
    assert latency_payload["ai_latency_summary"]["bot_turn_duration_p95_ms"] == 350.0
    assert latency_payload["ai_latency_summary"]["harness_playback_p95_ms"] == 400.0


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_internal_dispatch_mixed_pack_continues_after_ai_dispatch_failure(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", False)

    ai_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mixed-ai-disabled",
        name="Pack Run Mixed AI Disabled",
    )
    graph_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mixed-graph",
        name="Pack Run Mixed Graph",
    )
    await _set_scenario_kind(ai_scenario_id, ScenarioKind.AI.value)

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Pack Mixed Dispatch",
            scenario_ids=[ai_scenario_id, graph_scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    dispatch_payload = dispatch_resp.json()
    assert dispatch_payload["applied"] is True
    assert dispatch_payload["state"] == "running"

    children_resp = await client.get(f"/pack-runs/{pack_run_id}/runs", headers=user_auth_headers)
    assert children_resp.status_code == 200
    by_scenario = {item["scenario_id"]: item for item in children_resp.json()["items"]}

    ai_child = by_scenario[ai_scenario_id]
    assert ai_child["state"] == "failed"
    assert ai_child["run_id"] is None
    assert ai_child["ai_scenario_id"] is None
    assert ai_child["error_code"] == "ai_scenario_dispatch_unavailable"
    assert ai_child["failure_category"] == "dispatch_error"

    graph_child = by_scenario[graph_scenario_id]
    assert graph_child["state"] == "dispatched"
    assert graph_child["run_id"] is not None
    assert graph_child["failure_category"] is None

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.state == "running"
        assert pack_run.dispatched == 1
        assert pack_run.failed == 1
        assert pack_run.completed == 1


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_run_pack_with_destination_propagates_to_child_runs(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-destination-child",
        name="Pack Run Destination Child",
    )
    destination_resp = await client.post(
        "/destinations/",
        json={
            "name": "Pack Dispatch Destination",
            "protocol": "mock",
            "endpoint": "mock://carrier-a",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    destination_id = destination_resp.json()["destination_id"]

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch Destination Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": destination_id},
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    payload = run_resp.json()
    assert payload["destination_id"] == destination_id
    assert payload["transport_profile_id"] == destination_id
    assert payload["dial_target"] is None
    pack_run_id = payload["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200

    list_resp = await client.get("/pack-runs/", headers=user_auth_headers)
    assert list_resp.status_code == 200
    listed = {entry["pack_run_id"]: entry for entry in list_resp.json()}
    assert listed[pack_run_id]["destination_id"] == destination_id
    assert listed[pack_run_id]["transport_profile_id"] == destination_id

    detail_resp = await client.get(f"/pack-runs/{pack_run_id}", headers=user_auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["destination_id"] == destination_id
    assert detail_resp.json()["transport_profile_id"] == destination_id

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.destination_id == destination_id
        assert pack_run.transport_profile_id == destination_id
        runs = (
            await session.execute(
                select(RunRow)
                .where(RunRow.pack_run_id == pack_run_id)
                .order_by(RunRow.created_at.asc())
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].destination_id_at_start == destination_id
        assert runs[0].transport_profile_id_at_start == destination_id
        assert runs[0].dial_target_at_start == "mock://carrier-a"


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_run_pack_with_transport_profile_and_dial_target_propagates_to_child_runs(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-transport-child",
        name="Pack Run Transport Child",
    )
    destination_resp = await client.post(
        "/destinations/",
        json={
            "name": "Pack Dispatch Transport",
            "protocol": "mock",
            "endpoint": "mock://default",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    destination_id = destination_resp.json()["destination_id"]

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch Transport Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={
            "transport_profile_id": destination_id,
            "dial_target": "mock://override",
        },
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    payload = run_resp.json()
    assert payload["destination_id"] == destination_id
    assert payload["transport_profile_id"] == destination_id
    assert payload["dial_target"] == "mock://override"
    pack_run_id = payload["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.destination_id == destination_id
        assert pack_run.transport_profile_id == destination_id
        assert pack_run.dial_target == "mock://override"
        runs = (
            await session.execute(
                select(RunRow)
                .where(RunRow.pack_run_id == pack_run_id)
                .order_by(RunRow.created_at.asc())
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].destination_id_at_start == destination_id
        assert runs[0].transport_profile_id_at_start == destination_id
        assert runs[0].dial_target_at_start == "mock://override"


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_run_pack_with_http_transport_profile_propagates_http_snapshot_to_child_runs(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-http-child",
        name="Pack Run HTTP Child",
    )
    destination_resp = await client.post(
        "/destinations/",
        json=_http_destination_payload(),
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    destination_id = destination_resp.json()["destination_id"]

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch HTTP Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={"transport_profile_id": destination_id},
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    payload = run_resp.json()
    assert payload["destination_id"] == destination_id
    assert payload["transport_profile_id"] == destination_id
    pack_run_id = payload["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.destination_id == destination_id
        assert pack_run.transport_profile_id == destination_id
        runs = (
            await session.execute(
                select(RunRow)
                .where(RunRow.pack_run_id == pack_run_id)
                .order_by(RunRow.created_at.asc())
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].transport == "http"
        assert runs[0].destination_id_at_start == destination_id
        assert runs[0].transport_profile_id_at_start == destination_id
        assert runs[0].dial_target_at_start == "https://bot.internal/chat"
        assert runs[0].direct_http_headers_at_start == {"Authorization": "Bearer pack-token"}
        assert runs[0].direct_http_config_at_start is not None
        assert runs[0].direct_http_config_at_start["response_text_field"] == "response.text"


async def test_run_pack_returns_503_when_queue_unavailable(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-no-queue",
        name="Pack Run No Queue",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Queue Down Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    original_pool = app.state.arq_pool
    app.state.arq_pool = None
    try:
        run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    finally:
        app.state.arq_pool = original_pool
    assert run_resp.status_code == 503
    assert run_resp.json().get("error_code") == "job_queue_unavailable"

async def test_run_pack_rejects_unknown_destination(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-destination-missing",
        name="Pack Run Destination Missing",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Pack Destination Validation",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": "dest_missing"},
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 404
    assert "destination not found" in run_resp.json()["detail"].lower()

async def test_run_pack_idempotency_rejects_destination_mismatch(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-idempotency-destination",
        name="Pack Run Idempotency Destination",
    )

    destination_a_resp = await client.post(
        "/destinations/",
        json={
            "name": "Idempotency Destination A",
            "protocol": "mock",
            "endpoint": "mock://a",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    assert destination_a_resp.status_code == 201
    destination_a = destination_a_resp.json()["destination_id"]

    destination_b_resp = await client.post(
        "/destinations/",
        json={
            "name": "Idempotency Destination B",
            "protocol": "mock",
            "endpoint": "mock://b",
            "is_active": True,
        },
        headers=user_auth_headers,
    )
    assert destination_b_resp.status_code == 201
    destination_b = destination_b_resp.json()["destination_id"]

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Idempotency Destination Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    idempotency_headers = {
        **user_auth_headers,
        "Idempotency-Key": "dedupe-key-destination-mismatch",
    }

    first_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": destination_a},
        headers=idempotency_headers,
    )
    assert first_resp.status_code == 202

    second_resp = await client.post(
        f"/packs/{pack_id}/run",
        json={"destination_id": destination_b},
        headers=idempotency_headers,
    )
    assert second_resp.status_code == 409
    assert "idempotency-key already used with a different destination_id" in (
        second_resp.json()["detail"].lower()
    )

async def test_run_pack_reuses_active_snapshot_when_idempotency_key_matches(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-idempotency",
        name="Pack Run Idempotency",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Idempotency Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    idempotency_headers = {
        **user_auth_headers,
        "Idempotency-Key": "dedupe-key-1",
    }
    enqueue = app.state.arq_pool.enqueue_job
    before = enqueue.await_count

    first_resp = await client.post(f"/packs/{pack_id}/run", headers=idempotency_headers)
    assert first_resp.status_code == 202
    first = first_resp.json()

    second_resp = await client.post(f"/packs/{pack_id}/run", headers=idempotency_headers)
    assert second_resp.status_code == 202
    second = second_resp.json()

    assert second["pack_run_id"] == first["pack_run_id"]
    assert second["state"] == first["state"]
    assert enqueue.await_count == before + 1

async def test_run_pack_idempotency_allows_new_snapshot_after_terminal_state(
    client,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-idempotency-terminal",
        name="Pack Run Idempotency Terminal",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Idempotency Terminal Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    idempotency_headers = {
        **user_auth_headers,
        "Idempotency-Key": "dedupe-key-2",
    }
    enqueue = app.state.arq_pool.enqueue_job
    before = enqueue.await_count

    first_resp = await client.post(f"/packs/{pack_id}/run", headers=idempotency_headers)
    assert first_resp.status_code == 202
    first_pack_run_id = first_resp.json()["pack_run_id"]

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await session.get(PackRunRow, first_pack_run_id)
        assert row is not None
        row.state = "failed"
        await session.commit()

    second_resp = await client.post(f"/packs/{pack_id}/run", headers=idempotency_headers)
    assert second_resp.status_code == 202
    second_pack_run_id = second_resp.json()["pack_run_id"]
    assert second_pack_run_id != first_pack_run_id
    assert enqueue.await_count == before + 2

async def test_internal_dispatch_pack_run_transitions_pending_to_running(
    client,
    user_auth_headers,
    scheduler_auth_headers,
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
        scenario_id="pack-run-internal",
        name="Pack Run Internal",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Internal Dispatch Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    forbidden = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=harness_auth_headers,
    )
    assert forbidden.status_code == 403

    first = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["applied"] is True
    assert first_body["state"] == "running"
    assert first_body["reason"] == "applied"

    second = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["applied"] is False
    assert second_body["reason"] == "no_pending_items"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.dispatched == 1
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "dispatched"
        assert item.run_id is not None
        runs = (
            await session.execute(
                select(RunRow).where(RunRow.pack_run_id == pack_run_id)
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].run_id == item.run_id


async def test_internal_dispatch_pack_run_returns_pack_run_not_found(
    client,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    resp = await client.post(
        "/packs/internal/packrun_missing_internal/dispatch",
        headers=scheduler_auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "pack_run_not_found"


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_internal_dispatch_manual_pack_uses_pack_trigger_and_backoff_capacity(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "enable_outbound_sip", True)
    monkeypatch.setattr(settings, "sip_secret_provider", "env")
    monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
    monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
    monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
    monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

    acquire = AsyncMock(return_value=True)
    try_acquire = AsyncMock(return_value=True)
    monkeypatch.setattr("botcheck_api.runs.service_lifecycle.acquire_with_backoff", acquire)
    monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-sip-capacity",
        name="Pack Run SIP Capacity",
    )
    update_resp = await client.put(
        f"/scenarios/{scenario_id}",
        json=make_scenario_upload_payload(
            make_scenario_yaml(
                scenario_id=scenario_id,
                name="Pack Run SIP Capacity",
                protocol="sip",
                endpoint="sip:bot@test.example.com",
            )
        ),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Manual Pack Capacity",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["applied"] is True

    assert acquire.await_count == 1
    assert try_acquire.await_count == 0

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        runs = (
            await session.execute(
                select(RunRow)
                .where(RunRow.pack_run_id == pack_run_id)
                .order_by(RunRow.created_at.asc())
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].trigger_source == "pack"

@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_internal_dispatch_pack_capacity_backoff_limits_dispatched_children(
    mock_lk_class,
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    monkeypatch.setattr(settings, "enable_outbound_sip", True)
    monkeypatch.setattr(settings, "sip_secret_provider", "env")
    monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
    monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
    monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
    monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])

    acquire = AsyncMock(side_effect=[True, True, True, True, True, False, False, False, False, False])
    try_acquire = AsyncMock(return_value=True)
    monkeypatch.setattr("botcheck_api.runs.service_lifecycle.acquire_with_backoff", acquire)
    monkeypatch.setattr("botcheck_api.runs.service_lifecycle.try_acquire_sip_slot", try_acquire)

    scenario_ids: list[str] = []
    for idx in range(10):
        scenario_id = f"pack-capacity-sip-{idx}"
        upload_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(
                make_scenario_yaml(
                    scenario_id=scenario_id,
                    name=f"Pack Capacity SIP {idx}",
                    protocol="sip",
                    endpoint="sip:bot@test.example.com",
                    turns=[{"id": "t1", "speaker": "harness", "text": "Hello.", "wait_for_response": True}],
                )
            ),
            headers=user_auth_headers,
        )
        assert upload_resp.status_code == 201
        scenario_ids.append(upload_resp.json()["id"])

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Pack Capacity Backoff",
            scenario_ids=scenario_ids,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["applied"] is True

    assert acquire.await_count == 10
    assert try_acquire.await_count == 0

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.total_scenarios == 10
        assert pack_run.dispatched == 5
        assert pack_run.completed == 5
        assert pack_run.failed == 5
        assert pack_run.state == "running"

        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 10
        failed_items = [item for item in items if item.state == "failed"]
        dispatched_items = [item for item in items if item.state == "dispatched"]
        assert len(failed_items) == 5
        assert len(dispatched_items) == 5
        assert all(item.error_code == "sip_capacity_exhausted" for item in failed_items)

        runs = (
            await session.execute(
                select(RunRow)
                .where(RunRow.pack_run_id == pack_run_id)
                .order_by(RunRow.created_at.asc())
            )
        ).scalars().all()
        assert len(runs) == 5
        assert all(run.trigger_source == "pack" for run in runs)

async def test_internal_dispatch_marks_version_mismatch_as_failed(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-version-mismatch",
        name="Pack Run Version Mismatch",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Version Drift Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    # Update scenario after snapshot so dispatch sees version drift.
    update_resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(
            make_scenario_yaml(
                scenario_id=scenario_id,
                name="Pack Run Version Mismatch Updated",
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
    body = dispatch_resp.json()
    assert body["state"] == "failed"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.dispatched == 0
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        assert pack_run.state == "failed"
        assert pack_run.gate_outcome == "blocked"
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "failed"
        assert item.error_code == "scenario_version_mismatch"
        assert item.run_id is None

async def test_internal_dispatch_marks_item_failed_on_unexpected_dispatch_exception(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-dispatch-exception",
        name="Pack Run Dispatch Exception",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch Exception Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    async def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("botcheck_api.packs.packs.create_run_internal", _raise_unexpected)

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    body = dispatch_resp.json()
    assert body["state"] == "failed"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.dispatched == 0
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        assert pack_run.state == "failed"
        assert pack_run.gate_outcome == "blocked"
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "failed"
        assert item.error_code == "run_dispatch_failed"
        assert item.error_detail is not None
        assert "RuntimeError: boom" in item.error_detail
        assert item.run_id is None

async def test_internal_dispatch_marks_item_failed_on_api_problem(
    client,
    user_auth_headers,
    scheduler_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-api-problem",
        name="Pack Run API Problem",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Dispatch API Problem Pack",
            scenario_ids=[scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    async def _raise_api_problem(*_args, **_kwargs):
        raise ApiProblem(
            status=503,
            error_code=HARNESS_UNAVAILABLE,
            detail="Harness agent unavailable",
        )

    monkeypatch.setattr("botcheck_api.packs.packs.create_run_internal", _raise_api_problem)

    dispatch_resp = await client.post(
        f"/packs/internal/{pack_run_id}/dispatch",
        headers=scheduler_auth_headers,
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["state"] == "failed"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.dispatched == 0
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        assert pack_run.state == "failed"
        item = (
            await session.execute(
                select(PackRunItemRow).where(PackRunItemRow.pack_run_id == pack_run_id)
            )
        ).scalars().first()
        assert item is not None
        assert item.state == "failed"
        assert item.error_code == HARNESS_UNAVAILABLE
        assert item.error_detail is not None
        assert "API 503: Harness agent unavailable" in item.error_detail
        assert item.run_id is None

async def test_internal_dispatch_mixed_version_mismatch_and_successful_dispatch(
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
    first_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mixed-a",
        name="Pack Run Mixed A",
    )
    second_scenario_id = await _upload_scenario(
        client,
        user_auth_headers,
        scenario_id="pack-run-mixed-b",
        name="Pack Run Mixed B",
    )
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Mixed Dispatch Pack",
            scenario_ids=[first_scenario_id, second_scenario_id],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    pack_run_id = run_resp.json()["pack_run_id"]

    # Drift only the first scenario so one item fails and one item dispatches.
    update_resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(
            make_scenario_yaml(
                scenario_id=first_scenario_id,
                name="Pack Run Mixed A Updated",
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
    body = dispatch_resp.json()
    assert body["state"] == "running"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        pack_run = await session.get(PackRunRow, pack_run_id)
        assert pack_run is not None
        assert pack_run.total_scenarios == 2
        assert pack_run.dispatched == 1
        assert pack_run.completed == 1
        assert pack_run.failed == 1
        assert pack_run.state == "running"
        items = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().all()
        assert len(items) == 2
        assert items[0].scenario_id == first_scenario_id
        assert items[0].state == "failed"
        assert items[0].error_code == "scenario_version_mismatch"
        assert items[0].run_id is None
        assert items[1].scenario_id == second_scenario_id
        assert items[1].state == "dispatched"
        assert items[1].run_id is not None
