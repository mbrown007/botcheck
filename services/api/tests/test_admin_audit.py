from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.config import settings
from botcheck_api.models import AuditLogRow


def _headers_for_role(role: str, *, tenant_id: str | None = None) -> dict[str, str]:
    token = issue_user_token(
        UserContext(
            sub="user_test_admin",
            tenant_id=tenant_id or settings.tenant_id,
            role=role,
            amr=("pwd",),
        )
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_audit_event(*, tenant_id: str, event_id: str, action: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            AuditLogRow(
                event_id=event_id,
                tenant_id=tenant_id,
                actor_id="seed-actor",
                actor_type="user",
                action=action,
                resource_type="scenario",
                resource_id="scen_1",
                detail={"seeded": True},
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def test_admin_audit_requires_admin(client):
    resp = await client.get("/admin/audit/", headers=_headers_for_role("viewer"))
    assert resp.status_code == 403


async def test_admin_audit_tenant_admin_sees_only_own_tenant(client):
    await _seed_audit_event(tenant_id=settings.tenant_id, event_id="evt_local", action="local.action")
    await _seed_audit_event(tenant_id="other-tenant", event_id="evt_other", action="other.action")

    resp = await client.get("/admin/audit/", headers=_headers_for_role("admin"))

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert all(item["tenant_id"] == settings.tenant_id for item in payload["items"])


async def test_admin_audit_tenant_admin_cannot_filter_other_tenant(client):
    resp = await client.get(
        "/admin/audit/?tenant_id=other-tenant",
        headers=_headers_for_role("admin"),
    )
    assert resp.status_code == 403


async def test_admin_audit_platform_admin_can_filter_other_tenant_and_get_detail(client):
    await _seed_audit_event(
        tenant_id="other-tenant",
        event_id="evt_platform_visible",
        action="tenant.suspended",
    )

    list_resp = await client.get(
        "/admin/audit/?tenant_id=other-tenant",
        headers=_headers_for_role("system_admin"),
    )
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_id"] == "evt_platform_visible"

    detail_resp = await client.get(
        "/admin/audit/evt_platform_visible",
        headers=_headers_for_role("system_admin"),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["tenant_id"] == "other-tenant"
