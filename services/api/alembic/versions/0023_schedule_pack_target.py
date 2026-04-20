"""Add schedule target_type/pack_id and XOR constraint for Phase 9.

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column(
            "target_type",
            sa.String(length=32),
            nullable=False,
            server_default="scenario",
        ),
    )
    op.add_column("schedules", sa.Column("pack_id", sa.String(length=64), nullable=True))
    op.create_index("ix_schedules_pack_id", "schedules", ["pack_id"], unique=False)
    op.alter_column("schedules", "scenario_id", existing_type=sa.String(length=255), nullable=True)
    op.create_check_constraint(
        "ck_schedules_target_xor",
        "schedules",
        "((target_type = 'scenario' AND scenario_id IS NOT NULL AND pack_id IS NULL) OR "
        "(target_type = 'pack' AND pack_id IS NOT NULL AND scenario_id IS NULL))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_schedules_target_xor", "schedules", type_="check")
    op.drop_index("ix_schedules_pack_id", table_name="schedules")
    op.execute("UPDATE schedules SET scenario_id = '' WHERE scenario_id IS NULL")
    op.alter_column("schedules", "scenario_id", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("schedules", "pack_id")
    op.drop_column("schedules", "target_type")
