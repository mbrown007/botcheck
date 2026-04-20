from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from jose import jwt

from botcheck_api import auth
from botcheck_api.auth import LocalAuthProvider, UserContext
from botcheck_api.config import settings


@dataclass
class _StubProvider:
    authenticate_calls: int = 0
    issue_calls: int = 0
    verify_calls: int = 0

    def authenticate(self, email: str, password: str) -> UserContext | None:
        self.authenticate_calls += 1
        if email == "user@example.com" and password == "ok":
            return UserContext(sub="user-1", tenant_id="default", role="admin")
        return None

    def verify_password_hash(self, password: str, password_hash: str) -> bool:
        return password == password_hash

    def issue_token(
        self,
        user: UserContext,
        *,
        amr: tuple[str, ...] | list[str] | None = None,
        session_id: str | None = None,
    ) -> str:
        del user, amr, session_id
        self.issue_calls += 1
        return "stub-token"

    def verify_token(self, token: str) -> UserContext:
        self.verify_calls += 1
        if token != "stub-token":
            raise HTTPException(status_code=401, detail="invalid")
        return UserContext(sub="user-1", tenant_id="default", role="admin")


def test_local_auth_provider_authenticate_contract(monkeypatch):
    provider = LocalAuthProvider()
    monkeypatch.setattr(settings, "local_auth_enabled", True)
    monkeypatch.setattr(settings, "local_auth_email", "admin@botcheck.local")
    monkeypatch.setattr(settings, "local_auth_password", "botcheck-dev-password")
    monkeypatch.setattr(settings, "local_auth_password_hash", "")
    monkeypatch.setattr(settings, "environment", "development")

    user = provider.authenticate("ADMIN@botcheck.local", "botcheck-dev-password")
    assert user is not None
    assert user.sub == "admin@botcheck.local"
    assert user.tenant_id == settings.tenant_id
    assert user.role == "admin"
    assert user.amr == ("pwd",)

    assert provider.authenticate("admin@botcheck.local", "wrong-password") is None
    assert provider.authenticate("other@botcheck.local", "botcheck-dev-password") is None


def test_local_auth_provider_issue_and_verify_token_contract(monkeypatch):
    provider = LocalAuthProvider()
    monkeypatch.setattr(settings, "secret_key", "phase6-test-secret")
    monkeypatch.setattr(settings, "auth_issuer", "botcheck-local-auth")
    monkeypatch.setattr(settings, "auth_algorithm", "HS256")
    monkeypatch.setattr(settings, "local_auth_token_ttl_s", 900)

    token = provider.issue_token(
        UserContext(sub="user-1", tenant_id="default", role="admin"),
        amr=("pwd", "totp"),
        session_id="sess_123",
    )
    decoded = provider.verify_token(token)

    assert decoded.sub == "user-1"
    assert decoded.tenant_id == "default"
    assert decoded.role == "admin"
    assert decoded.amr == ("pwd", "totp")
    assert decoded.session_id == "sess_123"


def test_local_auth_provider_verify_token_rejects_wrong_issuer(monkeypatch):
    provider = LocalAuthProvider()
    monkeypatch.setattr(settings, "secret_key", "phase6-test-secret")
    monkeypatch.setattr(settings, "auth_issuer", "botcheck-local-auth")
    monkeypatch.setattr(settings, "auth_algorithm", "HS256")

    wrong_issuer_token = jwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "default",
            "role": "admin",
            "iss": "not-botcheck",
            "amr": ["pwd"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )

    with pytest.raises(HTTPException) as exc_info:
        provider.verify_token(wrong_issuer_token)
    assert exc_info.value.status_code == 401


def test_auth_helpers_delegate_to_provider_contract():
    stub = _StubProvider()
    auth.set_auth_provider_for_tests(stub)
    try:
        user = auth.authenticate_local_user("user@example.com", "ok")
        assert user is not None
        assert stub.authenticate_calls == 1

        token = auth.issue_user_token(user)
        assert token == "stub-token"
        assert stub.issue_calls == 1

        decoded = auth._decode_user_token(token)
        assert decoded.sub == "user-1"
        assert stub.verify_calls == 1
    finally:
        auth.set_auth_provider_for_tests(None)
