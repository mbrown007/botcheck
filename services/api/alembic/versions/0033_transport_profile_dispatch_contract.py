"""Add transport-profile dispatch contract fields.

Revision ID: 0033
Revises: 0032
Create Date: 2026-03-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("transport_profile_id_at_start", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("dial_target_at_start", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "pack_runs",
        sa.Column("transport_profile_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pack_runs",
        sa.Column("dial_target", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_pack_runs_transport_profile_id",
        "pack_runs",
        ["transport_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pack_runs_transport_profile_id", table_name="pack_runs")
    op.drop_column("pack_runs", "dial_target")
    op.drop_column("pack_runs", "transport_profile_id")
    op.drop_column("runs", "dial_target_at_start")
    op.drop_column("runs", "transport_profile_id_at_start")
