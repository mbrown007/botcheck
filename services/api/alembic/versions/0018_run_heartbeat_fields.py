"""Add run heartbeat runtime snapshot fields.

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("last_heartbeat_seq", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "last_heartbeat_seq")
    op.drop_column("runs", "last_heartbeat_at")
