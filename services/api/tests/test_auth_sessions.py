from __future__ import annotations

from jose import jwt

from botcheck_api.auth.security import consume_totp_counter_once
from botcheck_api.config import settings
from botcheck_api.auth.totp import (
    generate_totp_code,
    generate_totp_secret,
    resolve_totp_counter,
)

from auth_login_test_helpers import (
    _active_auth_sessions_for_seed_user,
    _active_recovery_rows,
    _configure_totp_for_seed_user,
    _get_seed_user,
    _login_headers_for_seed_user,
    _set_seed_tenant_state,
)
from factories import (
    make_login_payload,
    make_refresh_payload,
    make_totp_code_payload,
    make_totp_verify_payload,
)


class TestAuthSessions:

    async def test_totp_login_challenge_and_verify(self, client):
        secret = generate_totp_secret()
        await _configure_totp_for_seed_user(secret)

        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        login_payload = login_resp.json()
        assert login_payload["requires_totp"] is True
        challenge_token = login_payload["challenge_token"]
        assert challenge_token

        code = generate_totp_code(secret)
        verify_resp = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_token, code),
        )
        assert verify_resp.status_code == 200
        verify_payload = verify_resp.json()
        assert verify_payload["requires_totp"] is False
        assert verify_payload["access_token"]
        assert verify_payload["refresh_token"]
        assert verify_payload["refresh_expires_in_s"] > 0

    async def test_refresh_rotates_token_and_revokes_previous(self, client):
        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        login_payload = login_resp.json()
        refresh_token_1 = login_payload["refresh_token"]
        assert refresh_token_1

        refresh_resp = await client.post(
            "/auth/refresh",
            json=make_refresh_payload(refresh_token_1),
        )
        assert refresh_resp.status_code == 200
        refresh_payload = refresh_resp.json()
        refresh_token_2 = refresh_payload["refresh_token"]
        assert refresh_token_2
        assert refresh_token_2 != refresh_token_1
        assert refresh_payload["access_token"]

        stale_refresh = await client.post(
            "/auth/refresh",
            json=make_refresh_payload(refresh_token_1),
        )
        assert stale_refresh.status_code == 401

    async def test_refresh_rejects_suspended_tenant(self, client):
        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]
        assert refresh_token

        await _set_seed_tenant_state(suspended=True)

        refresh_resp = await client.post(
            "/auth/refresh",
            json=make_refresh_payload(refresh_token),
        )
        assert refresh_resp.status_code == 403
        assert refresh_resp.json()["detail"] == "Tenant suspended"

    async def test_logout_all_revokes_access_and_refresh_tokens(self, client):
        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        payload = login_resp.json()
        access_token = payload["access_token"]
        refresh_token = payload["refresh_token"]
        assert access_token
        assert refresh_token

        logout_resp = await client.post(
            "/auth/logout-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 200
        assert logout_resp.json()["revoked_sessions"] >= 1

        me_resp = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 401

        refresh_resp = await client.post(
            "/auth/refresh",
            json=make_refresh_payload(refresh_token),
        )
        assert refresh_resp.status_code == 401

        active_sessions = await _active_auth_sessions_for_seed_user()
        assert len(active_sessions) == 0

    async def test_totp_login_rejects_invalid_code(self, client):
        secret = generate_totp_secret()
        await _configure_totp_for_seed_user(secret)

        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        challenge_token = login_resp.json()["challenge_token"]

        verify_resp = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_token, "000000"),
        )
        assert verify_resp.status_code == 401
        user = await _get_seed_user()
        assert user.failed_login_attempts == 1

    async def test_totp_login_rejects_suspended_tenant_before_session_issue(self, client):
        secret = generate_totp_secret()
        await _configure_totp_for_seed_user(secret)

        login_resp = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp.status_code == 200
        challenge_token = login_resp.json()["challenge_token"]

        await _set_seed_tenant_state(suspended=True)

        verify_resp = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_token, generate_totp_code(secret)),
        )
        assert verify_resp.status_code == 403
        assert verify_resp.json()["detail"] == "Tenant suspended"

    async def test_totp_replay_code_is_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "auth_totp_step_s", 300)
        monkeypatch.setattr(settings, "auth_totp_window", 0)
        monkeypatch.setattr(settings, "auth_totp_replay_ttl_s", 600)
        secret = generate_totp_secret()
        await _configure_totp_for_seed_user(secret)

        login_resp_1 = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_1.status_code == 200
        challenge_1 = login_resp_1.json()["challenge_token"]
        code = generate_totp_code(secret, step_s=settings.auth_totp_step_s)
        verify_1 = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_1, code),
        )
        assert verify_1.status_code == 200

        login_resp_2 = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_2.status_code == 200
        challenge_2 = login_resp_2.json()["challenge_token"]
        verify_2 = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_2, code),
        )
        assert verify_2.status_code == 401

    async def test_totp_status_defaults_disabled(self, client):
        headers = await _login_headers_for_seed_user(client)
        resp = await client.get("/auth/totp/status", headers=headers)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["totp_enabled"] is False
        assert payload["enrollment_pending"] is False
        assert payload["recovery_codes_remaining"] == 0

    async def test_totp_enroll_start_returns_secret_and_persists_encrypted(self, client):
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200
        payload = start_resp.json()
        assert payload["secret"]
        assert payload["otpauth_uri"].startswith("otpauth://totp/")
        assert payload["otpauth_qr_data_url"].startswith("data:image/svg+xml;base64,")
        assert payload["issuer"]
        assert payload["account_name"]

        row = await _get_seed_user()
        assert row.totp_enabled is False
        assert row.totp_secret_encrypted is not None
        assert payload["secret"] not in row.totp_secret_encrypted

        status_resp = await client.get("/auth/totp/status", headers=headers)
        assert status_resp.status_code == 200
        status_payload = status_resp.json()
        assert status_payload["totp_enabled"] is False
        assert status_payload["enrollment_pending"] is True

    async def test_totp_enroll_start_uses_db_tenant_display_name_in_issuer(self, client):
        await _set_seed_tenant_state(display_name="Acme Support")
        headers = await _login_headers_for_seed_user(client)

        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)

        assert start_resp.status_code == 200
        payload = start_resp.json()
        assert payload["issuer"] == "BotCheck (Acme Support)"
        assert "BotCheck%20%28Acme%20Support%29" in payload["otpauth_uri"]

    async def test_totp_enroll_confirm_enables_totp(self, client, monkeypatch):
        monkeypatch.setattr(settings, "auth_totp_step_s", 300)
        monkeypatch.setattr(settings, "auth_totp_window", 0)
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200
        secret = start_resp.json()["secret"]
        code = generate_totp_code(secret, step_s=settings.auth_totp_step_s)

        confirm_resp = await client.post(
            "/auth/totp/enroll/confirm",
            headers=headers,
            json=make_totp_code_payload(code),
        )
        assert confirm_resp.status_code == 200
        confirm_payload = confirm_resp.json()
        assert confirm_payload["totp_enabled"] is True
        recovery_codes = confirm_payload["recovery_codes"]
        assert isinstance(recovery_codes, list)
        assert len(recovery_codes) == 10

        row = await _get_seed_user()
        assert row.totp_enabled is True
        assert row.failed_login_attempts == 0

        active_codes = await _active_recovery_rows()
        assert len(active_codes) == 10
        joined_hashes = "\n".join(item.code_hash for item in active_codes)
        for recovery_code in recovery_codes:
            assert recovery_code not in joined_hashes

        status_resp = await client.get("/auth/totp/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["recovery_codes_remaining"] == 10

    async def test_totp_enroll_confirm_rejects_invalid_code(self, client):
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200

        confirm_resp = await client.post(
            "/auth/totp/enroll/confirm",
            headers=headers,
            json=make_totp_code_payload("000000"),
        )
        assert confirm_resp.status_code == 401

    async def test_totp_enroll_confirm_replay_is_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "auth_totp_step_s", 300)
        monkeypatch.setattr(settings, "auth_totp_window", 0)
        monkeypatch.setattr(settings, "auth_totp_replay_ttl_s", 600)
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200
        secret = start_resp.json()["secret"]
        code = generate_totp_code(secret, step_s=settings.auth_totp_step_s)
        matched_counter = resolve_totp_counter(
            secret,
            code,
            step_s=settings.auth_totp_step_s,
            window=settings.auth_totp_window,
        )
        assert matched_counter is not None
        replay_key = f"{settings.tenant_id}:user_test_admin:enroll:{matched_counter}"
        assert consume_totp_counter_once(key=replay_key, ttl_s=settings.auth_totp_replay_ttl_s)

        confirm_resp = await client.post(
            "/auth/totp/enroll/confirm",
            headers=headers,
            json=make_totp_code_payload(code),
        )
        assert confirm_resp.status_code == 401

    async def test_totp_enroll_start_conflicts_when_already_enabled(self, client):
        headers = await _login_headers_for_seed_user(client)
        secret = generate_totp_secret()
        await _configure_totp_for_seed_user(secret)

        resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert resp.status_code == 409

    async def test_totp_login_accepts_recovery_code_once(self, client, monkeypatch):
        monkeypatch.setattr(settings, "auth_totp_step_s", 300)
        monkeypatch.setattr(settings, "auth_totp_window", 0)
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200
        secret = start_resp.json()["secret"]
        code = generate_totp_code(secret, step_s=settings.auth_totp_step_s)
        confirm_resp = await client.post(
            "/auth/totp/enroll/confirm",
            headers=headers,
            json=make_totp_code_payload(code),
        )
        assert confirm_resp.status_code == 200
        recovery_code = confirm_resp.json()["recovery_codes"][0]

        login_resp_1 = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_1.status_code == 200
        challenge_1 = login_resp_1.json()["challenge_token"]
        verify_1 = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_1, recovery_code),
        )
        assert verify_1.status_code == 200
        payload_1 = verify_1.json()
        token_1 = payload_1["access_token"]
        assert token_1
        decoded_1 = jwt.get_unverified_claims(token_1)
        assert decoded_1["amr"] == ["pwd", "recovery_code"]

        login_resp_2 = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_2.status_code == 200
        challenge_2 = login_resp_2.json()["challenge_token"]
        verify_2 = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_2, recovery_code),
        )
        assert verify_2.status_code == 401

    async def test_recovery_code_regeneration_invalidates_previous_codes(self, client, monkeypatch):
        monkeypatch.setattr(settings, "auth_totp_step_s", 300)
        monkeypatch.setattr(settings, "auth_totp_window", 0)
        headers = await _login_headers_for_seed_user(client)
        start_resp = await client.post("/auth/totp/enroll/start", headers=headers)
        assert start_resp.status_code == 200
        secret = start_resp.json()["secret"]
        code = generate_totp_code(secret, step_s=settings.auth_totp_step_s)
        confirm_resp = await client.post(
            "/auth/totp/enroll/confirm",
            headers=headers,
            json=make_totp_code_payload(code),
        )
        assert confirm_resp.status_code == 200
        old_recovery_code = confirm_resp.json()["recovery_codes"][0]

        regen_resp = await client.post("/auth/totp/recovery-codes/regenerate", headers=headers)
        assert regen_resp.status_code == 200
        regenerated = regen_resp.json()["recovery_codes"]
        assert isinstance(regenerated, list)
        assert len(regenerated) == 10
        new_recovery_code = regenerated[0]

        login_resp_old = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_old.status_code == 200
        challenge_old = login_resp_old.json()["challenge_token"]
        verify_old = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_old, old_recovery_code),
        )
        assert verify_old.status_code == 401

        login_resp_new = await client.post(
            "/auth/login",
            json=make_login_payload(),
        )
        assert login_resp_new.status_code == 200
        challenge_new = login_resp_new.json()["challenge_token"]
        verify_new = await client.post(
            "/auth/login/totp",
            json=make_totp_verify_payload(challenge_new, new_recovery_code),
        )
        assert verify_new.status_code == 200

        status_resp = await client.get("/auth/totp/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["recovery_codes_remaining"] == 9
