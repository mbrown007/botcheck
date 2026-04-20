"""Add run destination and capacity snapshot fields.

Revision ID: 0027
Revises: 0026
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("destination_id_at_start", sa.String(length=64), nullable=True))
    op.add_column("runs", sa.Column("capacity_scope_at_start", sa.String(length=128), nullable=True))
    op.add_column("runs", sa.Column("capacity_limit_at_start", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "capacity_limit_at_start")
    op.drop_column("runs", "capacity_scope_at_start")
    op.drop_column("runs", "destination_id_at_start")
