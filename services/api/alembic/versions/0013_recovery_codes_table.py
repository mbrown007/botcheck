"""Add recovery_codes table for Phase 6 TOTP recovery flow.

Revision ID: 0013
Revises: 0012
Create Date: 2026-02-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recovery_codes",
        sa.Column("code_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("code_id"),
    )
    op.create_index("ix_recovery_codes_tenant_id", "recovery_codes", ["tenant_id"], unique=False)
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"], unique=False)
    op.create_index("ix_recovery_codes_batch_id", "recovery_codes", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recovery_codes_batch_id", table_name="recovery_codes")
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_index("ix_recovery_codes_tenant_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
