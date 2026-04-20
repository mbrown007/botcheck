"""add playground run contract columns

Revision ID: 0042_playground_run_contract
Revises: 0041_run_http_transport_snapshot
Create Date: 2026-03-12 14:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_playground_run_contract"
down_revision = "0041_run_http_transport_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "run_type",
            sa.String(length=16),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "runs",
        sa.Column("playground_mode", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("playground_system_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("playground_tool_stubs", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "ck_runs_run_type",
        "runs",
        "run_type IN ('standard', 'playground')",
    )
    op.create_check_constraint(
        "ck_runs_playground_mode",
        "runs",
        "(playground_mode IS NULL OR playground_mode IN ('mock', 'direct_http'))",
    )
    op.alter_column("runs", "run_type", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_runs_playground_mode", "runs", type_="check")
    op.drop_constraint("ck_runs_run_type", "runs", type_="check")
    op.drop_column("runs", "playground_tool_stubs")
    op.drop_column("runs", "playground_system_prompt")
    op.drop_column("runs", "playground_mode")
    op.drop_column("runs", "run_type")
