from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.main import app
from botcheck_api.models import (
    GraiEvalCaseRow,
    GraiEvalPromptRow,
    GraiEvalResultRow,
    GraiEvalRunDestinationRow,
    GraiEvalRunRow,
    ProviderQuotaPolicyRow,
)

from factories import (
    make_grai_eval_run_payload,
    make_grai_eval_suite_payload,
    make_http_destination_payload,
)
from runs_test_helpers import _other_tenant_headers


@pytest.fixture(autouse=True)
def _enable_destinations(monkeypatch):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)


async def _create_suite_and_transport(client, user_auth_headers, *, suffix: str) -> tuple[str, str]:
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"Billing Eval Suite {suffix}"),
        headers=user_auth_headers,
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]

    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"Grai HTTP Transport {suffix}"),
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    return suite_id, transport_profile_id


async def _create_suite_and_two_transports(
    client,
    user_auth_headers,
    *,
    suffix: str,
) -> tuple[str, str, str]:
    suite_id, first_transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix=f"{suffix}-a",
    )
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"Grai HTTP Transport {suffix}-b"),
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    second_transport_profile_id = destination_resp.json()["transport_profile_id"]
    return suite_id, first_transport_profile_id, second_transport_profile_id


async def _seed_results_for_run(eval_run_id: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        run_row = await session.get(GraiEvalRunRow, eval_run_id)
        assert run_row is not None
        prompts = (
            await session.execute(
                select(GraiEvalPromptRow).where(GraiEvalPromptRow.suite_id == run_row.suite_id)
            )
        ).scalars().all()
        cases = (
            await session.execute(
                select(GraiEvalCaseRow).where(GraiEvalCaseRow.suite_id == run_row.suite_id)
            )
        ).scalars().all()
        assert len(prompts) == 1
        assert len(cases) == 1
        prompt = prompts[0]
        case = cases[0]
        now = datetime.now(UTC)
        session.add_all(
            [
                GraiEvalResultRow(
                    eval_result_id="geres_route_fail",
                    tenant_id=run_row.tenant_id,
                    suite_id=run_row.suite_id,
                    eval_run_id=run_row.eval_run_id,
                    prompt_id=prompt.prompt_id,
                    case_id=case.case_id,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=False,
                    score=None,
                    threshold=0.8,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason="missing refund",
                    latency_ms=120,
                    tags_json=["billing", "smoke-test"],
                    raw_s3_key="raw/fail.json",
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_route_pass",
                    tenant_id=run_row.tenant_id,
                    suite_id=run_row.suite_id,
                    eval_run_id=run_row.eval_run_id,
                    prompt_id=prompt.prompt_id,
                    case_id=case.case_id,
                    assertion_index=1,
                    assertion_type="icontains",
                    passed=True,
                    score=1.0,
                    threshold=0.8,
                    weight=1.0,
                    raw_value="policy",
                    failure_reason=None,
                    latency_ms=100,
                    tags_json=["billing", "smoke-test"],
                    raw_s3_key="raw/pass.json",
                    created_at=now - timedelta(seconds=1),
                    updated_at=now - timedelta(seconds=1),
                ),
            ]
        )
        run_row.status = "failed"
        run_row.terminal_outcome = "assertion_failed"
        run_row.completed_count = 1
        run_row.failed_count = 1
        run_row.dispatched_count = 1
        await session.commit()


async def _set_grai_run_summary(
    eval_run_id: str,
    *,
    status: str,
    terminal_outcome: str | None = None,
    completed_count: int,
    failed_count: int,
    dispatched_count: int,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        run_row = await session.get(GraiEvalRunRow, eval_run_id)
        assert run_row is not None
        run_row.status = status
        run_row.terminal_outcome = terminal_outcome
        run_row.completed_count = completed_count
        run_row.failed_count = failed_count
        run_row.dispatched_count = dispatched_count
        if created_at is not None:
            run_row.created_at = created_at
        if updated_at is not None:
            run_row.updated_at = updated_at
        await session.commit()


async def _insert_provider_quota_policy_row(
    *,
    provider_id: str,
    metric: str,
    limit_per_day: int,
    soft_limit_pct: int = 80,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            ProviderQuotaPolicyRow(
                quota_policy_id=f"provquota_{provider_id}_{metric}".replace(":", "_"),
                tenant_id=settings.tenant_id,
                provider_id=provider_id,
                metric=metric,
                limit_per_day=limit_per_day,
                soft_limit_pct=soft_limit_pct,
            )
        )
        await session.commit()


async def test_create_grai_run_enqueues_eval_worker_and_persists_snapshot(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-create",
    )

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["terminal_outcome"] is None
    assert body["suite_id"] == suite_id
    assert body["transport_profile_id"] == transport_profile_id
    assert body["prompt_count"] == 1
    assert body["case_count"] == 1
    assert body["total_pairs"] == 1
    eval_run_id = body["eval_run_id"]

    enqueue = app.state.arq_pool.enqueue_job
    assert enqueue.await_count >= 1
    args, kwargs = enqueue.call_args
    assert args[0] == "run_grai_eval"
    assert kwargs["_queue_name"] == "arq:eval"
    assert kwargs["payload"]["eval_run_id"] == eval_run_id
    assert kwargs["payload"]["tenant_id"]

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await session.get(GraiEvalRunRow, eval_run_id)
        assert row is not None
        assert row.status == "pending"
        assert row.endpoint_at_start == "https://bot.internal/chat"
        assert row.transport_profile_id == transport_profile_id
        assert row.total_pairs == 1
        assert row.dispatched_count == 0


async def test_create_grai_run_accepts_multiple_transport_profiles(client, user_auth_headers):
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="run-multi",
    )

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["transport_profile_id"] == transport_a
    assert body["transport_profile_ids"] == [transport_a, transport_b]
    assert [item["transport_profile_id"] for item in body["destinations"]] == [
        transport_a,
        transport_b,
    ]
    assert body["total_pairs"] == 2

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        run_row = await session.get(GraiEvalRunRow, body["eval_run_id"])
        assert run_row is not None
        assert run_row.transport_profile_id == transport_a
        destination_rows = (
            await session.execute(
                select(GraiEvalRunDestinationRow)
                .where(GraiEvalRunDestinationRow.eval_run_id == body["eval_run_id"])
                .order_by(GraiEvalRunDestinationRow.destination_index.asc())
            )
        ).scalars().all()
        assert [row.transport_profile_id for row in destination_rows] == [transport_a, transport_b]


async def test_create_grai_run_rejects_when_judge_provider_quota_reached(
    client,
    user_auth_headers,
):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-quota",
    )
    await _insert_provider_quota_policy_row(
        provider_id="anthropic:claude-sonnet-4-6",
        metric="requests",
        limit_per_day=0,
    )
    enqueue = app.state.arq_pool.enqueue_job
    before = enqueue.await_count

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )

    assert resp.status_code == 429
    assert resp.json()["error_code"] == "provider_quota_exceeded"
    assert enqueue.await_count == before


