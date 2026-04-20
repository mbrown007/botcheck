from __future__ import annotations

from jose import jwt
from sqlalchemy import select

from botcheck_api import database
from botcheck_api.auth import pwd_context
from botcheck_api.config import settings
from botcheck_api.models import UserRow

from auth_login_test_helpers import _get_seed_user, _set_seed_tenant_state
from factories import make_login_payload


class TestAuthPasswords:

    async def test_login_success_returns_jwt(self, client):
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["requires_totp"] is False
        assert payload["token_type"] == "bearer"
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["tenant_name"] == settings.tenant_name
        assert payload["role"] == "admin"
        assert isinstance(payload["access_token"], str)
        assert payload["access_token"]
        assert isinstance(payload["refresh_token"], str)
        assert payload["refresh_token"]
        assert payload["refresh_expires_in_s"] > 0

    async def test_login_returns_db_tenant_display_name(self, client):
        await _set_seed_tenant_state(display_name="Acme Support")

        resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )

        assert resp.status_code == 200
        assert resp.json()["tenant_name"] == "Acme Support"

    async def test_login_invalid_password_returns_401(self, client):
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(password="wrong-password"),
        )
        assert resp.status_code == 401
        user = await _get_seed_user()
        assert user.failed_login_attempts == 1

    async def test_login_invalid_email_returns_401(self, client):
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(
                email="other@botcheck.local",
            ),
        )
        assert resp.status_code == 401

    async def test_login_normalizes_email_whitespace_and_case(self, client):
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(email="  ADMIN@BOTCHECK.LOCAL  "),
        )
        assert resp.status_code == 200

    async def test_auth_me_success(self, client):
        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        me_resp = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        payload = me_resp.json()
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["role"] == "admin"
        assert payload["amr"] == ["pwd"]

    async def test_auth_me_invalid_token_returns_401(self, client):
        resp = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer definitely-invalid"},
        )
        assert resp.status_code == 401

    async def test_login_disabled_returns_403(self, client, monkeypatch):
        monkeypatch.setattr(settings, "local_auth_enabled", False)
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert resp.status_code == 403

    async def test_login_uses_password_hash_from_db(self, client):
        new_password = "phase6-db-hash-password"
        factory = database.AsyncSessionLocal
        assert factory is not None
        async with factory() as session:
            result = await session.execute(
                select(UserRow).where(
                    UserRow.tenant_id == settings.tenant_id,
                    UserRow.email == settings.local_auth_email,
                )
            )
            user = result.scalar_one()
            user.password_hash = pwd_context.hash(new_password)
            await session.commit()

        resp = await client.post(
            "/auth/login",
            json=make_login_payload(password=new_password),
        )
        assert resp.status_code == 200

    async def test_login_tenant_mismatch_returns_403(self, client):
        resp = await client.post(
            "/auth/login",
            json=make_login_payload(tenant_id="wrong-tenant"),
        )
        assert resp.status_code == 403

    async def test_login_suspended_tenant_returns_403(self, client):
        await _set_seed_tenant_state(suspended=True)

        resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Tenant suspended"

    async def test_auth_me_rejects_wrong_issuer(self, client):
        wrong_iss_token = jwt.encode(
            {
                "sub": "user@example.com",
                "tenant_id": settings.tenant_id,
                "role": "admin",
                "iss": "not-botcheck",
                "amr": ["pwd"],
            },
            settings.secret_key,
            algorithm=settings.auth_algorithm,
        )
        resp = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {wrong_iss_token}"},
        )
        assert resp.status_code == 401

    async def test_auth_me_rejects_dev_token_in_production_mode(self, client, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        resp = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {settings.dev_user_token}"},
        )
        assert resp.status_code == 401
