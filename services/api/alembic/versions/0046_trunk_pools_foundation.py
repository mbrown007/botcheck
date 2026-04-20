"""add trunk pools foundation

Revision ID: 0046_trunk_pools_foundation
Revises: 0045_ai_scenario_namespace
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_trunk_pools_foundation"
down_revision = "0045_ai_scenario_namespace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trunk_pools",
        sa.Column("trunk_pool_id", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "selection_policy",
            sa.String(length=64),
            nullable=False,
            server_default="first_available",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trunk_pool_id"),
        sa.UniqueConstraint("provider_name", "name", name="uq_trunk_pools_provider_name"),
    )
    op.create_index(
        "ix_trunk_pools_provider_name",
        "trunk_pools",
        ["provider_name"],
        unique=False,
    )

    op.create_table(
        "trunk_pool_members",
        sa.Column("trunk_pool_member_id", sa.String(length=64), nullable=False),
        sa.Column("trunk_pool_id", sa.String(length=64), nullable=False),
        sa.Column("trunk_id", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trunk_pool_member_id"),
        sa.UniqueConstraint(
            "trunk_pool_id",
            "trunk_id",
            name="uq_trunk_pool_members_pool_trunk",
        ),
    )
    op.create_index(
        "ix_trunk_pool_members_trunk_pool_id",
        "trunk_pool_members",
        ["trunk_pool_id"],
        unique=False,
    )
    op.create_index(
        "ix_trunk_pool_members_trunk_id",
        "trunk_pool_members",
        ["trunk_id"],
        unique=False,
    )

    op.create_table(
        "tenant_trunk_pools",
        sa.Column("tenant_trunk_pool_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("trunk_pool_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_label", sa.String(length=255), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_trunk_pool_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "trunk_pool_id",
            name="uq_tenant_trunk_pools_tenant_pool",
        ),
    )
    op.create_index(
        "ix_tenant_trunk_pools_tenant_id",
        "tenant_trunk_pools",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_trunk_pools_trunk_pool_id",
        "tenant_trunk_pools",
        ["trunk_pool_id"],
        unique=False,
    )

    op.add_column(
        "bot_destinations",
        sa.Column("trunk_pool_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_bot_destinations_trunk_pool_id",
        "bot_destinations",
        ["trunk_pool_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bot_destinations_trunk_pool_id", table_name="bot_destinations")
    op.drop_column("bot_destinations", "trunk_pool_id")

    op.drop_index("ix_tenant_trunk_pools_trunk_pool_id", table_name="tenant_trunk_pools")
    op.drop_index("ix_tenant_trunk_pools_tenant_id", table_name="tenant_trunk_pools")
    op.drop_table("tenant_trunk_pools")

    op.drop_index("ix_trunk_pool_members_trunk_id", table_name="trunk_pool_members")
    op.drop_index("ix_trunk_pool_members_trunk_pool_id", table_name="trunk_pool_members")
    op.drop_table("trunk_pool_members")

    op.drop_index("ix_trunk_pools_provider_name", table_name="trunk_pools")
    op.drop_table("trunk_pools")
