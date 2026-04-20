from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from botcheck_api.grai.store_service import (
    build_grai_eval_matrix,
    build_grai_eval_report,
    create_grai_eval_run_snapshot,
    list_grai_eval_results_page,
)
from botcheck_api.grai.service_models import (
    GRAI_EVAL_DISPATCH_ERROR_PREFIX,
    GraiEvalRunDestinationSnapshot,
)
from botcheck_api.models import Base, GraiEvalCaseRow, GraiEvalPromptRow, GraiEvalResultRow


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_run_with_results(db_factory):
    now = datetime.now(UTC)
    async with db_factory() as session:
        session.add_all(
            [
                GraiEvalPromptRow(
                    prompt_id="geprompt_a",
                    suite_id="gesuite_report",
                    tenant_id="default",
                    order_index=0,
                    label="helpful",
                    prompt_text="Prompt A",
                    metadata_json={},
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalPromptRow(
                    prompt_id="geprompt_b",
                    suite_id="gesuite_report",
                    tenant_id="default",
                    order_index=1,
                    label="strict",
                    prompt_text="Prompt B",
                    metadata_json={},
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalCaseRow(
                    case_id="gecase_a",
                    suite_id="gesuite_report",
                    tenant_id="default",
                    order_index=0,
                    description="Refund policy",
                    vars_json={},
                    assert_json=[{"assertion_type": "contains"}],
                    tags_json=["billing", "smoke-test"],
                    metadata_json={},
                    import_threshold=None,
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalCaseRow(
                    case_id="gecase_b",
                    suite_id="gesuite_report",
                    tenant_id="default",
                    order_index=1,
                    description="Security flow",
                    vars_json={},
                    assert_json=[{"assertion_type": "factuality"}],
                    tags_json=["security"],
                    metadata_json={},
                    import_threshold=None,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_report",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_http_report",
                    label="Report HTTP Bot",
                    protocol="http",
                    endpoint_at_start="https://bot.internal/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                )
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_report",
            prompt_count=2,
            case_count=2,
        )
        session.add_all(
            [
                GraiEvalResultRow(
                    eval_result_id="geres_003",
                    tenant_id="default",
                    suite_id="gesuite_report",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_a",
                    case_id="gecase_a",
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
                    raw_s3_key="raw/003.json",
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_002",
                    tenant_id="default",
                    suite_id="gesuite_report",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_b",
                    case_id="gecase_a",
                    assertion_index=0,
                    assertion_type="contains",
                    passed=True,
                    score=1.0,
                    threshold=0.8,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=None,
                    latency_ms=95,
                    tags_json=["billing", "smoke-test"],
                    raw_s3_key="raw/002.json",
                    created_at=now - timedelta(seconds=1),
                    updated_at=now - timedelta(seconds=1),
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_001",
                    tenant_id="default",
                    suite_id="gesuite_report",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_b",
                    case_id="gecase_b",
                    assertion_index=0,
                    assertion_type="factuality",
                    passed=False,
                    score=0.2,
                    threshold=0.8,
                    weight=1.0,
                    raw_value="answer factual",
                    failure_reason="hallucinated policy",
                    latency_ms=140,
                    tags_json=["security"],
                    raw_s3_key="raw/001.json",
                    created_at=now - timedelta(seconds=2),
                    updated_at=now - timedelta(seconds=2),
                ),
            ]
        )
        await session.commit()
        return snapshot.eval_run_id


@pytest.mark.asyncio
async def test_build_grai_eval_report_aggregates_breakdowns_and_filters(db_factory) -> None:
    eval_run_id = await _seed_run_with_results(db_factory)

    async with db_factory() as session:
        report = await build_grai_eval_report(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
        )

    assert report["total_results"] == 3
    assert report["passed_results"] == 1
    assert report["failed_results"] == 2
    assert report["assertion_type_breakdown"] == [
        {
            "assertion_type": "contains",
            "total_results": 2,
            "passed_results": 1,
            "failed_results": 1,
        },
        {
            "assertion_type": "factuality",
            "total_results": 1,
            "passed_results": 0,
            "failed_results": 1,
        },
    ]
    assert report["failing_prompt_variants"][0] == {
        "prompt_id": "geprompt_a",
        "prompt_label": "helpful",
        "failure_count": 1,
        "failed_pairs": 1,
    }
    assert report["tag_failure_clusters"] == [
        {"tag": "billing", "failure_count": 1, "failed_pairs": 1},
        {"tag": "security", "failure_count": 1, "failed_pairs": 1},
        {"tag": "smoke-test", "failure_count": 1, "failed_pairs": 1},
    ]
    assert [item["eval_result_id"] for item in report["exemplar_failures"]] == [
        "geres_003",
        "geres_001",
    ]

    async with db_factory() as session:
        filtered = await build_grai_eval_report(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            tag="billing",
            status="failed",
        )

    assert filtered["total_results"] == 1
    assert filtered["failed_results"] == 1
    assert filtered["passed_results"] == 0
    assert filtered["assertion_type_breakdown"] == [
        {
            "assertion_type": "contains",
            "total_results": 1,
            "passed_results": 0,
            "failed_results": 1,
        }
    ]


@pytest.mark.asyncio
async def test_list_grai_eval_results_page_uses_desc_cursor_pagination(db_factory) -> None:
    eval_run_id = await _seed_run_with_results(db_factory)

    async with db_factory() as session:
        page_one, next_created_at, next_eval_result_id = await list_grai_eval_results_page(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            limit=2,
        )

        assert [item["eval_result_id"] for item in page_one] == ["geres_003", "geres_002"]
        assert next_created_at is not None
        assert next_eval_result_id == "geres_002"

        page_two, final_created_at, final_eval_result_id = await list_grai_eval_results_page(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            limit=2,
            cursor_created_at=next_created_at,
            cursor_eval_result_id=next_eval_result_id,
        )

    assert [item["eval_result_id"] for item in page_two] == ["geres_001"]
    assert final_created_at is None
    assert final_eval_result_id is None


@pytest.mark.asyncio
async def test_results_and_report_support_destination_index_filter(db_factory) -> None:
    now = datetime.now(UTC)
    async with db_factory() as session:
        session.add(
            GraiEvalPromptRow(
                prompt_id="geprompt_dest",
                suite_id="gesuite_dest",
                tenant_id="default",
                order_index=0,
                label="helpful",
                prompt_text="Prompt dest",
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            GraiEvalCaseRow(
                case_id="gecase_dest",
                suite_id="gesuite_dest",
                tenant_id="default",
                order_index=0,
                description="Destination filtered",
                vars_json={},
                assert_json=[{"assertion_type": "contains"}],
                tags_json=["smoke"],
                metadata_json={},
                import_threshold=None,
                created_at=now,
                updated_at=now,
            )
        )
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_dest",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_http_a",
                    label="Bot A",
                    protocol="http",
                    endpoint_at_start="https://a.example/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                ),
                GraiEvalRunDestinationSnapshot(
                    destination_index=1,
                    transport_profile_id="dest_http_b",
                    label="Bot B",
                    protocol="http",
                    endpoint_at_start="https://b.example/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                ),
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_dest",
            prompt_count=1,
            case_count=1,
        )
        session.add_all(
            [
                GraiEvalResultRow(
                    eval_result_id="geres_dest_0",
                    tenant_id="default",
                    suite_id="gesuite_dest",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_dest",
                    case_id="gecase_dest",
                    destination_index=0,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=True,
                    score=1.0,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=None,
                    latency_ms=None,
                    tags_json=["smoke"],
                    raw_s3_key=None,
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_dest_1",
                    tenant_id="default",
                    suite_id="gesuite_dest",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_dest",
                    case_id="gecase_dest",
                    destination_index=1,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=False,
                    score=0.0,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason="missing refund",
                    latency_ms=None,
                    tags_json=["smoke"],
                    raw_s3_key=None,
                    created_at=now - timedelta(seconds=1),
                    updated_at=now - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()
        eval_run_id = snapshot.eval_run_id

    async with db_factory() as session:
        items, _, _ = await list_grai_eval_results_page(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            destination_index=1,
        )
        report = await build_grai_eval_report(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            destination_index=1,
        )

    assert [item["eval_result_id"] for item in items] == ["geres_dest_1"]
    assert report["total_results"] == 1
    assert report["failed_results"] == 1
    assert report["passed_results"] == 0


@pytest.mark.asyncio
async def test_build_grai_eval_matrix_groups_prompt_case_cells_and_error_status(db_factory) -> None:
    now = datetime.now(UTC)
    destinations = [
        GraiEvalRunDestinationSnapshot(
            destination_index=0,
            transport_profile_id="dest_http_a",
            label="Bot A",
            protocol="http",
            endpoint_at_start="https://a.example/chat",
            headers_at_start={},
            direct_http_config_at_start=None,
        ),
        GraiEvalRunDestinationSnapshot(
            destination_index=1,
            transport_profile_id="dest_http_b",
            label="Bot B",
            protocol="http",
            endpoint_at_start="https://b.example/chat",
            headers_at_start={},
            direct_http_config_at_start=None,
        ),
    ]
    async with db_factory() as session:
        session.add(
            GraiEvalPromptRow(
                prompt_id="geprompt_matrix",
                suite_id="gesuite_matrix",
                tenant_id="default",
                order_index=0,
                label="helpful",
                prompt_text="Prompt matrix",
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            GraiEvalCaseRow(
                case_id="gecase_matrix",
                suite_id="gesuite_matrix",
                tenant_id="default",
                order_index=0,
                description="Matrix case",
                vars_json={},
                assert_json=[{"assertion_type": "contains"}],
                tags_json=["billing"],
                metadata_json={},
                import_threshold=None,
                created_at=now,
                updated_at=now,
            )
        )
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_matrix",
            destinations=destinations,
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_matrix",
            prompt_count=1,
            case_count=1,
        )
        session.add_all(
            [
                GraiEvalResultRow(
                    eval_result_id="geres_matrix_0",
                    tenant_id="default",
                    suite_id="gesuite_matrix",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_matrix",
                    case_id="gecase_matrix",
                    destination_index=0,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=True,
                    score=1.0,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=None,
                    latency_ms=None,
                    tags_json=["billing"],
                    raw_s3_key="raw/matrix-0.json",
                    created_at=now,
                    updated_at=now,
                ),
                GraiEvalResultRow(
                    eval_result_id="geres_matrix_1",
                    tenant_id="default",
                    suite_id="gesuite_matrix",
                    eval_run_id=snapshot.eval_run_id,
                    prompt_id="geprompt_matrix",
                    case_id="gecase_matrix",
                    destination_index=1,
                    assertion_index=0,
                    assertion_type="contains",
                    passed=False,
                    score=None,
                    threshold=None,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=f"{GRAI_EVAL_DISPATCH_ERROR_PREFIX}transport boom",
                    latency_ms=None,
                    tags_json=["billing"],
                    raw_s3_key=None,
                    created_at=now - timedelta(seconds=1),
                    updated_at=now - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()
        eval_run_id = snapshot.eval_run_id

    async with db_factory() as session:
        matrix = await build_grai_eval_matrix(
            session,
            eval_run_id=eval_run_id,
            tenant_id="default",
            suite_id="gesuite_matrix",
            destinations=destinations,
        )

    assert [item["destination_index"] for item in matrix["destinations"]] == [0, 1]
    assert matrix["destinations"][0]["passed"] == 1
    assert matrix["destinations"][0]["failed"] == 0
    assert matrix["destinations"][0]["errors"] == 0
    assert matrix["destinations"][1]["passed"] == 0
    assert matrix["destinations"][1]["failed"] == 0
    assert matrix["destinations"][1]["errors"] == 1
    prompt_group = matrix["prompt_groups"][0]
    assert prompt_group["prompt_label"] == "helpful"
    row = prompt_group["rows"][0]
    assert row["case_description"] == "Matrix case"
    assert row["tags_json"] == ["billing"]
    assert [cell["status"] for cell in row["cells"]] == ["passed", "error"]
