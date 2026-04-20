from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.config import settings
from botcheck_api.models import AuditLogRow, SIPTrunkRow
from botcheck_api.packs.service_models import StoredSIPTrunk


def _platform_admin_headers() -> dict[str, str]:
    token = issue_user_token(
        UserContext(
            sub="user_test_admin",
            tenant_id=settings.tenant_id,
            role="system_admin",
            amr=("pwd",),
        )
    )
    return {"Authorization": f"Bearer {token}"}


def _admin_headers() -> dict[str, str]:
    token = issue_user_token(
        UserContext(
            sub="user_test_admin",
            tenant_id=settings.tenant_id,
            role="admin",
            amr=("pwd",),
        )
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_sip_trunk(*, trunk_id: str = "trunk-1") -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            SIPTrunkRow(
                trunk_id=trunk_id,
                name="Acme Trunk",
                provider_name="Twilio",
                address="sip.twilio.example.com",
                transport="udp",
                numbers=["+15550001111"],
                metadata_json={"region": "us-east-1"},
                is_active=True,
                last_synced_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def test_admin_sip_requires_platform_admin(client):
    resp = await client.get("/admin/sip/trunks", headers=_admin_headers())
    assert resp.status_code == 403


async def test_admin_sip_list_and_detail(client):
    await _seed_sip_trunk()

    list_resp = await client.get("/admin/sip/trunks", headers=_platform_admin_headers())
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["trunk_id"] == "trunk-1"

    detail_resp = await client.get(
        "/admin/sip/trunks/trunk-1",
        headers=_platform_admin_headers(),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["provider_name"] == "Twilio"


@patch("botcheck_api.admin.router_sip.sync_sip_trunks", new_callable=AsyncMock)
async def test_admin_sip_sync_route_wraps_service_and_writes_audit(mock_sync, client):
    mock_sync.return_value = [
        StoredSIPTrunk(
            trunk_id="trunk-sync",
            name="Synced Trunk",
            provider_name="LiveKit",
            address="sip.livekit.example.com",
            transport="tcp",
            numbers=["+15550002222"],
            metadata_json={},
            is_active=True,
            last_synced_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    ]

    resp = await client.post("/admin/sip/trunks/sync", headers=_platform_admin_headers())

    assert resp.status_code == 200
    assert resp.json() == {"synced": True, "total": 1, "active": 1}
    assert mock_sync.await_count == 1

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        audit = (
            await session.execute(
                select(AuditLogRow).where(AuditLogRow.action == "admin.sip.sync")
            )
        ).scalar_one()
        assert audit.resource_type == "sip_trunk_registry"


async def test_admin_sip_pool_lifecycle(client):
    await _seed_sip_trunk(trunk_id="trunk-pool-1")

    create_resp = await client.post(
        "/admin/sip/pools",
        json={"name": "UK Pool", "provider_name": "Twilio"},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201
    pool = create_resp.json()
    pool_id = pool["trunk_pool_id"]
    assert pool["name"] == "UK Pool"
    assert pool["provider_name"] == "Twilio"
    assert pool["members"] == []

    add_member = await client.post(
        f"/admin/sip/pools/{pool_id}/members",
        json={"trunk_id": "trunk-pool-1", "priority": 10},
        headers=_platform_admin_headers(),
    )
    assert add_member.status_code == 200
    assert add_member.json()["members"][0]["trunk_id"] == "trunk-pool-1"

    assign_resp = await client.post(
        f"/admin/sip/pools/{pool_id}/assign",
        json={
            "tenant_id": settings.tenant_id,
            "tenant_label": "UK Friendly",
            "is_default": True,
            "max_channels": 24,
            "reserved_channels": 6,
        },
        headers=_platform_admin_headers(),
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["assignments"][0]["tenant_label"] == "UK Friendly"
    assert assign_resp.json()["assignments"][0]["max_channels"] == 24
    assert assign_resp.json()["assignments"][0]["reserved_channels"] == 6

    patch_assignment_resp = await client.patch(
        f"/admin/sip/pools/{pool_id}/assign/{settings.tenant_id}",
        json={"tenant_label": "UK Priority", "reserved_channels": 8, "is_active": False},
        headers=_platform_admin_headers(),
    )
    assert patch_assignment_resp.status_code == 200
    assert patch_assignment_resp.json()["assignments"][0]["tenant_label"] == "UK Priority"
    assert patch_assignment_resp.json()["assignments"][0]["max_channels"] == 24
    assert patch_assignment_resp.json()["assignments"][0]["reserved_channels"] == 8
    assert patch_assignment_resp.json()["assignments"][0]["is_active"] is False

    list_resp = await client.get("/admin/sip/pools", headers=_platform_admin_headers())
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    patch_resp = await client.patch(
        f"/admin/sip/pools/{pool_id}",
        json={"name": "UK Pool Updated"},
        headers=_platform_admin_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "UK Pool Updated"

    revoke_resp = await client.delete(
        f"/admin/sip/pools/{pool_id}/assign/{settings.tenant_id}",
        headers=_platform_admin_headers(),
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["assignments"] == []

    remove_member = await client.delete(
        f"/admin/sip/pools/{pool_id}/members/trunk-pool-1",
        headers=_platform_admin_headers(),
    )
    assert remove_member.status_code == 200
    assert remove_member.json()["members"] == []


async def test_admin_sip_pool_assignment_rejects_reserved_channels_above_max(client):
    await _seed_sip_trunk(trunk_id="trunk-pool-invalid")

    create_resp = await client.post(
        "/admin/sip/pools",
        json={"name": "Quota Pool", "provider_name": "Twilio"},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201
    pool_id = create_resp.json()["trunk_pool_id"]

    assign_resp = await client.post(
        f"/admin/sip/pools/{pool_id}/assign",
        json={
            "tenant_id": settings.tenant_id,
            "max_channels": 4,
            "reserved_channels": 8,
        },
        headers=_platform_admin_headers(),
    )
    assert assign_resp.status_code == 422
    assert (
        assign_resp.json()["detail"][0]["msg"]
        == "Value error, reserved_channels must be less than or equal to max_channels"
    )


async def test_admin_sip_pool_assignment_patch_rejects_reserved_above_existing_max(client):
    """PATCH reserved_channels alone must validate against the existing max_channels."""
    await _seed_sip_trunk(trunk_id="trunk-patch-xfield")
    create_resp = await client.post(
        "/admin/sip/pools",
        json={"name": "Cross-field pool", "provider_name": "Twilio"},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201
    pool_id = create_resp.json()["trunk_pool_id"]

    await client.post(
        f"/admin/sip/pools/{pool_id}/assign",
        json={"tenant_id": settings.tenant_id, "max_channels": 10, "reserved_channels": 2},
        headers=_platform_admin_headers(),
    )

    patch_resp = await client.patch(
        f"/admin/sip/pools/{pool_id}/assign/{settings.tenant_id}",
        json={"reserved_channels": 15},
        headers=_platform_admin_headers(),
    )
    assert patch_resp.status_code == 422


async def test_admin_sip_pool_assignment_is_default_cleared_on_second_assignment(client):
    """Setting is_default on a second pool must clear it on the first."""
    await _seed_sip_trunk(trunk_id="trunk-default-a")
    await _seed_sip_trunk(trunk_id="trunk-default-b")

    pool_a = (await client.post(
        "/admin/sip/pools",
        json={"name": "Default Pool A", "provider_name": "Twilio"},
        headers=_platform_admin_headers(),
    )).json()["trunk_pool_id"]

    pool_b = (await client.post(
        "/admin/sip/pools",
        json={"name": "Default Pool B", "provider_name": "Twilio"},
        headers=_platform_admin_headers(),
    )).json()["trunk_pool_id"]

    await client.post(
        f"/admin/sip/pools/{pool_a}/assign",
        json={"tenant_id": settings.tenant_id, "is_default": True},
        headers=_platform_admin_headers(),
    )
    await client.post(
        f"/admin/sip/pools/{pool_b}/assign",
        json={"tenant_id": settings.tenant_id, "is_default": True},
        headers=_platform_admin_headers(),
    )

    list_resp = await client.get("/admin/sip/pools", headers=_platform_admin_headers())
    pools_by_id = {p["trunk_pool_id"]: p for p in list_resp.json()["items"]}
    a_assignment = next(
        (a for a in pools_by_id[pool_a]["assignments"] if a["tenant_id"] == settings.tenant_id), None
    )
    b_assignment = next(
        (a for a in pools_by_id[pool_b]["assignments"] if a["tenant_id"] == settings.tenant_id), None
    )
    assert a_assignment is not None
    assert b_assignment is not None
    assert a_assignment["is_default"] is False
    assert b_assignment["is_default"] is True


async def test_admin_sip_pool_routes_require_platform_admin(client):
    resp = await client.get("/admin/sip/pools", headers=_admin_headers())
    assert resp.status_code == 403
