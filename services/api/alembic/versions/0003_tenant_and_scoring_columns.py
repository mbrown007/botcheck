"""Add scenario tenant scoping and run score/finding JSON columns.

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Scenario tenant scoping for explicit per-tenant reads/writes.
    op.add_column(
        "scenarios",
        sa.Column(
            "tenant_id",
            sa.String(length=255),
            nullable=False,
            server_default="default",
        ),
    )
    op.create_index("ix_scenarios_tenant_id", "scenarios", ["tenant_id"], unique=False)
    op.alter_column("scenarios", "tenant_id", server_default=None)

    # Run-level API payload support for score cards and findings views.
    if is_postgres:
        scores_type = postgresql.JSONB(astext_type=sa.Text())
        findings_type = postgresql.JSONB(astext_type=sa.Text())
        scores_default = sa.text("'{}'::jsonb")
        findings_default = sa.text("'[]'::jsonb")
    else:
        scores_type = sa.JSON()
        findings_type = sa.JSON()
        scores_default = "{}"
        findings_default = "[]"

    op.add_column(
        "runs",
        sa.Column(
            "scores",
            scores_type,
            nullable=False,
            server_default=scores_default,
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "findings",
            findings_type,
            nullable=False,
            server_default=findings_default,
        ),
    )
    op.alter_column("runs", "scores", server_default=None)
    op.alter_column("runs", "findings", server_default=None)


def downgrade() -> None:
    op.drop_column("runs", "findings")
    op.drop_column("runs", "scores")
    op.drop_index("ix_scenarios_tenant_id", table_name="scenarios")
    op.drop_column("scenarios", "tenant_id")
