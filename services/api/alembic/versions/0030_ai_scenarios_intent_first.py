"""Promote AI scenario authoring fields to explicit columns.

Revision ID: 0030_ai_scenarios_intent_first
Revises: 0029_ai_scenarios_foundation
Create Date: 2026-03-06 13:30:00.000000
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_ai_scenarios_intent_first"
down_revision = "0029"
branch_labels = None
depends_on = None


def _read_config(config: Any) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    return {}


def upgrade() -> None:
    op.add_column(
        "ai_scenarios",
        sa.Column("ai_scenario_id", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column("scenario_brief", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column("scenario_facts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column("evaluation_objective", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column(
            "opening_strategy",
            sa.String(length=64),
            nullable=False,
            server_default="wait_for_bot_greeting",
        ),
    )
    op.add_column(
        "ai_scenarios",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    ai_scenarios = sa.Table("ai_scenarios", metadata, autoload_with=bind)
    scenarios = sa.Table("scenarios", metadata, autoload_with=bind)

    scenario_names = {
        str(row.scenario_id): str(row.name or row.scenario_id)
        for row in bind.execute(sa.select(scenarios.c.scenario_id, scenarios.c.name)).mappings()
    }

    rows = bind.execute(
        sa.select(
            ai_scenarios.c.scenario_id,
            ai_scenarios.c.config,
        )
    ).mappings()

    for row in rows:
        scenario_id = str(row["scenario_id"])
        config = _read_config(row.get("config"))
        scenario_facts = config.get("scenario_facts")
        if not isinstance(scenario_facts, dict):
            scenario_facts = {}
        opening_strategy = str(config.get("opening_strategy") or "wait_for_bot_greeting").strip()
        if opening_strategy not in {"wait_for_bot_greeting", "caller_opens"}:
            opening_strategy = "wait_for_bot_greeting"
        is_active_raw = config.get("is_active")
        is_active = bool(is_active_raw) if isinstance(is_active_raw, bool) else True
        bind.execute(
            ai_scenarios.update()
            .where(ai_scenarios.c.scenario_id == scenario_id)
            .values(
                ai_scenario_id=scenario_id,
                name=scenario_names.get(scenario_id, scenario_id),
                scenario_brief=str(config.get("scenario_brief") or "").strip(),
                scenario_facts=scenario_facts,
                evaluation_objective=str(config.get("evaluation_objective") or "").strip(),
                opening_strategy=opening_strategy,
                is_active=is_active,
            )
        )

    op.create_index(
        "ix_ai_scenarios_ai_scenario_id",
        "ai_scenarios",
        ["ai_scenario_id"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_ai_scenarios_opening_strategy",
        "ai_scenarios",
        "opening_strategy IN ('wait_for_bot_greeting', 'caller_opens')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_scenarios_opening_strategy", "ai_scenarios", type_="check")
    op.drop_index("ix_ai_scenarios_ai_scenario_id", table_name="ai_scenarios")
    op.drop_column("ai_scenarios", "is_active")
    op.drop_column("ai_scenarios", "opening_strategy")
    op.drop_column("ai_scenarios", "evaluation_objective")
    op.drop_column("ai_scenarios", "scenario_facts")
    op.drop_column("ai_scenarios", "scenario_brief")
    op.drop_column("ai_scenarios", "name")
    op.drop_column("ai_scenarios", "ai_scenario_id")