async def test_create_grai_run_rejects_non_http_or_inactive_transport(client, user_auth_headers):
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name="Billing Eval Suite invalid-transport"),
        headers=user_auth_headers,
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]

    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(
            name="Inactive Grai HTTP Transport",
            is_active=False,
        ),
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "grai_invalid_transport_profile"


async def test_get_and_cancel_grai_run_round_trip(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-cancel",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]

    get_resp = await client.get(f"/grai/runs/{eval_run_id}", headers=user_auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["eval_run_id"] == eval_run_id

    cancel_resp = await client.post(f"/grai/runs/{eval_run_id}/cancel", headers=user_auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json() == {
        "eval_run_id": eval_run_id,
        "applied": True,
        "status": "cancelled",
        "reason": "cancelled",
    }

    cancel_again_resp = await client.post(
        f"/grai/runs/{eval_run_id}/cancel",
        headers=user_auth_headers,
    )
    assert cancel_again_resp.status_code == 200
    assert cancel_again_resp.json()["applied"] is False
    assert cancel_again_resp.json()["reason"] == "already_cancelled"

    get_after_cancel = await client.get(f"/grai/runs/{eval_run_id}", headers=user_auth_headers)
    assert get_after_cancel.status_code == 200
    assert get_after_cancel.json()["status"] == "cancelled"
    assert get_after_cancel.json()["terminal_outcome"] == "cancelled"


async def test_get_grai_run_progress_reports_fraction(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-progress",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await session.get(GraiEvalRunRow, eval_run_id)
        assert row is not None
        row.status = "running"
        row.terminal_outcome = None
        row.dispatched_count = 1
        row.completed_count = 0
        row.failed_count = 1
        await session.commit()

    progress_resp = await client.get(f"/grai/runs/{eval_run_id}/progress", headers=user_auth_headers)

    assert progress_resp.status_code == 200
    assert progress_resp.json() == {
        "eval_run_id": eval_run_id,
        "status": "running",
        "terminal_outcome": None,
        "prompt_count": 1,
        "case_count": 1,
        "total_pairs": 1,
        "dispatched_count": 1,
        "completed_count": 0,
        "failed_count": 1,
        "progress_fraction": 1.0,
        "updated_at": progress_resp.json()["updated_at"],
    }


async def test_get_grai_run_report_returns_failure_focused_aggregates(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-report",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_results_for_run(eval_run_id)

    report_resp = await client.get(
        f"/grai/runs/{eval_run_id}/report?tag=billing",
        headers=user_auth_headers,
    )

    assert report_resp.status_code == 200
    body = report_resp.json()
    assert body["eval_run_id"] == eval_run_id
    assert body["status"] == "failed"
    assert body["filters"] == {
        "prompt_id": None,
        "assertion_type": None,
        "tag": "billing",
        "status": None,
        "destination_index": None,
    }
    assert body["total_results"] == 2
    assert body["passed_results"] == 1
    assert body["failed_results"] == 1
    assert body["assertion_type_breakdown"] == [
        {
            "assertion_type": "contains",
            "total_results": 1,
            "passed_results": 0,
            "failed_results": 1,
        },
        {
            "assertion_type": "icontains",
            "total_results": 1,
            "passed_results": 1,
            "failed_results": 0,
        },
    ]
    assert body["failing_prompt_variants"][0]["failure_count"] == 1
    assert body["tag_failure_clusters"][0] == {
        "tag": "billing",
        "failure_count": 1,
        "failed_pairs": 1,
    }
    assert body["exemplar_failures"][0]["eval_result_id"] == "geres_route_fail"


async def test_list_grai_run_results_supports_filters_and_cursor(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-results",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_results_for_run(eval_run_id)

    first_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results?limit=1",
        headers=user_auth_headers,
    )

    assert first_resp.status_code == 200
    first_body = first_resp.json()
    assert first_body["filters"] == {
        "prompt_id": None,
        "assertion_type": None,
        "tag": None,
        "status": None,
        "destination_index": None,
    }
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results?limit=1&cursor={first_body['next_cursor']}&status=passed",
        headers=user_auth_headers,
    )

    assert second_resp.status_code == 200
    second_body = second_resp.json()
    assert second_body["filters"] == {
        "prompt_id": None,
        "assertion_type": None,
        "tag": None,
        "status": "passed",
        "destination_index": None,
    }
    assert [item["eval_result_id"] for item in second_body["items"]] == ["geres_route_pass"]
    assert second_body["next_cursor"] is None


async def test_get_grai_run_result_artifact_returns_stored_request_response(
    client,
    user_auth_headers,
    monkeypatch,
):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-artifact",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_results_for_run(eval_run_id)

    download_mock = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "prompt_id": "prompt_artifact",
                    "case_id": "case_artifact",
                    "prompt_text": "Answer clearly: What is the refund policy?",
                    "vars_json": {"question": "What is the refund policy?"},
                    "response_text": "You can request a refund within 30 days.",
                    "assertions": [
                        {
                            "assertion_type": "contains",
                            "raw_value": "refund",
                            "passed": False,
                        }
                    ],
                }
            ).encode("utf-8"),
            "application/json",
        )
    )
    monkeypatch.setattr("botcheck_api.grai.grai.download_artifact_bytes", download_mock)

    artifact_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results/geres_route_fail/artifact",
        headers=user_auth_headers,
    )

    assert artifact_resp.status_code == 200
    assert artifact_resp.json() == {
        "prompt_id": "prompt_artifact",
        "case_id": "case_artifact",
        "prompt_text": "Answer clearly: What is the refund policy?",
        "vars_json": {"question": "What is the refund policy?"},
        "response_text": "You can request a refund within 30 days.",
        "assertions": [
            {
                "assertion_type": "contains",
                "raw_value": "refund",
                "passed": False,
            }
        ],
    }
    assert download_mock.await_count == 1
    assert download_mock.await_args.kwargs["key"] == "raw/fail.json"


