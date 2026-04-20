from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Integer, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import GRAI_EVAL_SUITE_NAME_CONFLICT
from .grai.service_models import GraiEvalResultWritePayload
from .models import (
    GraiEvalCaseRow,
    GraiEvalPromptRow,
    GraiEvalResultRow,
    GraiEvalRunDestinationRow,
    GraiEvalRunRow,
    GraiEvalRunStatus,
    GraiEvalRunTerminalOutcome,
    GraiEvalSuiteRow,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


async def list_grai_eval_suite_rows_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> list[GraiEvalSuiteRow]:
    result = await db.execute(
        select(GraiEvalSuiteRow)
        .where(GraiEvalSuiteRow.tenant_id == tenant_id)
        .order_by(GraiEvalSuiteRow.updated_at.desc(), GraiEvalSuiteRow.created_at.desc())
    )
    return list(result.scalars())


async def get_grai_eval_suite_row_for_tenant(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
) -> GraiEvalSuiteRow | None:
    result = await db.execute(
        select(GraiEvalSuiteRow).where(
            GraiEvalSuiteRow.suite_id == suite_id,
            GraiEvalSuiteRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def get_grai_eval_suite_row_by_name_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
) -> GraiEvalSuiteRow | None:
    result = await db.execute(
        select(GraiEvalSuiteRow).where(
            GraiEvalSuiteRow.tenant_id == tenant_id,
            GraiEvalSuiteRow.name == name,
        )
    )
    return result.scalar_one_or_none()


async def list_grai_eval_prompt_rows_for_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
) -> list[GraiEvalPromptRow]:
    result = await db.execute(
        select(GraiEvalPromptRow)
        .where(
            GraiEvalPromptRow.suite_id == suite_id,
            GraiEvalPromptRow.tenant_id == tenant_id,
        )
        .order_by(GraiEvalPromptRow.order_index.asc())
    )
    return list(result.scalars())


async def list_grai_eval_case_rows_for_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
) -> list[GraiEvalCaseRow]:
    result = await db.execute(
        select(GraiEvalCaseRow)
        .where(
            GraiEvalCaseRow.suite_id == suite_id,
            GraiEvalCaseRow.tenant_id == tenant_id,
        )
        .order_by(GraiEvalCaseRow.order_index.asc())
    )
    return list(result.scalars())


async def get_grai_eval_suite_counts(
    db: AsyncSession,
    *,
    tenant_id: str,
    suite_ids: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    if not suite_ids:
        return {}, {}

    prompt_result = await db.execute(
        select(
            GraiEvalPromptRow.suite_id,
            func.count(GraiEvalPromptRow.prompt_id),
        )
        .where(
            GraiEvalPromptRow.tenant_id == tenant_id,
            GraiEvalPromptRow.suite_id.in_(suite_ids),
        )
        .group_by(GraiEvalPromptRow.suite_id)
    )
    case_result = await db.execute(
        select(
            GraiEvalCaseRow.suite_id,
            func.count(GraiEvalCaseRow.case_id),
        )
        .where(
            GraiEvalCaseRow.tenant_id == tenant_id,
            GraiEvalCaseRow.suite_id.in_(suite_ids),
        )
        .group_by(GraiEvalCaseRow.suite_id)
    )
    prompt_counts = {suite_id: int(count) for suite_id, count in prompt_result.all()}
    case_counts = {suite_id: int(count) for suite_id, count in case_result.all()}
    return prompt_counts, case_counts


async def assert_grai_eval_suite_name_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    suite_id: str | None = None,
) -> None:
    existing = await get_grai_eval_suite_row_by_name_for_tenant(
        db,
        tenant_id=tenant_id,
        name=name,
    )
    if existing is not None and existing.suite_id != suite_id:
        raise ValueError(GRAI_EVAL_SUITE_NAME_CONFLICT)


