from __future__ import annotations

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.config import settings
from botcheck_api.models import AuditLogRow, TenantRow


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


async def test_admin_tenants_requires_platform_admin(client):
    resp = await client.get("/admin/tenants/", headers=_admin_headers())
    assert resp.status_code == 403


async def test_admin_tenants_crud_and_audit(client):
    create_resp = await client.post(
        "/admin/tenants/",
        json={
            "tenant_id": "acme",
            "slug": "acme",
            "display_name": "Acme Corp",
            "feature_overrides": {
                "feature_packs_enabled": True,
                "feature_tts_provider_elevenlabs_enabled": True,
            },
            "quota_config": {
                "max_concurrent_runs": 3,
                "max_runs_per_day": 120,
                "max_schedules": 8,
                "max_scenarios": 25,
                "max_packs": 4,
            },
        },
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["tenant_id"] == "acme"
    assert created["slug"] == "acme"
    assert created["display_name"] == "Acme Corp"
    assert created["feature_overrides"]["feature_packs_enabled"] is True
    assert created["effective_quotas"]["max_concurrent_runs"] == 3

    list_resp = await client.get("/admin/tenants/", headers=_platform_admin_headers())
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 2
    assert any(item["tenant_id"] == "acme" for item in listed["items"])

    detail_resp = await client.get("/admin/tenants/acme", headers=_platform_admin_headers())
    assert detail_resp.status_code == 200
    assert detail_resp.json()["display_name"] == "Acme Corp"

    patch_resp = await client.patch(
        "/admin/tenants/acme",
        json={
            "display_name": "Acme Support",
            "feature_overrides": {"feature_ai_scenarios_enabled": True},
            "quota_config": {"max_scenarios": 10},
        },
        headers=_platform_admin_headers(),
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["display_name"] == "Acme Support"
    assert patched["feature_overrides"] == {"feature_ai_scenarios_enabled": True}
    assert patched["quota_config"] == {"max_scenarios": 10}
    assert patched["effective_quotas"]["max_scenarios"] == 10
    assert patched["effective_quotas"]["max_packs"] == 50

    suspend_resp = await client.post(
        "/admin/tenants/acme/suspend",
        headers=_platform_admin_headers(),
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["suspended_at"] is not None

    reinstate_resp = await client.post(
        "/admin/tenants/acme/reinstate",
        headers=_platform_admin_headers(),
    )
    assert reinstate_resp.status_code == 200
    assert reinstate_resp.json()["suspended_at"] is None

    delete_resp = await client.delete(
        "/admin/tenants/acme",
        headers=_platform_admin_headers(),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_at"] is not None

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        tenant = await session.get(TenantRow, "acme")
        assert tenant is not None
        assert tenant.deleted_at is not None
        audit_rows = (
            await session.execute(
                select(AuditLogRow).where(
                    AuditLogRow.tenant_id == "acme",
                    AuditLogRow.resource_type == "tenant",
                )
            )
        ).scalars().all()
        actions = {row.action for row in audit_rows}
        assert actions == {
            "admin.tenant.create",
            "admin.tenant.update",
            "admin.tenant.suspend",
            "admin.tenant.reinstate",
            "admin.tenant.delete",
        }


async def test_admin_tenants_missing_tenant_returns_problem(client):
    resp = await client.get("/admin/tenants/missing", headers=_platform_admin_headers())
    assert resp.status_code == 404
    payload = resp.json()
    assert payload["error_code"] == "tenant_not_found"