async def test_create_grai_run_rolls_back_if_enqueue_fails(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-enqueue-fail",
    )
    app.state.arq_pool.enqueue_job = AsyncMock(side_effect=RuntimeError("boom"))

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )

    assert resp.status_code == 503
    assert resp.json()["error_code"] == "job_queue_unavailable"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        rows = (await session.execute(select(GraiEvalRunRow))).scalars().all()
        assert rows == []


async def test_grai_run_cross_tenant_read_and_cancel_return_404(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-cross-tenant",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    other_headers = _other_tenant_headers()

    get_resp = await client.get(f"/grai/runs/{eval_run_id}", headers=other_headers)
    assert get_resp.status_code in (403, 404)

    cancel_resp = await client.post(f"/grai/runs/{eval_run_id}/cancel", headers=other_headers)
    assert cancel_resp.status_code in (403, 404)


async def test_list_grai_suite_run_history_returns_newest_first_multi_destination_summaries(
    client,
    user_auth_headers,
):
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="history",
    )
    first_run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
        ),
        headers=user_auth_headers,
    )
    assert first_run_resp.status_code == 202
    first_run_id = first_run_resp.json()["eval_run_id"]

    second_run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )
    assert second_run_resp.status_code == 202
    second_run_id = second_run_resp.json()["eval_run_id"]

    now = datetime.now(UTC)
    await _set_grai_run_summary(
        first_run_id,
        status="complete",
        terminal_outcome="passed",
        completed_count=1,
        failed_count=0,
        dispatched_count=1,
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=4),
    )
    await _set_grai_run_summary(
        second_run_id,
        status="failed",
        terminal_outcome="assertion_failed",
        completed_count=1,
        failed_count=1,
        dispatched_count=2,
        created_at=now,
        updated_at=now + timedelta(seconds=5),
    )

    history_resp = await client.get(
        f"/grai/suites/{suite_id}/runs",
        headers=user_auth_headers,
    )

    assert history_resp.status_code == 200
    body = history_resp.json()
    assert [item["eval_run_id"] for item in body] == [second_run_id, first_run_id]

    newest = body[0]
    assert newest["suite_id"] == suite_id
    assert newest["transport_profile_id"] == transport_a
    assert newest["transport_profile_ids"] == [transport_a, transport_b]
    assert newest["destination_count"] == 2
    assert newest["destinations"] == [
        {
            "destination_index": 0,
            "transport_profile_id": transport_a,
            "label": "Grai HTTP Transport history-a",
        },
        {
            "destination_index": 1,
            "transport_profile_id": transport_b,
            "label": "Grai HTTP Transport history-b",
        },
    ]
    assert newest["status"] == "failed"
    assert newest["terminal_outcome"] == "assertion_failed"
    assert newest["dispatched_count"] == 2
    assert newest["completed_count"] == 1
    assert newest["failed_count"] == 1
    assert newest["trigger_source"] == "manual"
    assert "triggered_by" in newest
    assert newest["schedule_id"] is None
    assert body[1]["terminal_outcome"] == "passed"

    limited_resp = await client.get(
        f"/grai/suites/{suite_id}/runs?limit=1",
        headers=user_auth_headers,
    )
    assert limited_resp.status_code == 200
    assert [item["eval_run_id"] for item in limited_resp.json()] == [second_run_id]


