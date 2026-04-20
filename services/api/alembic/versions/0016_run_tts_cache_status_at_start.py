"""Add run cache-status snapshot captured at run start.

Revision ID: 0016
Revises: 0015
Create Date: 2026-02-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("tts_cache_status_at_start", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "tts_cache_status_at_start")
