"""Initial schema — scenarios and runs tables.

Revision ID: 0001
Revises:
Create Date: 2026-02-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("scenario_id", sa.String(), nullable=False),
        sa.Column("version_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scenario_id"),
    )
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("scenario_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("livekit_room", sa.String(length=255), nullable=False),
        sa.Column("conversation", sa.Text(), nullable=False),
        sa.Column("failed_dimensions", sa.Text(), nullable=False),
        sa.Column("gate_result", sa.String(length=64), nullable=True),
        sa.Column("overall_status", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("report_s3_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("scenarios")
