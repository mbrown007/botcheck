"""Create schedules table for Phase 3 scheduling engine.

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_expr() -> str:
    return "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("schedule_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("scenario_id", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cron_expr", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=64), nullable=True),
        sa.Column(
            "misfire_policy",
            sa.String(length=32),
            nullable=False,
            server_default="skip",
        ),
        sa.Column("config_overrides", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("schedule_id"),
    )
    op.create_index("ix_schedules_tenant_id", "schedules", ["tenant_id"], unique=False)
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"], unique=False)
    op.create_index(
        "ix_schedules_tenant_active_next",
        "schedules",
        ["tenant_id", "active", "next_run_at"],
        unique=False,
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        tenant_expr = _tenant_expr()
        op.execute("ALTER TABLE schedules ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE schedules FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY schedules_tenant_isolation ON schedules "
            f"USING ({tenant_expr}) "
            f"WITH CHECK ({tenant_expr})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS schedules_tenant_isolation ON schedules")
        op.execute("ALTER TABLE schedules NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE schedules DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_schedules_tenant_active_next", table_name="schedules")
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_index("ix_schedules_tenant_id", table_name="schedules")
    op.drop_table("schedules")
