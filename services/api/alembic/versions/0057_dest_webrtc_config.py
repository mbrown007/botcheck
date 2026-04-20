"""add webrtc config to bot destinations

Revision ID: 0057_dest_webrtc_config
Revises: 0056_pool_assignment_quotas
Create Date: 2026-04-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0057_dest_webrtc_config"
down_revision = "0056_pool_assignment_quotas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bot_destinations") as batch_op:
        batch_op.add_column(sa.Column("webrtc_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bot_destinations") as batch_op:
        batch_op.drop_column("webrtc_config")
