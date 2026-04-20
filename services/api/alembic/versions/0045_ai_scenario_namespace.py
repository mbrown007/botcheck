"""add namespace to ai scenarios

Revision ID: 0045_ai_scenario_namespace
Revises: 0044_scenario_namespace
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_ai_scenario_namespace"
down_revision = "0044_scenario_namespace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_scenarios", sa.Column("namespace", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_ai_scenarios_tenant_namespace",
        "ai_scenarios",
        ["tenant_id", "namespace"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_scenarios_tenant_namespace", table_name="ai_scenarios")
    op.drop_column("ai_scenarios", "namespace")