async def replace_grai_eval_suite_children(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
    prompts: list[dict[str, object]],
    cases: list[dict[str, object]],
) -> tuple[list[str], list[str]]:
    await db.execute(
        delete(GraiEvalPromptRow).where(
            GraiEvalPromptRow.suite_id == suite_id,
            GraiEvalPromptRow.tenant_id == tenant_id,
        )
    )
    await db.execute(
        delete(GraiEvalCaseRow).where(
            GraiEvalCaseRow.suite_id == suite_id,
            GraiEvalCaseRow.tenant_id == tenant_id,
        )
    )

    prompt_ids: list[str] = []
    for index, prompt in enumerate(prompts):
        prompt_id = f"geprompt_{uuid4().hex[:12]}"
        prompt_ids.append(prompt_id)
        t = now_utc()
        db.add(
            GraiEvalPromptRow(
                prompt_id=prompt_id,
                suite_id=suite_id,
                tenant_id=tenant_id,
                order_index=index,
                label=str(prompt["label"]),
                prompt_text=str(prompt["prompt_text"]),
                metadata_json=dict(prompt.get("metadata_json") or {}),
                created_at=t,
                updated_at=t,
            )
        )

    case_ids: list[str] = []
    for index, case in enumerate(cases):
        case_id = f"gecase_{uuid4().hex[:12]}"
        case_ids.append(case_id)
        t = now_utc()
        db.add(
            GraiEvalCaseRow(
                case_id=case_id,
                suite_id=suite_id,
                tenant_id=tenant_id,
                order_index=index,
                description=str(case["description"]),
                vars_json=dict(case.get("vars_json") or {}),
                assert_json=list(case.get("assert_json") or []),
                tags_json=list(case.get("tags_json") or []),
                metadata_json=dict(case.get("metadata_json") or {}),
                import_threshold=case.get("import_threshold"),
                created_at=t,
                updated_at=t,
            )
        )
    return prompt_ids, case_ids


async def add_grai_eval_suite_row(db: AsyncSession, row: GraiEvalSuiteRow) -> None:
    db.add(row)


async def delete_grai_eval_suite_row_for_tenant(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
) -> bool:
    row = await get_grai_eval_suite_row_for_tenant(db, suite_id=suite_id, tenant_id=tenant_id)
    if row is None:
        return False
    await db.execute(
        delete(GraiEvalPromptRow).where(
            GraiEvalPromptRow.suite_id == suite_id,
            GraiEvalPromptRow.tenant_id == tenant_id,
        )
    )
    await db.execute(
        delete(GraiEvalCaseRow).where(
            GraiEvalCaseRow.suite_id == suite_id,
            GraiEvalCaseRow.tenant_id == tenant_id,
        )
    )
    await db.delete(row)
    await db.flush()
    return True


