"""Add pack_run_id reference to runs.

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("pack_run_id", sa.String(length=64), nullable=True))
    op.create_index("ix_runs_pack_run_id", "runs", ["pack_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_pack_run_id", table_name="runs")
    op.drop_column("runs", "pack_run_id")
