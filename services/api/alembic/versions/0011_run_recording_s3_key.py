"""Add recording artifact key to runs.

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("recording_s3_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "recording_s3_key")
