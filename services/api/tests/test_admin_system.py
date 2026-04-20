from __future__ import annotations

from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.config import settings

from factories import make_scenario_upload_payload, make_scenario_yaml


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


async def test_admin_system_requires_platform_admin(client):
    resp = await client.get("/admin/system/health", headers=_admin_headers())
    assert resp.status_code == 403


async def test_admin_system_health_and_config_redaction(client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "live-secret")

    health_resp = await client.get("/admin/system/health", headers=_platform_admin_headers())
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert health["database"]["status"] == "ok"
    assert health["redis"]["status"] == "ok"
    assert "openai" in health["providers"]

    config_resp = await client.get("/admin/system/config", headers=_platform_admin_headers())
    assert config_resp.status_code == 200
    config = config_resp.json()["config"]
    assert config["secret_key"] == "<redacted>"
    assert config["openai_api_key"] == "<redacted>"
    assert config["local_auth_password"] == "<redacted>"


async def test_admin_system_feature_flag_patch_updates_features(client):
    patch_resp = await client.patch(
        "/admin/system/feature-flags",
        json={"feature_flags": {"feature_packs_enabled": True}},
        headers=_platform_admin_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["feature_flags"]["feature_packs_enabled"] is True

    features_resp = await client.get("/features")
    assert features_resp.status_code == 200
    assert features_resp.json()["packs_enabled"] is True


async def test_admin_system_quota_patch_updates_default_enforcement(
    client,
    user_auth_headers,
):
    patch_resp = await client.patch(
        "/admin/system/quotas",
        json={"quota_defaults": {"max_scenarios": 0}},
        headers=_platform_admin_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["quota_defaults"]["max_scenarios"] == 0

    create_resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(make_scenario_yaml()),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 409
    assert create_resp.json()["error_code"] == "tenant_quota_exceeded"
