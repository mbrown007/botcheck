"""Add SIP trunk registry table.

Revision ID: 0032
Revises: 0031_ai_persona_identity_fields
Create Date: 2026-03-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031_ai_persona_identity_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sip_trunks",
        sa.Column("trunk_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("transport", sa.String(length=64), nullable=True),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trunk_id"),
    )
    op.create_index("ix_sip_trunks_is_active", "sip_trunks", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sip_trunks_is_active", table_name="sip_trunks")
    op.drop_table("sip_trunks")
