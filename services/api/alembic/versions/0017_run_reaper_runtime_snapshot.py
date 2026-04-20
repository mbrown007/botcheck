"""Add run runtime snapshots for reaper reconciliation.

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("max_duration_s_at_start", sa.Float(), nullable=True))
    op.create_index("ix_runs_tenant_state", "runs", ["tenant_id", "state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_tenant_state", table_name="runs")
    op.drop_column("runs", "max_duration_s_at_start")
    op.drop_column("runs", "run_started_at")
