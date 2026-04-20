from __future__ import annotations

from datetime import UTC, datetime

import pytest

from botcheck_api import database
from botcheck_api.exceptions import ApiProblem
from botcheck_api.models import SIPTrunkRow, TenantTrunkPoolRow, TrunkPoolMemberRow, TrunkPoolRow
from botcheck_api.runs.service_trunk_pools import resolve_sip_trunk_for_dispatch


async def _seed_trunk_pool(
    *,
    trunk_pool_id: str = "pool_outbound_uk",
    tenant_id: str = "default",
    provider_name: str = "sipgate.co.uk",
    trunk_ids: list[tuple[str, int]] | None = None,
) -> None:
    if trunk_ids is None:
        trunk_ids = [("trunk-uk-2", 20), ("trunk-uk-1", 10)]
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        db.add(
            TrunkPoolRow(
                trunk_pool_id=trunk_pool_id,
                provider_name=provider_name,
                name="UK Outbound",
                selection_policy="first_available",
                is_active=True,
            )
        )
        db.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id=f"tenant_pool_{trunk_pool_id}",
                tenant_id=tenant_id,
                trunk_pool_id=trunk_pool_id,
                tenant_label="UK Testing",
                is_default=True,
                is_active=True,
            )
        )
        for index, (trunk_id, priority) in enumerate(trunk_ids, start=1):
            db.add(
                SIPTrunkRow(
                    trunk_id=trunk_id,
                    name=trunk_id,
                    provider_name=provider_name,
                    address=f"{provider_name}/{trunk_id}",
                    transport="SIP_TRANSPORT_AUTO",
                    numbers=[],
                    metadata_json={},
                    is_active=True,
                    last_synced_at=datetime.now(UTC),
                )
            )
            db.add(
                TrunkPoolMemberRow(
                    trunk_pool_member_id=f"member_{index}_{trunk_pool_id}",
                    trunk_pool_id=trunk_pool_id,
                    trunk_id=trunk_id,
                    priority=priority,
                    is_active=True,
                )
            )
        await db.commit()


async def test_resolve_sip_trunk_for_dispatch_selects_lowest_priority_active_member(db_setup):
    await _seed_trunk_pool()

    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        resolved = await resolve_sip_trunk_for_dispatch(
            db,
            tenant_id="default",
            trunk_id=None,
            trunk_pool_id="pool_outbound_uk",
        )

    assert resolved.trunk_pool_id == "pool_outbound_uk"
    assert resolved.trunk_id == "trunk-uk-1"


async def test_resolve_sip_trunk_for_dispatch_rejects_unassigned_pool(db_setup):
    await _seed_trunk_pool(tenant_id="other-tenant")

    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ApiProblem) as excinfo:
            await resolve_sip_trunk_for_dispatch(
                db,
                tenant_id="default",
                trunk_id=None,
                trunk_pool_id="pool_outbound_uk",
            )

    assert excinfo.value.error_code == "trunk_pool_unassigned"
