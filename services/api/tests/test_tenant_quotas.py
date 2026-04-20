from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import ProviderQuotaPolicyRow, RunRow, TenantRow

from factories import make_run_create_payload, make_scenario_upload_payload


async def _set_default_tenant_quota(**overrides: int) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        tenant = await session.get(TenantRow, settings.tenant_id)
        assert tenant is not None
        tenant.quota_config = dict(overrides)
        await session.commit()


async def _insert_run_row(*, state: str, created_at: datetime | None = None) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            RunRow(
                run_id=f"run_{state}_{int(datetime.now(UTC).timestamp() * 1000000)}",
                scenario_id="test-jailbreak",
                tenant_id=settings.tenant_id,
                state=state,
                livekit_room="room",
                trigger_source="manual",
                transport="mock",
                conversation=[],
                failed_dimensions=[],
                scores={},
                findings=[],
                events=[],
                created_at=created_at or datetime.now(UTC),
            )
        )
        await session.commit()


async def _insert_provider_quota_policy_row(
    *,
    provider_id: str,
    metric: str,
    limit_per_day: int,
    soft_limit_pct: int = 80,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            ProviderQuotaPolicyRow(
                quota_policy_id=f"provquota_{provider_id}_{metric}".replace(":", "_"),
                tenant_id=settings.tenant_id,
                provider_id=provider_id,
                metric=metric,
                limit_per_day=limit_per_day,
                soft_limit_pct=soft_limit_pct,
            )
        )
        await session.commit()


async def test_create_scenario_rejects_when_max_scenarios_quota_reached(
    client,
    scenario_yaml,
    user_auth_headers,
):
    await _set_default_tenant_quota(max_scenarios=0)

    resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(scenario_yaml),
        headers=user_auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "tenant_quota_exceeded"


async def test_create_schedule_rejects_when_max_schedules_quota_reached(
    client,
    uploaded_scenario,
    user_auth_headers,
):
    await _set_default_tenant_quota(max_schedules=0)

    resp = await client.post(
        "/schedules/",
        json={
            "target_type": "scenario",
            "scenario_id": uploaded_scenario["id"],
            "cron_expr": "0 * * * *",
        },
        headers=user_auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "tenant_quota_exceeded"


async def test_create_pack_rejects_when_max_packs_quota_reached(
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)
    await _set_default_tenant_quota(max_packs=0)

    resp = await client.post(
        "/packs/",
        json={
            "name": "Quota Pack",
            "description": "desc",
            "tags": [],
            "execution_mode": "parallel",
            "scenario_ids": [uploaded_scenario["id"]],
            "items": [],
        },
        headers=user_auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "tenant_quota_exceeded"


async def test_create_run_rejects_when_max_concurrent_runs_quota_reached(
    client,
    uploaded_scenario,
    user_auth_headers,
):
    await _insert_run_row(state="running")
    await _set_default_tenant_quota(max_concurrent_runs=1)

    resp = await client.post(
        "/runs/",
        json=make_run_create_payload(uploaded_scenario["id"]),
        headers=user_auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "tenant_quota_exceeded"


async def test_create_run_rejects_when_max_runs_per_day_quota_reached(
    client,
    uploaded_scenario,
    user_auth_headers,
):
    await _insert_run_row(state="complete")
    await _set_default_tenant_quota(max_runs_per_day=1)

    resp = await client.post(
        "/runs/",
        json=make_run_create_payload(uploaded_scenario["id"]),
        headers=user_auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "tenant_quota_exceeded"


async def test_create_run_rejects_when_provider_quota_reached(
    client,
    uploaded_scenario,
    user_auth_headers,
):
    await _insert_provider_quota_policy_row(
        provider_id="openai:gpt-4o-mini-tts",
        metric="requests",
        limit_per_day=0,
    )

    resp = await client.post(
        "/runs/",
        json=make_run_create_payload(uploaded_scenario["id"]),
        headers=user_auth_headers,
    )

    assert resp.status_code == 429
    assert resp.json()["error_code"] == "provider_quota_exceeded"
