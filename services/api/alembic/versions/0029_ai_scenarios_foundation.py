"""Add AI scenario foundation schema and scenario kind discriminator.

Revision ID: 0029
Revises: 0028
Create Date: 2026-03-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column(
            "scenario_kind",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'graph'"),
        ),
    )
    op.execute("UPDATE scenarios SET scenario_kind = 'graph' WHERE scenario_kind IS NULL")
    op.alter_column(
        "scenarios",
        "scenario_kind",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default=sa.text("'graph'"),
    )
    op.create_check_constraint(
        "ck_scenarios_kind",
        "scenarios",
        "scenario_kind IN ('graph', 'ai')",
    )
    op.create_index(
        "ix_scenarios_tenant_kind",
        "scenarios",
        ["tenant_id", "scenario_kind"],
        unique=False,
    )

    op.create_table(
        "ai_personas",
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("style", sa.String(length=128), nullable=True),
        sa.Column("voice", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("persona_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ai_personas_tenant_name"),
    )
    op.create_index("ix_ai_personas_tenant_id", "ai_personas", ["tenant_id"], unique=False)

    op.create_table(
        "ai_scenarios",
        sa.Column("scenario_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("scoring_profile", sa.String(length=128), nullable=True),
        sa.Column("dataset_source", sa.String(length=255), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scenario_id"),
    )
    op.create_index("ix_ai_scenarios_tenant_id", "ai_scenarios", ["tenant_id"], unique=False)
    op.create_index("ix_ai_scenarios_persona_id", "ai_scenarios", ["persona_id"], unique=False)

    op.create_table(
        "ai_scenario_records",
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "scenario_id",
            "order_index",
            name="uq_ai_scenario_records_order",
        ),
    )
    op.create_index(
        "ix_ai_scenario_records_scenario_id",
        "ai_scenario_records",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_scenario_records_tenant_id",
        "ai_scenario_records",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_scenario_records_tenant_id", table_name="ai_scenario_records")
    op.drop_index("ix_ai_scenario_records_scenario_id", table_name="ai_scenario_records")
    op.drop_table("ai_scenario_records")

    op.drop_index("ix_ai_scenarios_persona_id", table_name="ai_scenarios")
    op.drop_index("ix_ai_scenarios_tenant_id", table_name="ai_scenarios")
    op.drop_table("ai_scenarios")

    op.drop_index("ix_ai_personas_tenant_id", table_name="ai_personas")
    op.drop_table("ai_personas")

    op.drop_index("ix_scenarios_tenant_kind", table_name="scenarios")
    op.drop_constraint("ck_scenarios_kind", "scenarios", type_="check")
    op.drop_column("scenarios", "scenario_kind")
