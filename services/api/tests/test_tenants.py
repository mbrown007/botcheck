"""Tests for /tenants routes."""

from unittest.mock import patch

from jose import jwt

from botcheck_api.config import settings
from auth_login_test_helpers import _set_seed_tenant_state


def _other_tenant_headers() -> dict[str, str]:
    token = jwt.encode(
        {"sub": "other-user", "tenant_id": "other-tenant", "role": "admin", "iss": settings.auth_issuer},
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _headers_for_role(role: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "user_test_admin",
            "tenant_id": settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


class TestTenants:
    async def test_get_current_tenant_includes_instance_timezone(
        self,
        client,
        user_auth_headers,
    ):
        resp = await client.get("/tenants/me", headers=user_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == settings.tenant_id
        assert data["instance_timezone"] == settings.instance_timezone
        assert data["default_retention_profile"] == settings.default_retention_profile
        assert data["redaction_enabled"] == settings.redaction_enabled
        assert data["tenant_context_locked"] is True
        assert data["tenant_switcher_enabled"] is False

    async def test_get_current_tenant_uses_db_display_name(self, client, user_auth_headers):
        await _set_seed_tenant_state(display_name="Acme Support")

        resp = await client.get("/tenants/me", headers=user_auth_headers)

        assert resp.status_code == 200
        assert resp.json()["name"] == "Acme Support"

    async def test_redaction_enabled_reflects_config(self, client, user_auth_headers):
        """redaction_enabled is read from settings, not hard-coded."""
        with patch.object(settings, "redaction_enabled", False):
            resp = await client.get("/tenants/me", headers=user_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["redaction_enabled"] is False

    async def test_get_current_tenant_rejects_cross_tenant_user(self, client):
        resp = await client.get("/tenants/me", headers=_other_tenant_headers())
        assert resp.status_code == 403

    async def test_get_current_tenant_rejects_suspended_tenant(self, client, user_auth_headers):
        await _set_seed_tenant_state(suspended=True)

        resp = await client.get("/tenants/me", headers=user_auth_headers)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Tenant suspended"

    async def test_get_current_tenant_rejects_deleted_tenant(self, client, user_auth_headers):
        await _set_seed_tenant_state(deleted=True)

        resp = await client.get("/tenants/me", headers=user_auth_headers)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Tenant deleted"

    async def test_tenant_switcher_enabled_only_for_allowed_role(self, client):
        with (
            patch.object(settings, "shared_instance_mode", True),
            patch.object(settings, "tenant_switcher_allowed_roles", ["admin"]),
        ):
            admin_resp = await client.get("/tenants/me", headers=_headers_for_role("admin"))
            viewer_resp = await client.get("/tenants/me", headers=_headers_for_role("viewer"))

        assert admin_resp.status_code == 200
        assert admin_resp.json()["tenant_context_locked"] is False
        assert admin_resp.json()["tenant_switcher_enabled"] is True

        assert viewer_resp.status_code == 200
        assert viewer_resp.json()["tenant_context_locked"] is False
        assert viewer_resp.json()["tenant_switcher_enabled"] is False
