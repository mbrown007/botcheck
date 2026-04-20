from __future__ import annotations

from datetime import UTC, datetime, timedelta

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import RunRow


async def _insert_run_rows(*, count: int) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory() as session:
        for index in range(count):
            session.add(
                RunRow(
                    run_id=f"run_list_{index:03d}",
                    scenario_id=f"scenario_{index:03d}",
                    tenant_id=settings.tenant_id,
                    state="complete",
                    livekit_room=f"room_{index:03d}",
                    trigger_source="manual",
                    transport="mock",
                    conversation=[],
                    failed_dimensions=[],
                    scores={},
                    findings=[],
                    events=[],
                    created_at=base_time + timedelta(seconds=index),
                )
            )
        await session.commit()


async def test_list_runs_uses_default_limit_of_100(
    client,
    user_auth_headers,
):
    await _insert_run_rows(count=105)

    resp = await client.get("/runs/", headers=user_auth_headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 100
    assert payload[0]["run_id"] == "run_list_104"
    assert payload[-1]["run_id"] == "run_list_005"


async def test_list_runs_accepts_explicit_limit(
    client,
    user_auth_headers,
):
    await _insert_run_rows(count=5)

    resp = await client.get("/runs/?limit=2", headers=user_auth_headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert [row["run_id"] for row in payload] == ["run_list_004", "run_list_003"]


async def test_list_runs_applies_offset_after_ordering(
    client,
    user_auth_headers,
):
    await _insert_run_rows(count=5)

    resp = await client.get("/runs/?limit=2&offset=1", headers=user_auth_headers)

    assert resp.status_code == 200
    payload = resp.json()
    assert [row["run_id"] for row in payload] == ["run_list_003", "run_list_002"]


async def test_list_runs_rejects_invalid_limit(client, user_auth_headers):
    resp = await client.get("/runs/?limit=0", headers=user_auth_headers)
    assert resp.status_code == 422

    resp = await client.get("/runs/?limit=501", headers=user_auth_headers)
    assert resp.status_code == 422
