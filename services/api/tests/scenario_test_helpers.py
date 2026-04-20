"""Shared helpers for scenario-row test mutations."""

from __future__ import annotations

from botcheck_api import database
from botcheck_api.models import ScenarioRow


async def _set_scenario_kind(
    scenario_id: str,
    scenario_kind: str,
    *,
    tenant_id: str = "default",
) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(ScenarioRow, scenario_id)
        assert row is not None
        assert row.tenant_id == tenant_id
        row.scenario_kind = scenario_kind
        await db.commit()
