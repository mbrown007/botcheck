"""Add run end_reason and end_source fields.

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-27

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("end_reason", sa.String(length=64), nullable=True))
    op.add_column("runs", sa.Column("end_source", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "end_source")
    op.drop_column("runs", "end_reason")

