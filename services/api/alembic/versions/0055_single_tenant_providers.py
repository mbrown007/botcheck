"""enforce single-tenant provider assignments

Revision ID: 0055_single_tenant_providers
Revises: 0054_provider_label
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0055_single_tenant_providers"
down_revision = "0054_provider_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy bootstrap seeded every catalog provider to every tenant. Keep one
    # assignment row per provider (the earliest row by timestamps/id), delete
    # extra assignment rows, and clear quota policies for superseded tenants so
    # the new provider->tenant invariant is not violated by stale data.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    assignment_id,
                    provider_id,
                    tenant_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY provider_id
                        ORDER BY created_at ASC, updated_at ASC, assignment_id ASC
                    ) AS row_num
                FROM tenant_provider_assignments
            ),
            keepers AS (
                SELECT provider_id, tenant_id
                FROM ranked
                WHERE row_num = 1
            )
            DELETE FROM provider_quota_policies
            WHERE EXISTS (
                SELECT 1
                FROM keepers
                WHERE keepers.provider_id = provider_quota_policies.provider_id
                  AND keepers.tenant_id <> provider_quota_policies.tenant_id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    assignment_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY provider_id
                        ORDER BY created_at ASC, updated_at ASC, assignment_id ASC
                    ) AS row_num
                FROM tenant_provider_assignments
            )
            DELETE FROM tenant_provider_assignments
            WHERE assignment_id IN (
                SELECT assignment_id
                FROM ranked
                WHERE row_num > 1
            )
            """
        )
    )
    with op.batch_alter_table("tenant_provider_assignments") as batch_op:
        batch_op.create_unique_constraint(
            "uq_tenant_provider_assignments_provider",
            ["provider_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tenant_provider_assignments") as batch_op:
        batch_op.drop_constraint(
            "uq_tenant_provider_assignments_provider",
            type_="unique",
        )
