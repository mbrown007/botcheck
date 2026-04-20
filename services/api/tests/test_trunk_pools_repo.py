from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import (
    SIPTrunkRow,
    TenantTrunkPoolRow,
    TrunkPoolMemberRow,
    TrunkPoolRow,
)


async def test_trunk_pool_tables_persist_membership_and_tenant_assignment() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        session.add(
            SIPTrunkRow(
                trunk_id="trunk_lk_1",
                name="Carrier A UK 1",
                provider_name="carrier-a",
                address="carrier-a.example.com",
                transport="tcp",
                numbers=["+441234567890"],
                metadata_json={},
                is_active=True,
                last_synced_at=datetime.now(UTC),
            )
        )
        session.add(
            TrunkPoolRow(
                trunk_pool_id="pool_outbound_uk",
                provider_name="carrier-a",
                name="uk-outbound",
                selection_policy="first_available",
                is_active=True,
            )
        )
        session.add(
            TrunkPoolMemberRow(
                trunk_pool_member_id="member_1",
                trunk_pool_id="pool_outbound_uk",
                trunk_id="trunk_lk_1",
                priority=10,
                is_active=True,
            )
        )
        session.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id="tenant_pool_1",
                tenant_id=settings.tenant_id,
                trunk_pool_id="pool_outbound_uk",
                tenant_label="UK Test Carrier",
                is_default=True,
                is_active=True,
                max_channels=12,
                reserved_channels=3,
            )
        )
        await session.commit()

    async with factory() as session:
        trunk_pool = await session.scalar(
            select(TrunkPoolRow).where(TrunkPoolRow.trunk_pool_id == "pool_outbound_uk")
        )
        assert trunk_pool is not None
        assert trunk_pool.provider_name == "carrier-a"

        member = await session.scalar(
            select(TrunkPoolMemberRow).where(
                TrunkPoolMemberRow.trunk_pool_member_id == "member_1"
            )
        )
        assert member is not None
        assert member.trunk_id == "trunk_lk_1"
        assert member.priority == 10

        tenant_assignment = await session.scalar(
            select(TenantTrunkPoolRow).where(
                TenantTrunkPoolRow.tenant_trunk_pool_id == "tenant_pool_1"
            )
        )
        assert tenant_assignment is not None
        assert tenant_assignment.trunk_pool_id == "pool_outbound_uk"
        assert tenant_assignment.tenant_label == "UK Test Carrier"
        assert tenant_assignment.max_channels == 12
        assert tenant_assignment.reserved_channels == 3
