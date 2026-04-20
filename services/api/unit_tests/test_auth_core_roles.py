from __future__ import annotations

import pytest
from fastapi import HTTPException

from botcheck_api.auth.core import (
    Role,
    _ROLE_RANK,
    normalize_role_value,
    require_admin,
    require_platform_admin,
    require_role,
    require_viewer,
)
from botcheck_api.auth import UserContext
from botcheck_api.config import settings


def test_role_rank_ordering():
    assert _ROLE_RANK == {
        "viewer": 0,
        "operator": 1,
        "editor": 2,
        "admin": 3,
        "system_admin": 4,
    }


def test_normalize_role_value_canonicalizes_and_falls_back_to_viewer():
    assert normalize_role_value("ADMIN") == "admin"
    assert normalize_role_value(" system_admin ") == "system_admin"
    assert normalize_role_value("   ") == "viewer"
    assert normalize_role_value("qa_engineer") == "viewer"
    assert normalize_role_value(None) == "viewer"


@pytest.mark.asyncio
async def test_require_role_allows_exact_match(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")
    dependency = require_role(Role.EDITOR)

    user = UserContext(sub="user-1", tenant_id="tenant-a", role="editor")

    assert await dependency(user=user) == user


@pytest.mark.asyncio
async def test_require_role_allows_higher_rank(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")
    dependency = require_role(Role.OPERATOR)

    user = UserContext(sub="user-1", tenant_id="tenant-a", role="system_admin")

    assert await dependency(user=user) == user


@pytest.mark.asyncio
async def test_require_role_rejects_lower_rank(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")
    dependency = require_role(Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user=UserContext(sub="user-1", tenant_id="tenant-a", role="editor"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient role"


@pytest.mark.asyncio
async def test_require_role_rejects_tenant_mismatch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")
    dependency = require_role(Role.VIEWER)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user=UserContext(sub="user-1", tenant_id="tenant-b", role="system_admin"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Tenant mismatch"


@pytest.mark.asyncio
async def test_prebound_aliases_apply_expected_minimums(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")

    viewer = UserContext(sub="viewer-1", tenant_id="tenant-a", role="viewer")
    assert await require_viewer(user=viewer) == viewer

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user=UserContext(sub="user-1", tenant_id="tenant-a", role="editor"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient role"


@pytest.mark.asyncio
async def test_require_platform_admin_allows_cross_tenant_system_admin(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")
    user = UserContext(sub="user-1", tenant_id="tenant-b", role="system_admin")

    assert await require_platform_admin(user=user) == user


@pytest.mark.asyncio
async def test_require_platform_admin_rejects_tenant_admin(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "tenant_id", "tenant-a")

    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(
            user=UserContext(sub="user-1", tenant_id="tenant-b", role="admin")
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient role"