async def test_list_grai_suite_run_history_returns_empty_list_for_suite_without_runs(
    client,
    user_auth_headers,
):
    suite_id, _transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="history-empty",
    )

    history_resp = await client.get(
        f"/grai/suites/{suite_id}/runs",
        headers=user_auth_headers,
    )

    assert history_resp.status_code == 200
    assert history_resp.json() == []


async def test_list_grai_suite_run_history_cross_tenant_returns_404(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="history-cross-tenant",
    )
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202

    other_headers = _other_tenant_headers()
    history_resp = await client.get(
        f"/grai/suites/{suite_id}/runs",
        headers=other_headers,
    )

    # Cross-tenant callers are rejected at the tenant context check (403) or suite lookup (404).
    assert history_resp.status_code in (403, 404)
    if history_resp.status_code == 404:
        assert history_resp.json()["error_code"] == "grai_eval_suite_not_found"


async def test_grai_run_result_artifact_cross_tenant_returns_404(client, user_auth_headers):
    suite_id, transport_profile_id = await _create_suite_and_transport(
        client,
        user_auth_headers,
        suffix="run-artifact-cross-tenant",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_results_for_run(eval_run_id)
    other_headers = _other_tenant_headers()

    artifact_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results/geres_route_fail/artifact",
        headers=other_headers,
    )
    assert artifact_resp.status_code in (403, 404)


