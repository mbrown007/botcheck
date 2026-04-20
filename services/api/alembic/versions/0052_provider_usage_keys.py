"""add provider usage keys

Revision ID: 0052_provider_usage_keys
Revises: 0051_provider_registry
Create Date: 2026-03-17 20:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0052_provider_usage_keys"
down_revision = "0051_provider_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_usage_ledger",
        sa.Column("usage_key", sa.String(length=255), nullable=True),
    )
    # Back-fill pre-existing rows with their own ledger_id. These rows pre-date structured
    # keys, so they become orphaned historical records that will never be matched by a
    # subsequent upsert — which is correct: their usage was already recorded and should
    # not be overwritten by future writes.
    op.execute("UPDATE provider_usage_ledger SET usage_key = ledger_id WHERE usage_key IS NULL")
    op.alter_column("provider_usage_ledger", "usage_key", nullable=False)
    # The unique constraint implicitly creates an index; no separate non-unique index needed.
    op.create_unique_constraint(
        "uq_provider_usage_ledger_usage_key",
        "provider_usage_ledger",
        ["usage_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_provider_usage_ledger_usage_key",
        "provider_usage_ledger",
        type_="unique",
    )
    op.drop_column("provider_usage_ledger", "usage_key")
