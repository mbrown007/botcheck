"""Migrate conversation and failed_dimensions from TEXT to JSONB (PostgreSQL).

On PostgreSQL, the existing TEXT columns (which already contain valid JSON)
are cast in-place to JSONB using a USING clause. No data transformation is
required since the stored values are always valid JSON arrays.

On other dialects (SQLite for tests), SQLAlchemy's JSON type already renders
as TEXT with automatic Python serde — no DDL change is needed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Cast existing JSON-as-text values to native JSONB in one statement each.
    # The USING clause handles the conversion without a full table rewrite on
    # Postgres 14+ (it uses an in-place rewrite only for rows that need it).
    op.execute(
        "ALTER TABLE runs "
        "ALTER COLUMN conversation TYPE jsonb "
        "USING conversation::jsonb"
    )
    op.execute(
        "ALTER TABLE runs "
        "ALTER COLUMN failed_dimensions TYPE jsonb "
        "USING failed_dimensions::jsonb"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "ALTER TABLE runs "
        "ALTER COLUMN conversation TYPE text "
        "USING conversation::text"
    )
    op.execute(
        "ALTER TABLE runs "
        "ALTER COLUMN failed_dimensions TYPE text "
        "USING failed_dimensions::text"
    )
