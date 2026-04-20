"""Add bot destinations registry table.

Revision ID: 0026
Revises: 0025
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_destinations",
        sa.Column("destination_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("caller_id", sa.String(length=64), nullable=True),
        sa.Column("trunk_id", sa.String(length=255), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("provisioned_channels", sa.Integer(), nullable=True),
        sa.Column("reserved_channels", sa.Integer(), nullable=True),
        sa.Column("botcheck_max_channels", sa.Integer(), nullable=True),
        sa.Column("capacity_scope", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "protocol IN ('sip', 'webrtc', 'mock')",
            name="ck_bot_destinations_protocol",
        ),
        sa.CheckConstraint(
            "(provisioned_channels IS NULL OR provisioned_channels >= 1)",
            name="ck_bot_destinations_provisioned_channels_min",
        ),
        sa.CheckConstraint(
            "(reserved_channels IS NULL OR reserved_channels >= 0)",
            name="ck_bot_destinations_reserved_channels_min",
        ),
        sa.CheckConstraint(
            "(botcheck_max_channels IS NULL OR botcheck_max_channels >= 1)",
            name="ck_bot_destinations_botcheck_max_channels_min",
        ),
        sa.CheckConstraint(
            "(provisioned_channels IS NULL OR reserved_channels IS NULL "
            "OR reserved_channels <= provisioned_channels)",
            name="ck_bot_destinations_reserved_le_provisioned",
        ),
        sa.PrimaryKeyConstraint("destination_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_bot_destinations_tenant_name"),
    )
    op.create_index(
        "ix_bot_destinations_tenant_id",
        "bot_destinations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_bot_destinations_tenant_capacity_scope",
        "bot_destinations",
        ["tenant_id", "capacity_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bot_destinations_tenant_capacity_scope", table_name="bot_destinations")
    op.drop_index("ix_bot_destinations_tenant_id", table_name="bot_destinations")
    op.drop_table("bot_destinations")
