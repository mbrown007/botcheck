from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from botcheck_api.grai.service_models import (
    GraiEvalResultWritePayload,
    GraiEvalRunDestinationSnapshot,
)
from botcheck_api.grai.store_service import (
    cancel_grai_eval_run,
    create_grai_eval_run_snapshot,
    replace_grai_eval_pair_results,
    set_grai_eval_run_progress,
)
from botcheck_api.models import (
    Base,
    GraiEvalCaseRow,
    GraiEvalPromptRow,
    GraiEvalResultRow,
    GraiEvalRunStatus,
    GraiEvalRunTerminalOutcome,
)


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


@pytest.mark.asyncio
async def test_create_grai_eval_run_snapshot_persists_counts_and_snapshots(db_factory) -> None:
    async with db_factory() as session:
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_store_test",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_http_store_test",
                    label="Store HTTP Bot",
                    protocol="http",
                    endpoint_at_start="https://bot.internal/chat",
                    headers_at_start={"Authorization": "Bearer store-token"},
                    direct_http_config_at_start={"request_text_field": "message"},
                ),
                GraiEvalRunDestinationSnapshot(
                    destination_index=1,
                    transport_profile_id="dest_http_store_test_b",
                    label="Store HTTP Bot B",
                    protocol="http",
                    endpoint_at_start="https://bot-b.internal/chat",
                    headers_at_start={"Authorization": "Bearer store-token-b"},
                    direct_http_config_at_start={"request_text_field": "message"},
                ),
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_store_test",
            prompt_count=2,
            case_count=3,
        )
        await session.commit()

        assert snapshot.status == GraiEvalRunStatus.PENDING.value
        assert snapshot.terminal_outcome is None
        assert snapshot.prompt_count == 2
        assert snapshot.case_count == 3
        assert snapshot.total_pairs == 12
        assert snapshot.headers_at_start["Authorization"] == "Bearer store-token"
        assert snapshot.transport_profile_ids == [
            "dest_http_store_test",
            "dest_http_store_test_b",
        ]
        assert len(snapshot.destinations) == 2


@pytest.mark.asyncio
async def test_cancel_grai_eval_run_transitions_pending_and_is_idempotent(db_factory) -> None:
    async with db_factory() as session:
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_cancel_test",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_http_cancel_test",
                    label="Cancel HTTP Bot",
                    protocol="http",
                    endpoint_at_start="https://bot.internal/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                )
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_cancel_test",
            prompt_count=1,
            case_count=1,
        )
        await session.commit()

    async with db_factory() as session:
        result = await cancel_grai_eval_run(
            session,
            eval_run_id=snapshot.eval_run_id,
            tenant_id="default",
        )
        await session.commit()

        assert result.found is True
        assert result.applied is True
        assert result.status == GraiEvalRunStatus.CANCELLED.value
        assert result.reason == "cancelled"

    async with db_factory() as session:
        second = await cancel_grai_eval_run(
            session,
            eval_run_id=snapshot.eval_run_id,
            tenant_id="default",
        )

        assert second.found is True
        assert second.applied is False
        assert second.reason == "already_cancelled"


@pytest.mark.asyncio
async def test_set_grai_eval_run_progress_persists_terminal_outcome(db_factory) -> None:
    async with db_factory() as session:
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_progress_test",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_progress_test",
                    label="Progress HTTP Bot",
                    protocol="http",
                    endpoint_at_start="https://bot.internal/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                )
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_progress_test",
            prompt_count=1,
            case_count=1,
        )
        await session.commit()

    async with db_factory() as session:
        row = await set_grai_eval_run_progress(
            session,
            eval_run_id=snapshot.eval_run_id,
            tenant_id="default",
            status=GraiEvalRunStatus.COMPLETE.value,
            terminal_outcome=GraiEvalRunTerminalOutcome.PASSED,
            dispatched_count=1,
            completed_count=1,
            failed_count=0,
        )
        await session.commit()

        assert row is not None
        assert row.status == GraiEvalRunStatus.COMPLETE.value
        assert row.terminal_outcome == GraiEvalRunTerminalOutcome.PASSED.value
        assert row.completed_count == 1
        assert row.failed_count == 0


@pytest.mark.asyncio
async def test_replace_grai_eval_pair_results_accepts_typed_payloads(db_factory) -> None:
    async with db_factory() as session:
        snapshot = await create_grai_eval_run_snapshot(
            session,
            tenant_id="default",
            suite_id="gesuite_result_write_test",
            destinations=[
                GraiEvalRunDestinationSnapshot(
                    destination_index=0,
                    transport_profile_id="dest_result_write_test",
                    label="Result Write HTTP Bot",
                    protocol="http",
                    endpoint_at_start="https://bot.internal/chat",
                    headers_at_start={},
                    direct_http_config_at_start=None,
                )
            ],
            trigger_source="manual",
            schedule_id=None,
            triggered_by="user_result_write_test",
            prompt_count=1,
            case_count=1,
        )
        session.add(
            GraiEvalPromptRow(
                prompt_id="geprompt_result_write",
                suite_id="gesuite_result_write_test",
                tenant_id="default",
                order_index=0,
                label="helpful",
                prompt_text="Prompt",
                metadata_json={},
                created_at=snapshot.created_at,
                updated_at=snapshot.updated_at,
            )
        )
        session.add(
            GraiEvalCaseRow(
                case_id="gecase_result_write",
                suite_id="gesuite_result_write_test",
                tenant_id="default",
                order_index=0,
                description="Case",
                vars_json={},
                assert_json=[],
                tags_json=["billing"],
                metadata_json={},
                import_threshold=None,
                created_at=snapshot.created_at,
                updated_at=snapshot.updated_at,
            )
        )
        await replace_grai_eval_pair_results(
            session,
            eval_run_id=snapshot.eval_run_id,
            tenant_id="default",
            suite_id="gesuite_result_write_test",
            prompt_id="geprompt_result_write",
            case_id="gecase_result_write",
            destination_index=0,
            rows=[
                GraiEvalResultWritePayload(
                    assertion_type="contains",
                    passed=True,
                    score=1.0,
                    threshold=0.8,
                    weight=1.0,
                    raw_value="refund",
                    failure_reason=None,
                    latency_ms=120,
                    tags_json=["billing"],
                    raw_s3_key="raw/result-write.json",
                )
            ],
        )
        await session.commit()

        stored = (
            await session.execute(select(GraiEvalResultRow).where(GraiEvalResultRow.eval_run_id == snapshot.eval_run_id))
        ).scalar_one()
        assert stored.assertion_type == "contains"
        assert stored.passed is True
        assert stored.score == 1.0
        assert stored.tags_json == ["billing"]
