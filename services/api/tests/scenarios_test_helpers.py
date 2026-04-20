"""Shared helpers for scenario route tests."""

import hashlib
import yaml

from botcheck_scenarios import ScenarioDefinition

from botcheck_api import database, store
from botcheck_api.auth import UserContext, issue_user_token
from botcheck_api.config import settings


def _viewer_auth_headers() -> dict[str, str]:
    token = issue_user_token(
        UserContext(
            sub="user_test_admin",
            tenant_id=settings.tenant_id,
            role="viewer",
            amr=("pwd",),
        )
    )
    return {"Authorization": f"Bearer {token}"}


async def store_scenario_yaml_direct(yaml_content: str) -> None:
    assert database.AsyncSessionLocal is not None
    scenario = ScenarioDefinition.model_validate(yaml.safe_load(yaml_content))
    version_hash = hashlib.sha256(yaml_content.encode()).hexdigest()[:16]
    async with database.AsyncSessionLocal() as db:
        await store.store_scenario(
            db,
            scenario,
            version_hash,
            yaml_content,
            settings.tenant_id,
        )
        await db.commit()