async def _seed_multi_dest_results_for_run(eval_run_id: str, transport_a: str, transport_b: str) -> None:
    """Seed result rows for a two-destination run (destination_index 0 and 1)."""
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        run_row = await session.get(GraiEvalRunRow, eval_run_id)
        assert run_row is not None
        stmt = select(GraiEvalPromptRow).where(GraiEvalPromptRow.suite_id == run_row.suite_id)
        prompts = (await session.execute(stmt)).scalars().all()
        stmt = select(GraiEvalCaseRow).where(GraiEvalCaseRow.suite_id == run_row.suite_id)
        cases = (await session.execute(stmt)).scalars().all()
        assert len(prompts) == 1
        assert len(cases) == 1
        prompt = prompts[0]
        case = cases[0]
        now = datetime.now(UTC)
        # destination 0 passes, destination 1 fails
        session.add_all(
            [
                GraiEvalResultRow(
                    eval_result_id="geres_multi_dest_0_pass",
                    tenant_id=run_row.tenant_id,
                    suite_id=run_row.suite_id,
                    eval_run_id=eval_run_id,
                    prompt_id=prompt.prompt_id,
                    case_id=case.case_id,
                    destination_index=0,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=True,
                    score=1.0,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=None,
                    latency_ms=200,
                    tags_json=["smoke"],
                    raw_s3_key="raw/dest0.json",
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_multi_dest_1_fail",
                    tenant_id=run_row.tenant_id,
                    suite_id=run_row.suite_id,
                    eval_run_id=eval_run_id,
                    prompt_id=prompt.prompt_id,
                    case_id=case.case_id,
                    destination_index=1,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=False,
                    score=0.0,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason="response did not contain 'refund'",
                    latency_ms=400,
                    tags_json=["smoke"],
                    raw_s3_key="raw/dest1.json",
                    created_at=now - timedelta(milliseconds=1),
                    updated_at=now - timedelta(milliseconds=1),
                ),
            ]
        )
        run_row.status = "complete"
        run_row.dispatched_count = 2
        run_row.completed_count = 1
        run_row.failed_count = 1
        await session.commit()


