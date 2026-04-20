from __future__ import annotations

from botcheck_api import users_bootstrap
from botcheck_api.auth import Role
from botcheck_api.config import settings


def test_load_bootstrap_users_normalizes_invalid_role_to_viewer(
    monkeypatch,
    tmp_path,
):
    bootstrap_path = tmp_path / "users.yaml"
    bootstrap_path.write_text(
        """
users:
  - email: "  ADMIN@example.com  "
    tenant_id: default
    role: qa_engineer
    password_hash: hash-1
""".strip()
    )

    monkeypatch.setattr(settings, "users_bootstrap_enabled", True)
    monkeypatch.setattr(settings, "users_bootstrap_path", str(bootstrap_path))

    users = users_bootstrap.load_bootstrap_users()

    assert len(users) == 1
    assert users[0].email == "admin@example.com"
    assert users[0].role == Role.VIEWER.value
