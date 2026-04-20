"""add grai eval suites

Revision ID: 0048_grai_eval_suites
Revises: 0047_playground_presets
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0048_grai_eval_suites"
down_revision = "0047_playground_presets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grai_eval_suites",
        sa.Column("suite_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_yaml", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("suite_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_grai_eval_suites_tenant_name"),
    )
    op.create_index(
        "ix_grai_eval_suites_tenant_updated",
        "grai_eval_suites",
        ["tenant_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_suites_tenant_id"),
        "grai_eval_suites",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "grai_eval_prompts",
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("suite_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("prompt_id"),
        sa.UniqueConstraint("suite_id", "order_index", name="uq_grai_eval_prompts_suite_order"),
        sa.UniqueConstraint("suite_id", "label", name="uq_grai_eval_prompts_suite_label"),
    )
    op.create_index(
        op.f("ix_grai_eval_prompts_suite_id"),
        "grai_eval_prompts",
        ["suite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_prompts_tenant_id"),
        "grai_eval_prompts",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "grai_eval_cases",
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("suite_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vars_json", sa.JSON(), nullable=False),
        sa.Column("assert_json", sa.JSON(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("import_threshold", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("suite_id", "order_index", name="uq_grai_eval_cases_suite_order"),
    )
    op.create_index(
        op.f("ix_grai_eval_cases_suite_id"),
        "grai_eval_cases",
        ["suite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_cases_tenant_id"),
        "grai_eval_cases",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_grai_eval_cases_tenant_id"), table_name="grai_eval_cases")
    op.drop_index(op.f("ix_grai_eval_cases_suite_id"), table_name="grai_eval_cases")
    op.drop_table("grai_eval_cases")
    op.drop_index(op.f("ix_grai_eval_prompts_tenant_id"), table_name="grai_eval_prompts")
    op.drop_index(op.f("ix_grai_eval_prompts_suite_id"), table_name="grai_eval_prompts")
    op.drop_table("grai_eval_prompts")
    op.drop_index(op.f("ix_grai_eval_suites_tenant_id"), table_name="grai_eval_suites")
    op.drop_index("ix_grai_eval_suites_tenant_updated", table_name="grai_eval_suites")
    op.drop_table("grai_eval_suites")
