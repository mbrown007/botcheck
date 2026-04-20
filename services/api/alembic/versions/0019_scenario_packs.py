"""Add scenario pack tables.

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenario_packs",
        sa.Column("pack_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("pack_id"),
    )
    op.create_index(
        "ix_scenario_packs_tenant_id",
        "scenario_packs",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "scenario_pack_items",
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("pack_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("item_id"),
        sa.UniqueConstraint("pack_id", "scenario_id", name="uq_pack_scenario"),
    )
    op.create_index(
        "ix_scenario_pack_items_pack_id",
        "scenario_pack_items",
        ["pack_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_pack_items_pack_id", table_name="scenario_pack_items")
    op.drop_table("scenario_pack_items")
    op.drop_index("ix_scenario_packs_tenant_id", table_name="scenario_packs")
    op.drop_table("scenario_packs")
