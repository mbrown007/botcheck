"""add http transport profile foundation

Revision ID: 0040_http_transport_profiles
Revises: 0039_schedule_name
Create Date: 2026-03-11 19:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040_http_transport_profiles"
down_revision = "0039_schedule_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bot_destinations",
        sa.Column("direct_http_config", sa.JSON(), nullable=True),
    )
    op.drop_constraint("ck_bot_destinations_protocol", "bot_destinations", type_="check")
    op.create_check_constraint(
        "ck_bot_destinations_protocol",
        "bot_destinations",
        "protocol IN ('sip', 'http', 'webrtc', 'mock')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bot_destinations_protocol", "bot_destinations", type_="check")
    op.create_check_constraint(
        "ck_bot_destinations_protocol",
        "bot_destinations",
        "protocol IN ('sip', 'webrtc', 'mock')",
    )
    op.drop_column("bot_destinations", "direct_http_config")
