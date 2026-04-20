"""add schedule name column

Revision ID: 0039_schedule_name
Revises: 0038_platform_settings
Create Date: 2026-03-11 16:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039_schedule_name"
down_revision: str | Sequence[str] | None = "0038_platform_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "name")
