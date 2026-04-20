"""platform settings singleton

Revision ID: 0038_platform_settings
Revises: 0037_tenants_foundation
Create Date: 2026-03-10 14:15:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0038_platform_settings"
down_revision = "0037_tenants_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("singleton_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("feature_flags", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("quota_defaults", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            "INSERT INTO platform_settings "
            "(singleton_id, feature_flags, quota_defaults, created_at, updated_at) "
            "VALUES ('default', '{}', '{}', :created_at, :updated_at)"
        ).bindparams(created_at=now, updated_at=now)
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
