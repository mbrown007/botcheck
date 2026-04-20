"""Unit tests for SIP secret-provider credential loading."""

import json

from botcheck_api.config import settings
from botcheck_api.sip import clear_sip_credentials_cache, load_sip_credentials


class _FakeSecretsManagerClient:
    def __init__(self, payload: dict[str, str], call_counter: dict[str, int]):
        self._payload = payload
        self._call_counter = call_counter

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_secret_value(self, SecretId: str):
        self._call_counter["count"] += 1
        return {"SecretString": json.dumps(self._payload)}


class _FakeAioboto3Session:
    def __init__(self, payload: dict[str, str], call_counter: dict[str, int]):
        self._payload = payload
        self._call_counter = call_counter

    def client(self, service_name: str, region_name: str):
        assert service_name == "secretsmanager"
        assert region_name == "us-east-1"
        return _FakeSecretsManagerClient(self._payload, self._call_counter)


class _FakeHTTPResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _FakeHTTPClient:
    def __init__(self, response: _FakeHTTPResponse, capture: dict):
        self._response = response
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, headers: dict[str, str]):
        self._capture["url"] = url
        self._capture["headers"] = headers
        return self._response


class TestSipCredentials:
    async def test_load_sip_credentials_from_env(self, monkeypatch):
        clear_sip_credentials_cache()
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "environment", "development")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-dev")
        monkeypatch.setattr(settings, "sip_auth_username", "user-dev")
        monkeypatch.setattr(settings, "sip_auth_password", "pass-dev")

        creds = await load_sip_credentials(settings)

        assert creds.trunk_id == "trunk-dev"
        assert creds.auth_username == "user-dev"
        assert creds.auth_password == "pass-dev"

    async def test_env_provider_rejected_in_production(self, monkeypatch):
        clear_sip_credentials_cache()
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "allow_env_sip_secrets_in_production", False)

        try:
            await load_sip_credentials(settings)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "disabled in production" in str(exc).lower()

    async def test_load_sip_credentials_from_aws_with_cache(self, monkeypatch):
        clear_sip_credentials_cache()
        monkeypatch.setattr(settings, "sip_secret_provider", "aws_secrets_manager")
        monkeypatch.setattr(settings, "sip_secret_ref", "botcheck/sip")
        monkeypatch.setattr(settings, "sip_secret_region", "us-east-1")
        monkeypatch.setattr(settings, "sip_secret_cache_ttl_s", 60)
        call_counter = {"count": 0}
        payload = {
            "sip_trunk_id": "trunk-aws",
            "sip_auth_username": "user-aws",
            "sip_auth_password": "pass-aws",
        }
        monkeypatch.setattr(
            "botcheck_api.sip.aioboto3.Session",
            lambda: _FakeAioboto3Session(payload, call_counter),
        )

        creds1 = await load_sip_credentials(settings)
        creds2 = await load_sip_credentials(settings)

        assert call_counter["count"] == 1
        assert creds1 == creds2
        assert creds1.trunk_id == "trunk-aws"

    async def test_load_sip_credentials_from_vault_kv2(self, monkeypatch):
        clear_sip_credentials_cache()
        monkeypatch.setattr(settings, "sip_secret_provider", "vault")
        monkeypatch.setattr(settings, "sip_secret_ref", "secret/data/botcheck/sip")
        monkeypatch.setattr(settings, "vault_addr", "https://vault.example.com")
        monkeypatch.setattr(settings, "vault_token", "vault-token")
        monkeypatch.setattr(settings, "vault_namespace", "team-a")
        monkeypatch.setattr(settings, "vault_kv_version", 2)
        capture: dict[str, dict[str, str] | str] = {}
        response = _FakeHTTPResponse(
            200,
            {
                "data": {
                    "data": {
                        "sip_trunk_id": "trunk-vault",
                        "sip_auth_username": "user-vault",
                        "sip_auth_password": "pass-vault",
                    }
                }
            },
        )
        monkeypatch.setattr(
            "botcheck_api.sip.httpx.AsyncClient",
            lambda timeout: _FakeHTTPClient(response, capture),
        )

        creds = await load_sip_credentials(settings)

        assert creds.trunk_id == "trunk-vault"
        assert creds.auth_username == "user-vault"
        assert creds.auth_password == "pass-vault"
        assert capture["url"] == "https://vault.example.com/v1/secret/data/botcheck/sip"
        headers = capture["headers"]
        assert isinstance(headers, dict)
        assert headers["X-Vault-Token"] == "vault-token"
        assert headers["X-Vault-Namespace"] == "team-a"
