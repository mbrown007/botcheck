"""Add tenant registry foundation and backfill existing tenant IDs.

Revision ID: 0037_tenants_foundation
Revises: 0036_users_role_constraint
Create Date: 2026-03-10
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_tenants_foundation"
down_revision: Union[str, None] = "0036_users_role_constraint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return candidate or "default"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("feature_overrides", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("quota_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=False)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = [name for name in inspector.get_table_names() if name != "tenants"]

    tenant_ids: set[str] = {"default"}
    for table_name in table_names:
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            continue
        rows = bind.execute(
            sa.text(
                f'SELECT DISTINCT tenant_id FROM "{table_name}" '
                "WHERE tenant_id IS NOT NULL AND tenant_id <> ''"
            )
        ).scalars()
        tenant_ids.update(str(value).strip() for value in rows if str(value).strip())

    tenants = sa.table(
        "tenants",
        sa.column("tenant_id", sa.String(length=255)),
        sa.column("slug", sa.String(length=255)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("feature_overrides", sa.JSON()),
        sa.column("quota_config", sa.JSON()),
    )
    op.bulk_insert(
        tenants,
        [
            {
                "tenant_id": tenant_id,
                "slug": _slugify(tenant_id),
                "display_name": "Default Tenant" if tenant_id == "default" else tenant_id,
                "feature_overrides": {},
                "quota_config": {},
            }
            for tenant_id in sorted(tenant_ids)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
