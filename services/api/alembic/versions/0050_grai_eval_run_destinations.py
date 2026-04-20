"""add grai eval run destinations

Revision ID: 0050_grai_eval_run_destinations
Revises: 0049_grai_eval_runs
Create Date: 2026-03-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_grai_eval_run_destinations"
down_revision = "0049_grai_eval_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # grai_eval_run_destinations — FK to grai_eval_runs with CASCADE delete
    op.create_table(
        "grai_eval_run_destinations",
        sa.Column("run_dest_id", sa.String(length=64), nullable=False),
        sa.Column("eval_run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("destination_index", sa.Integer(), nullable=False),
        sa.Column("transport_profile_id", sa.String(length=64), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("endpoint_at_start", sa.String(length=512), nullable=False),
        sa.Column("headers_at_start", sa.JSON(), nullable=False),
        sa.Column("direct_http_config_at_start", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_dest_id"),
        sa.ForeignKeyConstraint(
            ["eval_run_id"],
            ["grai_eval_runs.eval_run_id"],
            ondelete="CASCADE",
            name="fk_grai_eval_run_destinations_eval_run_id",
        ),
        sa.UniqueConstraint(
            "eval_run_id",
            "destination_index",
            name="uq_grai_eval_run_destinations_run_index",
        ),
    )
    op.create_index(
        "ix_grai_eval_run_destinations_tenant_run",
        "grai_eval_run_destinations",
        ["tenant_id", "eval_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_run_destinations_eval_run_id"),
        "grai_eval_run_destinations",
        ["eval_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_run_destinations_tenant_id"),
        "grai_eval_run_destinations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grai_eval_run_destinations_transport_profile_id"),
        "grai_eval_run_destinations",
        ["transport_profile_id"],
        unique=False,
    )

    # grai_eval_results — add destination_index NOT NULL (default 0 for legacy rows).
    # Use direct DDL ops (not batch_alter_table) so PostgreSQL does an in-place ALTER
    # rather than a full-table rebuild.
    op.add_column("grai_eval_results", sa.Column("destination_index", sa.Integer(), nullable=True))
    # Coerce all pre-existing rows to destination_index = 0 before adding the NOT NULL
    # constraint. Legacy single-destination results belong to destination 0.
    op.execute("UPDATE grai_eval_results SET destination_index = 0 WHERE destination_index IS NULL")
    op.alter_column("grai_eval_results", "destination_index", nullable=False)
    op.drop_constraint(
        "uq_grai_eval_results_eval_prompt_case_assertion",
        table_name="grai_eval_results",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_grai_eval_results_eval_prompt_case_assertion",
        "grai_eval_results",
        ["eval_run_id", "prompt_id", "case_id", "destination_index", "assertion_index"],
    )
    op.create_index(
        "ix_grai_eval_results_run_destination",
        "grai_eval_results",
        ["eval_run_id", "destination_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_grai_eval_results_run_destination", table_name="grai_eval_results")
    op.drop_constraint(
        "uq_grai_eval_results_eval_prompt_case_assertion",
        table_name="grai_eval_results",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_grai_eval_results_eval_prompt_case_assertion",
        "grai_eval_results",
        ["eval_run_id", "prompt_id", "case_id", "assertion_index"],
    )
    op.drop_column("grai_eval_results", "destination_index")

    op.drop_index(
        op.f("ix_grai_eval_run_destinations_transport_profile_id"),
        table_name="grai_eval_run_destinations",
    )
    op.drop_index(
        op.f("ix_grai_eval_run_destinations_tenant_id"),
        table_name="grai_eval_run_destinations",
    )
    op.drop_index(
        op.f("ix_grai_eval_run_destinations_eval_run_id"),
        table_name="grai_eval_run_destinations",
    )
    op.drop_index("ix_grai_eval_run_destinations_tenant_run", table_name="grai_eval_run_destinations")
    op.drop_table("grai_eval_run_destinations")
