"""provider_catalog: add label column for user-created provider entries.

Revision ID: 0054_provider_label
Revises: 0053_grai_eval_terminal_outcome
Create Date: 2026-03-18

Adds an optional human-friendly label to ProviderCatalogRow.
Seeded providers have label=NULL; user-created entries carry a label
supplied by the system admin.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0054_provider_label"
down_revision = "0053_grai_eval_terminal_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_catalog",
        sa.Column("label", sa.String(255), nullable=True, server_default=None),
    )
    # Mark seeded rows as user_created=False; new rows default to True.
    op.add_column(
        "provider_catalog",
        sa.Column(
            "user_created",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_catalog", "user_created")
    op.drop_column("provider_catalog", "label")
