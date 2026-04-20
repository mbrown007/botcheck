"""add namespace column to scenarios

Revision ID: 0044_scenario_namespace
Revises: 0043_playground_events
Create Date: 2026-03-13 17:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_scenario_namespace"
down_revision = "0043_playground_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("namespace", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_scenarios_tenant_namespace",
        "scenarios",
        ["tenant_id", "namespace"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scenarios_tenant_namespace", table_name="scenarios")
    op.drop_column("scenarios", "namespace")
