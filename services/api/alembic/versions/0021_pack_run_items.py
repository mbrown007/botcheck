"""Add pack_run_items table.

Revision ID: 0021
Revises: 0020
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pack_run_items",
        sa.Column("pack_run_item_id", sa.String(length=64), nullable=False),
        sa.Column("pack_run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("scenario_id", sa.String(length=255), nullable=False),
        sa.Column("scenario_version_hash", sa.String(length=64), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("pack_run_item_id"),
        sa.UniqueConstraint("pack_run_id", "scenario_id", name="uq_pack_run_item_scenario"),
    )
    op.create_index(
        "ix_pack_run_items_pack_run_id",
        "pack_run_items",
        ["pack_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_pack_run_items_tenant_id",
        "pack_run_items",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pack_run_items_tenant_id", table_name="pack_run_items")
    op.drop_index("ix_pack_run_items_pack_run_id", table_name="pack_run_items")
    op.drop_table("pack_run_items")
