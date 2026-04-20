"""Add cost_pence to runs for pack cost rollups.

Revision ID: 0025
Revises: 0024
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("cost_pence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "cost_pence")
