"""add playground presets

Revision ID: 0047_playground_presets
Revises: 0046_trunk_pools_foundation
Create Date: 2026-03-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0047_playground_presets"
down_revision = "0046_trunk_pools_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playground_presets",
        sa.Column("preset_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scenario_id", sa.String(), nullable=True),
        sa.Column("ai_scenario_id", sa.String(length=255), nullable=True),
        sa.Column("playground_mode", sa.String(length=16), nullable=False),
        sa.Column("transport_profile_id", sa.String(length=64), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("tool_stubs", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("preset_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_playground_presets_tenant_name"),
        sa.CheckConstraint(
            "(scenario_id IS NULL) != (ai_scenario_id IS NULL)",
            name="ck_playground_presets_exactly_one_target",
        ),
        sa.CheckConstraint(
            "playground_mode IN ('mock', 'direct_http')",
            name="ck_playground_presets_mode",
        ),
        sa.CheckConstraint(
            "("
            "(playground_mode = 'mock' AND system_prompt IS NOT NULL AND transport_profile_id IS NULL) "
            "OR "
            "(playground_mode = 'direct_http' AND transport_profile_id IS NOT NULL AND system_prompt IS NULL AND tool_stubs IS NULL)"
            ")",
            name="ck_playground_presets_mode_contract",
        ),
    )
    op.create_index(
        "ix_playground_presets_tenant_updated",
        "playground_presets",
        ["tenant_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_playground_presets_tenant_id"),
        "playground_presets",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_playground_presets_scenario_id"),
        "playground_presets",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_playground_presets_ai_scenario_id"),
        "playground_presets",
        ["ai_scenario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_playground_presets_transport_profile_id"),
        "playground_presets",
        ["transport_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_playground_presets_transport_profile_id"), table_name="playground_presets")
    op.drop_index(op.f("ix_playground_presets_ai_scenario_id"), table_name="playground_presets")
    op.drop_index(op.f("ix_playground_presets_scenario_id"), table_name="playground_presets")
    op.drop_index(op.f("ix_playground_presets_tenant_id"), table_name="playground_presets")
    op.drop_index("ix_playground_presets_tenant_updated", table_name="playground_presets")
    op.drop_table("playground_presets")
