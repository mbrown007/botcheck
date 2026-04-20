"""add provider registry

Revision ID: 0051_provider_registry
Revises: 0050_grai_eval_run_destinations
Create Date: 2026-03-17 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0051_provider_registry"
down_revision = "0050_grai_eval_run_destinations"
branch_labels = None
depends_on = None


_PROVIDER_SEED_ROWS = (
    {
        "provider_id": "openai:gpt-4o-mini-tts",
        "vendor": "openai",
        "model": "gpt-4o-mini-tts",
        "capability": "tts",
        "runtime_scopes": ["api", "agent"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "elevenlabs:eleven_flash_v2_5",
        "vendor": "elevenlabs",
        "model": "eleven_flash_v2_5",
        "capability": "tts",
        "runtime_scopes": ["api", "agent"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "deepgram:nova-2-general",
        "vendor": "deepgram",
        "model": "nova-2-general",
        "capability": "stt",
        "runtime_scopes": ["agent"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "azure:azure-speech",
        "vendor": "azure",
        "model": "azure-speech",
        "capability": "stt",
        "runtime_scopes": ["api", "agent"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "anthropic:claude-sonnet-4-6",
        "vendor": "anthropic",
        "model": "claude-sonnet-4-6",
        "capability": "judge",
        "runtime_scopes": ["judge"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "anthropic:claude-sonnet-4-5-20251001",
        "vendor": "anthropic",
        "model": "claude-sonnet-4-5-20251001",
        "capability": "llm",
        "runtime_scopes": ["api"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "openai:gpt-4o",
        "vendor": "openai",
        "model": "gpt-4o",
        "capability": "judge",
        "runtime_scopes": ["api"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
    {
        "provider_id": "openai:gpt-4o-mini",
        "vendor": "openai",
        "model": "gpt-4o-mini",
        "capability": "llm",
        "runtime_scopes": ["api"],
        "supports_tenant_credentials": False,
        "supports_platform_credentials": True,
    },
)


def upgrade() -> None:
    op.create_table(
        "provider_catalog",
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("vendor", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("runtime_scopes", sa.JSON(), nullable=False),
        sa.Column("supports_tenant_credentials", sa.Boolean(), nullable=False),
        sa.Column("supports_platform_credentials", sa.Boolean(), nullable=False),
        sa.Column("cost_per_input_token_microcents", sa.Integer(), nullable=True),
        sa.Column("cost_per_output_token_microcents", sa.Integer(), nullable=True),
        sa.Column("cost_per_audio_second_microcents", sa.Integer(), nullable=True),
        sa.Column("cost_per_character_microcents", sa.Integer(), nullable=True),
        sa.Column("cost_per_request_microcents", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    op.create_index(op.f("ix_provider_catalog_vendor"), "provider_catalog", ["vendor"], unique=False)
    op.create_index(
        op.f("ix_provider_catalog_capability"),
        "provider_catalog",
        ["capability"],
        unique=False,
    )

    op.create_table(
        "provider_credentials",
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("owner_scope", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("credential_source", sa.String(length=32), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("external_secret_ref", sa.String(length=255), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_catalog.provider_id"]),
        sa.PrimaryKeyConstraint("credential_id"),
        sa.UniqueConstraint(
            "owner_scope",
            "tenant_id",
            "provider_id",
            name="uq_provider_credentials_owner_tenant_provider",
        ),
    )
    op.create_index(
        op.f("ix_provider_credentials_owner_scope"),
        "provider_credentials",
        ["owner_scope"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_credentials_tenant_id"),
        "provider_credentials",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_credentials_provider_id"),
        "provider_credentials",
        ["provider_id"],
        unique=False,
    )

    op.create_table(
        "tenant_provider_assignments",
        sa.Column("assignment_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("effective_credential_source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_catalog.provider_id"]),
        sa.PrimaryKeyConstraint("assignment_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            name="uq_tenant_provider_assignments_tenant_provider",
        ),
    )
    op.create_index(
        op.f("ix_tenant_provider_assignments_tenant_id"),
        "tenant_provider_assignments",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_provider_assignments_provider_id"),
        "tenant_provider_assignments",
        ["provider_id"],
        unique=False,
    )

    op.create_table(
        "provider_quota_policies",
        sa.Column("quota_policy_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("limit_per_day", sa.Integer(), nullable=False),
        sa.Column("soft_limit_pct", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_catalog.provider_id"]),
        sa.PrimaryKeyConstraint("quota_policy_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "metric",
            name="uq_provider_quota_policies_tenant_provider_metric",
        ),
    )
    op.create_index(
        op.f("ix_provider_quota_policies_tenant_id"),
        "provider_quota_policies",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_quota_policies_provider_id"),
        "provider_quota_policies",
        ["provider_id"],
        unique=False,
    )

    op.create_table(
        "provider_usage_ledger",
        sa.Column("ledger_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_scope", sa.String(length=32), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("eval_run_id", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("audio_seconds", sa.Float(), nullable=False),
        sa.Column("characters", sa.Integer(), nullable=False),
        sa.Column("sip_minutes", sa.Float(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("calculated_cost_microcents", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_catalog.provider_id"]),
        sa.PrimaryKeyConstraint("ledger_id"),
    )
    op.create_index(
        "ix_provider_usage_ledger_tenant_provider_recorded_at",
        "provider_usage_ledger",
        ["tenant_id", "provider_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_usage_ledger_tenant_id"),
        "provider_usage_ledger",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_usage_ledger_provider_id"),
        "provider_usage_ledger",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_usage_ledger_run_id"),
        "provider_usage_ledger",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_usage_ledger_eval_run_id"),
        "provider_usage_ledger",
        ["eval_run_id"],
        unique=False,
    )

    provider_catalog = sa.table(
        "provider_catalog",
        sa.column("provider_id", sa.String(length=128)),
        sa.column("vendor", sa.String(length=64)),
        sa.column("model", sa.String(length=128)),
        sa.column("capability", sa.String(length=32)),
        sa.column("runtime_scopes", sa.JSON()),
        sa.column("supports_tenant_credentials", sa.Boolean()),
        sa.column("supports_platform_credentials", sa.Boolean()),
        sa.column("cost_per_input_token_microcents", sa.Integer()),
        sa.column("cost_per_output_token_microcents", sa.Integer()),
        sa.column("cost_per_audio_second_microcents", sa.Integer()),
        sa.column("cost_per_character_microcents", sa.Integer()),
        sa.column("cost_per_request_microcents", sa.Integer()),
    )
    op.bulk_insert(provider_catalog, list(_PROVIDER_SEED_ROWS))

    bind = op.get_bind()
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT tenant_id FROM tenants WHERE deleted_at IS NULL"))]
    now = datetime.now(timezone.utc)
    tenant_provider_assignments = sa.table(
        "tenant_provider_assignments",
        sa.column("assignment_id", sa.String(length=64)),
        sa.column("tenant_id", sa.String(length=255)),
        sa.column("provider_id", sa.String(length=128)),
        sa.column("enabled", sa.Boolean()),
        sa.column("is_default", sa.Boolean()),
        sa.column("effective_credential_source", sa.String(length=32)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    assignment_rows = []
    for tenant_id in tenant_ids:
        for provider_row in _PROVIDER_SEED_ROWS:
            assignment_rows.append(
                {
                    "assignment_id": f"provassign_{uuid.uuid4().hex}",
                    "tenant_id": tenant_id,
                    "provider_id": provider_row["provider_id"],
                    "enabled": True,
                    "is_default": False,
                    "effective_credential_source": "env",
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if assignment_rows:
        op.bulk_insert(tenant_provider_assignments, assignment_rows)


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_usage_ledger_eval_run_id"), table_name="provider_usage_ledger")
    op.drop_index(op.f("ix_provider_usage_ledger_run_id"), table_name="provider_usage_ledger")
    op.drop_index(op.f("ix_provider_usage_ledger_provider_id"), table_name="provider_usage_ledger")
    op.drop_index(op.f("ix_provider_usage_ledger_tenant_id"), table_name="provider_usage_ledger")
    op.drop_index("ix_provider_usage_ledger_tenant_provider_recorded_at", table_name="provider_usage_ledger")
    op.drop_table("provider_usage_ledger")

    op.drop_index(op.f("ix_provider_quota_policies_provider_id"), table_name="provider_quota_policies")
    op.drop_index(op.f("ix_provider_quota_policies_tenant_id"), table_name="provider_quota_policies")
    op.drop_table("provider_quota_policies")

    op.drop_index(
        op.f("ix_tenant_provider_assignments_provider_id"),
        table_name="tenant_provider_assignments",
    )
    op.drop_index(
        op.f("ix_tenant_provider_assignments_tenant_id"),
        table_name="tenant_provider_assignments",
    )
    op.drop_table("tenant_provider_assignments")

    op.drop_index(op.f("ix_provider_credentials_provider_id"), table_name="provider_credentials")
    op.drop_index(op.f("ix_provider_credentials_tenant_id"), table_name="provider_credentials")
    op.drop_index(op.f("ix_provider_credentials_owner_scope"), table_name="provider_credentials")
    op.drop_table("provider_credentials")

    op.drop_index(op.f("ix_provider_catalog_capability"), table_name="provider_catalog")
    op.drop_index(op.f("ix_provider_catalog_vendor"), table_name="provider_catalog")
    op.drop_table("provider_catalog")
