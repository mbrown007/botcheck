"""Add dispatch-level destination binding to pack runs.

Revision ID: 0028
Revises: 0027
Create Date: 2026-03-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pack_runs", sa.Column("destination_id", sa.String(length=64), nullable=True))
    op.create_index("ix_pack_runs_destination_id", "pack_runs", ["destination_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pack_runs_destination_id", table_name="pack_runs")
    op.drop_column("pack_runs", "destination_id")
