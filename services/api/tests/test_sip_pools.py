from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

import jwt

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import SIPTrunkRow, TenantTrunkPoolRow, TrunkPoolMemberRow, TrunkPoolRow


def _auth_headers(role: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": f"{role}-sip-pools-user",
            "tenant_id": settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "amr": ["pwd", "dev_token"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _editor_headers() -> dict[str, str]:
    return _auth_headers("editor")


def _operator_headers() -> dict[str, str]:
    return _auth_headers("operator")


def _viewer_headers() -> dict[str, str]:
    return _auth_headers("viewer")


async def _seed_tenant_pool(*, trunk_pool_id: str = "pool_default") -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            SIPTrunkRow(
                trunk_id="trunk-default-1",
                name="Default Trunk",
                provider_name="Twilio",
                address="sip.twilio.example.com",
                transport="udp",
                numbers=["+15550001111"],
                metadata_json={},
                is_active=True,
                last_synced_at=datetime.now(UTC),
            )
        )
        session.add(
            TrunkPoolRow(
                trunk_pool_id=trunk_pool_id,
                provider_name="Twilio",
                name="Default Pool",
                selection_policy="first_available",
                is_active=True,
            )
        )
        session.add(
            TrunkPoolMemberRow(
                trunk_pool_member_id="member_default_1",
                trunk_pool_id=trunk_pool_id,
                trunk_id="trunk-default-1",
                priority=10,
                is_active=True,
            )
        )
        session.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id="tenant_pool_default",
                tenant_id=settings.tenant_id,
                trunk_pool_id=trunk_pool_id,
                tenant_label="Tenant Label",
                is_default=True,
                is_active=True,
                max_channels=12,
                reserved_channels=3,
            )
        )
        await session.commit()


async def test_list_tenant_sip_pools_and_patch_label(client):
    await _seed_tenant_pool()

    list_resp = await client.get("/sip/pools", headers=_operator_headers())
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["tenant_label"] == "Tenant Label"
    assert payload["items"][0]["member_count"] == 1
    assert payload["items"][0]["max_channels"] == 12
    assert payload["items"][0]["reserved_channels"] == 3

    patch_resp = await client.patch(
        "/sip/pools/pool_default",
        json={"tenant_label": "Renamed Pool", "is_default": True},
        headers=_editor_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["tenant_label"] == "Renamed Pool"
    assert patch_resp.json()["max_channels"] == 12
    assert patch_resp.json()["reserved_channels"] == 3

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = (
            await session.execute(
                select(TenantTrunkPoolRow).where(TenantTrunkPoolRow.trunk_pool_id == "pool_default")
            )
        ).scalar_one()
        assert row.tenant_label == "Renamed Pool"


async def test_list_tenant_sip_pools_null_quota(client):
    """Pool assigned with no quota returns null for both channel fields."""
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            TrunkPoolRow(
                trunk_pool_id="pool_no_quota",
                provider_name="Twilio",
                name="No Quota Pool",
                selection_policy="first_available",
                is_active=True,
            )
        )
        session.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id="tenant_pool_no_quota",
                tenant_id=settings.tenant_id,
                trunk_pool_id="pool_no_quota",
                tenant_label="No Quota",
                is_default=False,
                is_active=True,
                max_channels=None,
                reserved_channels=None,
            )
        )
        await session.commit()

    resp = await client.get("/sip/pools", headers=_operator_headers())
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["trunk_pool_id"] == "pool_no_quota")
    assert item["max_channels"] is None
    assert item["reserved_channels"] is None


async def test_list_tenant_sip_pools_partial_quota(client):
    """Pool with only max_channels set returns null for reserved_channels."""
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            TrunkPoolRow(
                trunk_pool_id="pool_partial_quota",
                provider_name="Twilio",
                name="Partial Quota Pool",
                selection_policy="first_available",
                is_active=True,
            )
        )
        session.add(
            TenantTrunkPoolRow(
                tenant_trunk_pool_id="tenant_pool_partial_quota",
                tenant_id=settings.tenant_id,
                trunk_pool_id="pool_partial_quota",
                tenant_label="Partial Quota",
                is_default=False,
                is_active=True,
                max_channels=8,
                reserved_channels=None,
            )
        )
        await session.commit()

    resp = await client.get("/sip/pools", headers=_operator_headers())
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["trunk_pool_id"] == "pool_partial_quota")
    assert item["max_channels"] == 8
    assert item["reserved_channels"] is None


async def test_sip_pools_list_requires_operator_or_above(client):
    resp = await client.get("/sip/pools", headers=_viewer_headers())
    assert resp.status_code == 403


async def test_sip_pools_patch_requires_editor_or_above(client):
    await _seed_tenant_pool(trunk_pool_id="pool_patch_editor")

    resp = await client.patch(
        "/sip/pools/pool_patch_editor",
        json={"tenant_label": "Operator Should Not Edit"},
        headers=_operator_headers(),
    )
    assert resp.status_code == 403
