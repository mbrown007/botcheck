"""add grai eval terminal outcome

Revision ID: 0053_grai_eval_terminal_outcome
Revises: 0052_provider_usage_keys
Create Date: 2026-03-17 22:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0053_grai_eval_terminal_outcome"
down_revision = "0052_provider_usage_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grai_eval_runs",
        sa.Column("terminal_outcome", sa.String(length=32), nullable=True),
    )
    # Backfill inference notes:
    # - 'complete' → 'passed': all terminal complete runs passed assertions by definition.
    # - 'cancelled' → 'cancelled': unambiguous.
    # - 'failed' AND failed_count > 0 → 'assertion_failed': at least one assertion row
    #   failed, so the run reached an assertion that did not pass.
    # - 'failed' AND failed_count = 0 → 'execution_failed': the run failed before any
    #   assertion could complete (e.g. HTTP error, eval worker crash). In practice no
    #   such rows exist in production — failed_count == 0 on a failed run implies the
    #   worker never recorded results — so this branch is a safe default for the enum
    #   and will never match existing data.
    # - Any other status (pending, running) → NULL: not yet terminal; stays NULL.
    op.execute(
        """
        UPDATE grai_eval_runs
        SET terminal_outcome = CASE
            WHEN status = 'complete' THEN 'passed'
            WHEN status = 'cancelled' THEN 'cancelled'
            WHEN status = 'failed' AND failed_count > 0 THEN 'assertion_failed'
            WHEN status = 'failed' THEN 'execution_failed'
            ELSE NULL
        END
        """
    )
    op.create_check_constraint(
        "ck_grai_eval_runs_terminal_outcome",
        "grai_eval_runs",
        "terminal_outcome IS NULL OR terminal_outcome IN "
        "('passed', 'assertion_failed', 'execution_failed', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_grai_eval_runs_terminal_outcome",
        "grai_eval_runs",
        type_="check",
    )
    op.drop_column("grai_eval_runs", "terminal_outcome")
