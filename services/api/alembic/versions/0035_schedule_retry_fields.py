"""Add schedule retry and outcome tracking fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0035_schedule_retry_fields"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("last_run_outcome", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "schedules",
        sa.Column("retry_on_failure", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "schedules",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("schedules", "retry_on_failure", server_default=None)
    op.alter_column("schedules", "consecutive_failures", server_default=None)


def downgrade() -> None:
    op.drop_column("schedules", "consecutive_failures")
    op.drop_column("schedules", "retry_on_failure")
    op.drop_column("schedules", "last_run_outcome")
