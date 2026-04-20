"""Make transport profile default dial target optional.

Revision ID: 0034
Revises: 0033
Create Date: 2026-03-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "bot_destinations",
        "endpoint",
        existing_type=sa.String(length=512),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "bot_destinations",
        "endpoint",
        existing_type=sa.String(length=512),
        nullable=False,
    )