async def get_grai_eval_run_row_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> GraiEvalRunRow | None:
    result = await db.execute(
        select(GraiEvalRunRow).where(
            GraiEvalRunRow.eval_run_id == eval_run_id,
            GraiEvalRunRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_grai_eval_run_rows_for_suite(
    db: AsyncSession,
    *,
    suite_id: str,
    tenant_id: str,
    limit: int,
) -> list[GraiEvalRunRow]:
    result = await db.execute(
        select(GraiEvalRunRow)
        .where(
            GraiEvalRunRow.suite_id == suite_id,
            GraiEvalRunRow.tenant_id == tenant_id,
        )
        .order_by(
            GraiEvalRunRow.created_at.desc(),
            GraiEvalRunRow.updated_at.desc(),
            GraiEvalRunRow.eval_run_id.desc(),
        )
        .limit(limit)
    )
    return list(result.scalars())


async def list_grai_eval_run_destination_rows_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> list[GraiEvalRunDestinationRow]:
    result = await db.execute(
        select(GraiEvalRunDestinationRow)
        .where(
            GraiEvalRunDestinationRow.eval_run_id == eval_run_id,
            GraiEvalRunDestinationRow.tenant_id == tenant_id,
        )
        .order_by(GraiEvalRunDestinationRow.destination_index.asc())
    )
    return list(result.scalars())


async def list_grai_eval_run_destination_rows_for_runs(
    db: AsyncSession,
    *,
    eval_run_ids: list[str],
    tenant_id: str,
) -> list[GraiEvalRunDestinationRow]:
    if not eval_run_ids:
        return []
    result = await db.execute(
        select(GraiEvalRunDestinationRow)
        .where(
            GraiEvalRunDestinationRow.eval_run_id.in_(eval_run_ids),
            GraiEvalRunDestinationRow.tenant_id == tenant_id,
        )
        .order_by(
            GraiEvalRunDestinationRow.eval_run_id.asc(),
            GraiEvalRunDestinationRow.destination_index.asc(),
        )
    )
    return list(result.scalars())


async def get_grai_eval_result_row_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    eval_result_id: str,
    tenant_id: str,
) -> GraiEvalResultRow | None:
    result = await db.execute(
        select(GraiEvalResultRow).where(
            GraiEvalResultRow.eval_run_id == eval_run_id,
            GraiEvalResultRow.eval_result_id == eval_result_id,
            GraiEvalResultRow.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def cancel_grai_eval_run_row_for_tenant(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> GraiEvalRunRow | None:
    row = await get_grai_eval_run_row_for_tenant(db, eval_run_id=eval_run_id, tenant_id=tenant_id)
    if row is None:
        return None
    if row.status == GraiEvalRunStatus.CANCELLED.value:
        return row
    if row.status in {
        GraiEvalRunStatus.COMPLETE.value,
        GraiEvalRunStatus.FAILED.value,
    }:
        return row
    row.status = GraiEvalRunStatus.CANCELLED.value
    row.terminal_outcome = GraiEvalRunTerminalOutcome.CANCELLED.value
    row.updated_at = now_utc()
    await db.flush()
    return row


async def list_grai_eval_pair_progress_rows(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
) -> list[tuple[str, str, int, int | None]]:
    result = await db.execute(
        select(
            GraiEvalResultRow.prompt_id,
            GraiEvalResultRow.case_id,
            GraiEvalResultRow.destination_index,
            func.min(cast(GraiEvalResultRow.passed, Integer)),
        )
        .where(
            GraiEvalResultRow.eval_run_id == eval_run_id,
            GraiEvalResultRow.tenant_id == tenant_id,
        )
        .group_by(
            GraiEvalResultRow.prompt_id,
            GraiEvalResultRow.case_id,
            GraiEvalResultRow.destination_index,
        )
    )
    return [
        (str(prompt_id), str(case_id), int(destination_index or 0), min_passed)
        for prompt_id, case_id, destination_index, min_passed in result.all()
    ]


async def replace_grai_eval_pair_result_rows(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    suite_id: str,
    prompt_id: str,
    case_id: str,
    destination_index: int,
    rows: list[GraiEvalResultWritePayload],
) -> None:
    await db.execute(
        delete(GraiEvalResultRow).where(
            GraiEvalResultRow.eval_run_id == eval_run_id,
            GraiEvalResultRow.tenant_id == tenant_id,
            GraiEvalResultRow.prompt_id == prompt_id,
            GraiEvalResultRow.case_id == case_id,
            GraiEvalResultRow.destination_index == destination_index,
        )
    )
    for index, payload in enumerate(rows):
        t = now_utc()
        db.add(
            GraiEvalResultRow(
                eval_result_id=f"geres_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                suite_id=suite_id,
                eval_run_id=eval_run_id,
                prompt_id=prompt_id,
                case_id=case_id,
                destination_index=destination_index,
                assertion_index=index,
                assertion_type=payload.assertion_type,
                passed=payload.passed,
                score=payload.score,
                threshold=payload.threshold,
                weight=payload.weight,
                raw_value=payload.raw_value,
                failure_reason=payload.failure_reason,
                latency_ms=payload.latency_ms,
                tags_json=list(payload.tags_json),
                raw_s3_key=payload.raw_s3_key,
                created_at=t,
                updated_at=t,
            )
        )
    await db.flush()


async def set_grai_eval_run_progress_row(
    db: AsyncSession,
    *,
    eval_run_id: str,
    tenant_id: str,
    status: str,
    terminal_outcome: GraiEvalRunTerminalOutcome | None,
    dispatched_count: int,
    completed_count: int,
    failed_count: int,
) -> GraiEvalRunRow | None:
    row = await get_grai_eval_run_row_for_tenant(db, eval_run_id=eval_run_id, tenant_id=tenant_id)
    if row is None:
        return None
    row.status = status
    row.terminal_outcome = terminal_outcome.value if terminal_outcome is not None else None
    row.dispatched_count = dispatched_count
    row.completed_count = completed_count
    row.failed_count = failed_count
    row.updated_at = now_utc()
    await db.flush()
    return row


__all__ = [
    "add_grai_eval_suite_row",
    "assert_grai_eval_suite_name_available",
    "cancel_grai_eval_run_row_for_tenant",
    "delete_grai_eval_suite_row_for_tenant",
    "get_grai_eval_result_row_for_tenant",
    "get_grai_eval_run_row_for_tenant",
    "get_grai_eval_suite_counts",
    "get_grai_eval_suite_row_by_name_for_tenant",
    "get_grai_eval_suite_row_for_tenant",
    "list_grai_eval_case_rows_for_suite",
    "list_grai_eval_pair_progress_rows",
    "list_grai_eval_prompt_rows_for_suite",
    "list_grai_eval_run_destination_rows_for_runs",
    "list_grai_eval_run_destination_rows_for_tenant",
    "list_grai_eval_run_rows_for_suite",
    "list_grai_eval_suite_rows_for_tenant",
    "now_utc",
    "replace_grai_eval_pair_result_rows",
    "replace_grai_eval_suite_children",
    "set_grai_eval_run_progress_row",
]
