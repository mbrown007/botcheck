"""add grai eval runs

Revision ID: 0049_grai_eval_runs
Revises: 0048_grai_eval_suites
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_grai_eval_runs"
down_revision = "0048_grai_eval_suites"
branch_labels = None
depends_on = None


_GRAI_ASSERTION_TYPE_SQL = (
    "'contains', 'contains-all', 'contains-any', 'icontains', 'icontains-all', "
    "'icontains-any', 'equals', 'starts-with', 'regex', 'is-json', 'word-count', "
    "'levenshtein', 'latency', 'is-refusal', 'llm-rubric', 'factuality', "
    "'model-graded-closedqa', 'answer-relevance'"
)
_GRAI_EVAL_RUN_STATUS_SQL = "'pending', 'running', 'complete', 'failed', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "grai_eval_runs",
        sa.Column("eval_run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("suite_id", sa.String(length=64), nullable=False),
        sa.Column("transport_profile_id", sa.String(length=64), nullable=False),
        sa.Column("endpoint_at_start", sa.String(length=512), nullable=False),
        sa.Column("headers_at_start", sa.JSON(), nullable=False),
        sa.Column("direct_http_config_at_start", sa.JSON(), nullable=True),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("schedule_id", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_count", sa.Integer(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("total_pairs", sa.Integer(), nullable=False),
        sa.Column("dispatched_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_GRAI_EVAL_RUN_STATUS_SQL})",
            name="ck_grai_eval_runs_status",
        ),
        sa.PrimaryKeyConstraint("eval_run_id"),
    )
    op.create_index(
        "ix_grai_eval_runs_tenant_created",
        "grai_eval_runs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_runs_tenant_id"),
        "grai_eval_runs",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_runs_suite_id"),
        "grai_eval_runs",
        ["suite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_runs_transport_profile_id"),
        "grai_eval_runs",
        ["transport_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_runs_schedule_id"),
        "grai_eval_runs",
        ["schedule_id"],
        unique=False,
    )

    op.create_table(
        "grai_eval_results",
        sa.Column("eval_result_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("suite_id", sa.String(length=64), nullable=False),
        sa.Column("eval_run_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("assertion_index", sa.Integer(), nullable=False),
        sa.Column("assertion_type", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("raw_s3_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"assertion_type IN ({_GRAI_ASSERTION_TYPE_SQL})",
            name="ck_grai_eval_results_assertion_type",
        ),
        sa.PrimaryKeyConstraint("eval_result_id"),
        sa.UniqueConstraint(
            "eval_run_id",
            "prompt_id",
            "case_id",
            "assertion_index",
            name="uq_grai_eval_results_eval_prompt_case_assertion",
        ),
    )
    op.create_index(
        op.f("ix_grai_eval_results_tenant_id"),
        "grai_eval_results",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_results_suite_id"),
        "grai_eval_results",
        ["suite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_results_eval_run_id"),
        "grai_eval_results",
        ["eval_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_grai_eval_results_run_assertion_passed",
        "grai_eval_results",
        ["eval_run_id", "assertion_type", "passed"],
        unique=False,
    )
    op.create_index(
        "ix_grai_eval_results_run_prompt",
        "grai_eval_results",
        ["eval_run_id", "prompt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_grai_eval_results_run_prompt", table_name="grai_eval_results")
    op.drop_index("ix_grai_eval_results_run_assertion_passed", table_name="grai_eval_results")
    op.drop_index(op.f("ix_grai_eval_results_eval_run_id"), table_name="grai_eval_results")
    op.drop_index(op.f("ix_grai_eval_results_suite_id"), table_name="grai_eval_results")
    op.drop_index(op.f("ix_grai_eval_results_tenant_id"), table_name="grai_eval_results")
    op.drop_table("grai_eval_results")
    op.drop_index(op.f("ix_grai_eval_runs_schedule_id"), table_name="grai_eval_runs")
    op.drop_index(op.f("ix_grai_eval_runs_transport_profile_id"), table_name="grai_eval_runs")
    op.drop_index(op.f("ix_grai_eval_runs_suite_id"), table_name="grai_eval_runs")
    op.drop_index(op.f("ix_grai_eval_runs_tenant_id"), table_name="grai_eval_runs")
    op.drop_index("ix_grai_eval_runs_tenant_created", table_name="grai_eval_runs")
    op.drop_table("grai_eval_runs")