async def test_multi_destination_results_carry_destination_index(client, user_auth_headers):
    """Results list returns destination_index on each row; filtering by destination_index works."""
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="multi-dest-results",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_multi_dest_results_for_run(eval_run_id, transport_a, transport_b)

    # All results — expect two rows with distinct destination_index values
    all_resp = await client.get(f"/grai/runs/{eval_run_id}/results", headers=user_auth_headers)
    assert all_resp.status_code == 200
    items = all_resp.json()["items"]
    assert len(items) == 2
    dest_indices = {item["destination_index"] for item in items}
    assert dest_indices == {0, 1}

    # Filter by status=passed — should return only destination 0's result
    passed_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results?status=passed",
        headers=user_auth_headers,
    )
    assert passed_resp.status_code == 200
    passed_items = passed_resp.json()["items"]
    assert len(passed_items) == 1
    assert passed_items[0]["destination_index"] == 0

    # Filter by status=failed — should return only destination 1's result
    failed_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results?status=failed",
        headers=user_auth_headers,
    )
    assert failed_resp.status_code == 200
    failed_items = failed_resp.json()["items"]
    assert len(failed_items) == 1
    assert failed_items[0]["destination_index"] == 1


async def test_multi_destination_report_aggregates_per_destination(client, user_auth_headers):
    """Report correctly counts passed/failed split across two destinations."""
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="multi-dest-report",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_multi_dest_results_for_run(eval_run_id, transport_a, transport_b)

    report_resp = await client.get(f"/grai/runs/{eval_run_id}/report", headers=user_auth_headers)
    assert report_resp.status_code == 200
    report = report_resp.json()

    # 2 total results: 1 pass (dest 0) + 1 fail (dest 1)
    assert report["total_results"] == 2
    assert report["passed_results"] == 1
    assert report["failed_results"] == 1

    # exemplar failures should include the dest-1 failure
    exemplar_ids = [e["eval_result_id"] for e in report.get("exemplar_failures", [])]
    assert "geres_multi_dest_1_fail" in exemplar_ids


async def test_multi_destination_report_and_results_accept_destination_index_filter(
    client,
    user_auth_headers,
):
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="multi-dest-filter",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_multi_dest_results_for_run(eval_run_id, transport_a, transport_b)

    report_resp = await client.get(
        f"/grai/runs/{eval_run_id}/report?destination_index=1",
        headers=user_auth_headers,
    )
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["filters"]["destination_index"] == 1
    assert report["total_results"] == 1
    assert report["failed_results"] == 1

    results_resp = await client.get(
        f"/grai/runs/{eval_run_id}/results?destination_index=0",
        headers=user_auth_headers,
    )
    assert results_resp.status_code == 200
    items = results_resp.json()["items"]
    assert results_resp.json()["filters"]["destination_index"] == 0
    assert [item["destination_index"] for item in items] == [0]


async def test_get_grai_run_matrix_returns_prompt_case_cells_by_destination(client, user_auth_headers):
    suite_id, transport_a, transport_b = await _create_suite_and_two_transports(
        client,
        user_auth_headers,
        suffix="multi-dest-matrix",
    )
    create_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_a,
            transport_profile_ids=[transport_a, transport_b],
        ),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202
    eval_run_id = create_resp.json()["eval_run_id"]
    await _seed_multi_dest_results_for_run(eval_run_id, transport_a, transport_b)

    matrix_resp = await client.get(f"/grai/runs/{eval_run_id}/matrix", headers=user_auth_headers)

    assert matrix_resp.status_code == 200
    body = matrix_resp.json()
    assert body["eval_run_id"] == eval_run_id
    assert [item["transport_profile_id"] for item in body["destinations"]] == [transport_a, transport_b]
    assert body["destinations"][0]["passed"] == 1
    assert body["destinations"][1]["failed"] == 1
    prompt_group = body["prompt_groups"][0]
    assert prompt_group["prompt_label"] == "helpful"
    row = prompt_group["rows"][0]
    assert len(row["cells"]) == 2
    assert [cell["status"] for cell in row["cells"]] == ["passed", "failed"]
