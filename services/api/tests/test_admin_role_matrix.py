from __future__ import annotations

from datetime import UTC, datetime

import pytest
from jose import jwt

from botcheck_api.config import settings


def _role_auth_headers(role: str, *, tenant_id: str | None = None) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": f"{role}-admin-matrix-user",
            "tenant_id": tenant_id or settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "amr": ["pwd", "dev_token"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("path", "expected_for_role"),
    [
        (
            "/admin/users/",
            {
                "viewer": 403,
                "operator": 403,
                "editor": 403,
                "admin": 200,
                "system_admin": 200,
            },
        ),
        (
            "/admin/audit/",
            {
                "viewer": 403,
                "operator": 403,
                "editor": 403,
                "admin": 200,
                "system_admin": 200,
            },
        ),
        (
            "/admin/tenants/",
            {
                "viewer": 403,
                "operator": 403,
                "editor": 403,
                "admin": 403,
                "system_admin": 200,
            },
        ),
        (
            "/admin/sip/trunks",
            {
                "viewer": 403,
                "operator": 403,
                "editor": 403,
                "admin": 403,
                "system_admin": 200,
            },
        ),
        (
            "/admin/system/health",
            {
                "viewer": 403,
                "operator": 403,
                "editor": 403,
                "admin": 403,
                "system_admin": 200,
            },
        ),
    ],
)
@pytest.mark.parametrize("role", ["viewer", "operator", "editor", "admin", "system_admin"])
async def test_admin_endpoint_role_matrix(path, expected_for_role, role, client):
    resp = await client.get(path, headers=_role_auth_headers(role))

    assert resp.status_code == expected_for_role[role]
