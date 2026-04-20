"""Add optional idempotency key for pack runs.

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pack_runs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index(
        "ix_pack_runs_idempotency_lookup",
        "pack_runs",
        ["tenant_id", "pack_id", "idempotency_key", "state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pack_runs_idempotency_lookup", table_name="pack_runs")
    op.drop_column("pack_runs", "idempotency_key")
