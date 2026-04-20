"""add quota fields to tenant trunk pool assignments

Revision ID: 0056_tenant_trunk_pool_assignment_quotas
Revises: 0055_single_tenant_providers
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0056_pool_assignment_quotas"
down_revision = "0055_single_tenant_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_trunk_pools") as batch_op:
        batch_op.add_column(sa.Column("max_channels", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reserved_channels", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_tenant_trunk_pools_max_channels_min",
            "(max_channels IS NULL OR max_channels >= 1)",
        )
        batch_op.create_check_constraint(
            "ck_tenant_trunk_pools_reserved_channels_min",
            "(reserved_channels IS NULL OR reserved_channels >= 0)",
        )
        batch_op.create_check_constraint(
            "ck_tenant_trunk_pools_reserved_le_max",
            "(max_channels IS NULL OR reserved_channels IS NULL OR reserved_channels <= max_channels)",
        )


def downgrade() -> None:
    with op.batch_alter_table("tenant_trunk_pools") as batch_op:
        batch_op.drop_constraint(
            "ck_tenant_trunk_pools_reserved_le_max",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_tenant_trunk_pools_reserved_channels_min",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_tenant_trunk_pools_max_channels_min",
            type_="check",
        )
        batch_op.drop_column("reserved_channels")
        batch_op.drop_column("max_channels")
