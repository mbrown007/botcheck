from unittest.mock import patch

import pytest

from botcheck_api import database
from botcheck_api.main import app
from botcheck_api.models import AuditLogRow
from botcheck_api.runs import service_judge
from botcheck_api.runs.service_judge import rejudge_run
from sqlalchemy import select

from factories import make_run_complete_payload, make_run_patch_payload
from runs_test_helpers import SAMPLE_CONVERSATION, _create_run, _livekit_mock


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_rejudge_run_reenqueues_completed_run(
    mock_lk_class,
    client,
    uploaded_scenario,
    user_auth_headers,
    harness_auth_headers,
    judge_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr(
        service_judge,
        "current_w3c_trace_context",
        lambda: {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "tracestate": "vendor=test",
        },
    )
    run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

    complete_resp = await client.post(
        f"/runs/{run_id}/complete",
        json=make_run_complete_payload(conversation=SAMPLE_CONVERSATION),
        headers=harness_auth_headers,
    )
    assert complete_resp.status_code == 200

    patch_resp = await client.patch(
        f"/runs/{run_id}",
        json=make_run_patch_payload(gate_result="passed", summary="initial score"),
        headers=judge_auth_headers,
    )
    assert patch_resp.status_code == 200

    app.state.arq_pool.enqueue_job.reset_mock()
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        result = await rejudge_run(
            db,
            run_id=run_id,
            actor_id="operator_admin",
            arq_pool=app.state.arq_pool,
            reason="scoring rules updated",
        )
        await db.commit()

    assert result.run_id == run_id
    assert result.previous_state == "complete"
    assert result.state == "judging"
    assert result.tool_context_replayed is False

    app.state.arq_pool.enqueue_job.assert_awaited_once()
    args, kwargs = app.state.arq_pool.enqueue_job.await_args
    assert args[0] == "judge_run"
    assert kwargs["_queue_name"] == "arq:judge"
    payload = kwargs["payload"]
    assert payload["run_id"] == run_id
    assert payload["scenario_id"] == uploaded_scenario["id"]
    assert payload["tool_context"] == []
    # Rejudge must produce a new root span — trace context must be absent so the
    # judge worker opens judge.run as a disconnected root, not a child of the
    # admin operator's request span.
    assert "traceparent" not in payload
    assert "tracestate" not in payload

    run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["state"] == "judging"
    reenqueue_events = [e for e in run_data["events"] if e["type"] == "judge_reenqueued"]
    assert len(reenqueue_events) == 1
    assert reenqueue_events[0]["detail"]["tool_context_replayed"] is False
    assert reenqueue_events[0]["detail"]["reason"] == "scoring rules updated"

    async with database.AsyncSessionLocal() as db:
        audit_rows = (
            await db.execute(
                select(AuditLogRow)
                .where(
                    AuditLogRow.resource_id == run_id,
                    AuditLogRow.action == "run.rejudge",
                )
            )
        ).scalars().all()
        assert len(audit_rows) == 1
        assert audit_rows[0].detail["tool_context_replayed"] is False


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_rejudge_run_rejects_non_terminal_run(
    mock_lk_class,
    client,
    uploaded_scenario,
    user_auth_headers,
):
    mock_lk_class.return_value = _livekit_mock()
    run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="Run must be terminal"):
            await rejudge_run(
                db,
                run_id=run_id,
                actor_id="operator_admin",
                arq_pool=app.state.arq_pool,
            )
