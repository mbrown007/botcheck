"""Playground event stream persistence."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0043_playground_events"
down_revision = "0042_playground_run_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playground_events",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence_number", name="uq_playground_events_run_sequence"),
    )
    op.create_index(
        "ix_playground_events_run_id",
        "playground_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_playground_events_tenant_id",
        "playground_events",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_playground_events_tenant_id", table_name="playground_events")
    op.drop_index("ix_playground_events_run_id", table_name="playground_events")
    op.drop_table("playground_events")
