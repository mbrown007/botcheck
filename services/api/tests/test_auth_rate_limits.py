from __future__ import annotations

from botcheck_api.config import settings

from auth_login_test_helpers import _get_seed_user
from factories import make_login_payload


class TestAuthRateLimits:

    async def test_login_rate_limit_returns_429(self, client, monkeypatch):
        monkeypatch.setattr(settings, "local_auth_rate_limit_attempts", 2)
        monkeypatch.setattr(settings, "local_auth_rate_limit_window_s", 60)

        for _ in range(2):
            resp = await client.post(
                "/auth/login",
                json=make_login_payload(password="wrong-password"),
            )
            assert resp.status_code == 401

        blocked = await client.post(
            "/auth/login",
            json=make_login_payload(password="wrong-password"),
        )
        assert blocked.status_code == 429

    async def test_login_applies_lockout_after_threshold(self, client, monkeypatch):
        monkeypatch.setattr(settings, "local_auth_lockout_failed_attempts", 2)
        monkeypatch.setattr(settings, "local_auth_lockout_duration_s", 600)

        first = await client.post(
            "/auth/login",
            json=make_login_payload(password="wrong-password"),
        )
        assert first.status_code == 401

        second = await client.post(
            "/auth/login",
            json=make_login_payload(password="wrong-password"),
        )
        assert second.status_code == 401

        user = await _get_seed_user()
        assert user.locked_until is not None

        blocked = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert blocked.status_code == 401
