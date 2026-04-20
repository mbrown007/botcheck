from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from botcheck_api import database, store_repo
from botcheck_api.config import settings
from botcheck_api.models import BotDestinationRow, DestinationProtocol


async def test_bot_destination_repo_crud_and_tenant_scoping() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    primary = BotDestinationRow(
        destination_id="dest_sip_1",
        tenant_id=settings.tenant_id,
        name="Staging SIP Trunk",
        protocol=DestinationProtocol.SIP.value,
        endpoint="sip:bot@trunk-a.example.com",
        caller_id="+15551234567",
        trunk_id="trunk-a",
        trunk_pool_id="pool_outbound_uk",
        headers={"X-Test": "1"},
        is_active=True,
        provisioned_channels=10,
        reserved_channels=2,
        botcheck_max_channels=6,
        capacity_scope="carrier-a",
    )
    secondary_tenant = BotDestinationRow(
        destination_id="dest_mock_other",
        tenant_id="tenant-other",
        name="Staging SIP Trunk",
        protocol=DestinationProtocol.MOCK.value,
        endpoint="mock://echo",
        headers={},
        is_active=True,
    )

    async with factory() as session:
        await store_repo.add_bot_destination_row(session, primary)
        await store_repo.add_bot_destination_row(session, secondary_tenant)
        await session.commit()

    async with factory() as session:
        fetched = await store_repo.get_bot_destination_row_for_tenant(
            session,
            destination_id="dest_sip_1",
            tenant_id=settings.tenant_id,
        )
        assert fetched is not None
        assert fetched.name == "Staging SIP Trunk"
        assert fetched.capacity_scope == "carrier-a"
        assert fetched.trunk_pool_id == "pool_outbound_uk"

        missing_cross_tenant = await store_repo.get_bot_destination_row_for_tenant(
            session,
            destination_id="dest_sip_1",
            tenant_id="tenant-other",
        )
        assert missing_cross_tenant is None

        by_name = await store_repo.get_bot_destination_row_by_name_for_tenant(
            session,
            tenant_id=settings.tenant_id,
            name="Staging SIP Trunk",
        )
        assert by_name is not None
        assert by_name.destination_id == "dest_sip_1"

        by_name_missing = await store_repo.get_bot_destination_row_by_name_for_tenant(
            session,
            tenant_id=settings.tenant_id,
            name="Does Not Exist",
        )
        assert by_name_missing is None

        by_name_cross_tenant = await store_repo.get_bot_destination_row_by_name_for_tenant(
            session,
            tenant_id="tenant-other",
            name="Staging SIP Trunk",
        )
        assert by_name_cross_tenant is not None
        assert by_name_cross_tenant.destination_id == "dest_mock_other"

        by_name_cross_tenant_missing = await store_repo.get_bot_destination_row_by_name_for_tenant(
            session,
            tenant_id="tenant-missing",
            name="Staging SIP Trunk",
        )
        assert by_name_cross_tenant_missing is None

        listed = await store_repo.list_bot_destination_rows_for_tenant(
            session,
            tenant_id=settings.tenant_id,
        )
        assert [row.destination_id for row in listed] == ["dest_sip_1"]

        assert (
            await store_repo.delete_bot_destination_row_for_tenant(
                session,
                destination_id="dest_sip_1",
                tenant_id="tenant-other",
            )
            is False
        )
        assert (
            await store_repo.delete_bot_destination_row_for_tenant(
                session,
                destination_id="dest_sip_1",
                tenant_id=settings.tenant_id,
            )
            is True
        )
        await session.commit()

        listed_after_delete = await store_repo.list_bot_destination_rows_for_tenant(
            session,
            tenant_id=settings.tenant_id,
        )
        assert listed_after_delete == []


async def test_bot_destination_repo_persists_direct_http_config() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    http_destination = BotDestinationRow(
        destination_id="dest_http_1",
        tenant_id=settings.tenant_id,
        name="Direct HTTP",
        protocol=DestinationProtocol.HTTP.value,
        endpoint="https://bot.internal/chat",
        headers={"Authorization": "Bearer test-token"},
        direct_http_config={
            "method": "POST",
            "request_content_type": "json",
            "request_text_field": "message",
            "response_text_field": "response",
            "timeout_s": 30,
        },
        is_active=True,
    )

    async with factory() as session:
        await store_repo.add_bot_destination_row(session, http_destination)
        await session.commit()

    async with factory() as session:
        fetched = await store_repo.get_bot_destination_row_for_tenant(
            session,
            destination_id="dest_http_1",
            tenant_id=settings.tenant_id,
        )
        assert fetched is not None
        assert fetched.protocol == DestinationProtocol.HTTP.value
        assert fetched.direct_http_config is not None
        assert fetched.direct_http_config["request_text_field"] == "message"
        assert fetched.direct_http_config["timeout_s"] == 30


async def test_bot_destination_db_constraints_reject_reserved_over_provisioned() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    invalid = BotDestinationRow(
        destination_id="dest_invalid_channels",
        tenant_id=settings.tenant_id,
        name="Invalid Channels",
        protocol=DestinationProtocol.SIP.value,
        endpoint="sip:bot@invalid.example.com",
        headers={},
        is_active=True,
        provisioned_channels=1,
        reserved_channels=2,
        capacity_scope="carrier-invalid",
    )

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await store_repo.add_bot_destination_row(session, invalid)
            await session.commit()
        await session.rollback()
