"""snapshot webrtc transport config onto runs

Revision ID: 0058_run_webrtc_snap
Revises: 0057_dest_webrtc_config
Create Date: 2026-04-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0058_run_webrtc_snap"
down_revision = "0057_dest_webrtc_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("webrtc_config_at_start", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "webrtc_config_at_start")
