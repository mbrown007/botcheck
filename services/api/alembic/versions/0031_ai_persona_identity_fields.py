"""Add AI persona identity fields.

Revision ID: 0031_ai_persona_identity_fields
Revises: 0030_ai_scenarios_intent_first
Create Date: 2026-03-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0031_ai_persona_identity_fields"
down_revision = "0030_ai_scenarios_intent_first"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_personas", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("ai_personas", sa.Column("avatar_url", sa.String(length=512), nullable=True))
    op.add_column("ai_personas", sa.Column("backstory_summary", sa.Text(), nullable=True))
    op.execute("UPDATE ai_personas SET display_name = name WHERE display_name IS NULL")


def downgrade() -> None:
    op.drop_column("ai_personas", "backstory_summary")
    op.drop_column("ai_personas", "avatar_url")
    op.drop_column("ai_personas", "display_name")
