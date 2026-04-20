"""snapshot direct http transport config onto runs

Revision ID: 0041_run_http_transport_snapshot
Revises: 0040_http_transport_profiles
Create Date: 2026-03-11 21:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0041_run_http_transport_snapshot"
down_revision = "0040_http_transport_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("direct_http_headers_at_start", sa.JSON(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("direct_http_config_at_start", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "direct_http_config_at_start")
    op.drop_column("runs", "direct_http_headers_at_start")
