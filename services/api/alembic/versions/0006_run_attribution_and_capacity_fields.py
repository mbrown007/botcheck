"""Add run attribution and SIP slot tracking columns.

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("trigger_source", sa.String(length=64), nullable=False, server_default="manual"),
    )
    op.add_column("runs", sa.Column("schedule_id", sa.String(length=255), nullable=True))
    op.add_column("runs", sa.Column("triggered_by", sa.String(length=255), nullable=True))
    op.add_column(
        "runs",
        sa.Column("transport", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column(
        "runs",
        sa.Column("sip_slot_held", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.alter_column("runs", "trigger_source", server_default=None)
    op.alter_column("runs", "transport", server_default=None)
    op.alter_column("runs", "sip_slot_held", server_default=None)


def downgrade() -> None:
    op.drop_column("runs", "sip_slot_held")
    op.drop_column("runs", "transport")
    op.drop_column("runs", "triggered_by")
    op.drop_column("runs", "schedule_id")
    op.drop_column("runs", "trigger_source")
