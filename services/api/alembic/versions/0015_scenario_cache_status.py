"""Add scenario cache status metadata columns.

Revision ID: 0015
Revises: 0014
Create Date: 2026-02-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column(
            "cache_status",
            sa.String(length=16),
            nullable=False,
            server_default="cold",
        ),
    )
    op.add_column(
        "scenarios",
        sa.Column("cache_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "cache_updated_at")
    op.drop_column("scenarios", "cache_status")
