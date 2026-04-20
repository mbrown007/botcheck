"""Add run error_code taxonomy field and immutable events log column.

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-25

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.add_column("runs", sa.Column("error_code", sa.String(length=64), nullable=True))

    events_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    events_default = sa.text("'[]'::jsonb") if is_postgres else "[]"
    op.add_column(
        "runs",
        sa.Column(
            "events",
            events_type,
            nullable=False,
            server_default=events_default,
        ),
    )
    op.alter_column("runs", "events", server_default=None)


def downgrade() -> None:
    op.drop_column("runs", "events")
    op.drop_column("runs", "error_code")
