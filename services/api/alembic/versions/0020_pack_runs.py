"""Add pack_runs table.

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pack_runs",
        sa.Column("pack_run_id", sa.String(length=64), nullable=False),
        sa.Column("pack_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("schedule_id", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(length=255), nullable=True),
        sa.Column("gate_outcome", sa.String(length=32), nullable=False),
        sa.Column("total_scenarios", sa.Integer(), nullable=False),
        sa.Column("dispatched", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("pack_run_id"),
    )
    op.create_index("ix_pack_runs_pack_id", "pack_runs", ["pack_id"], unique=False)
    op.create_index("ix_pack_runs_tenant_id", "pack_runs", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pack_runs_tenant_id", table_name="pack_runs")
    op.drop_index("ix_pack_runs_pack_id", table_name="pack_runs")
    op.drop_table("pack_runs")
