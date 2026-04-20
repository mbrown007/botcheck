"""Add retention profile to runs.

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "retention_profile",
            sa.String(length=32),
            nullable=False,
            server_default="standard",
        ),
    )
    op.alter_column("runs", "retention_profile", server_default=None)


def downgrade() -> None:
    op.drop_column("runs", "retention_profile")
