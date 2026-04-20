"""Shared helpers/constants for run route tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from jose import jwt

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import RunRow, ScenarioRow

from factories import make_conversation_turn, make_run_create_payload


def _other_tenant_headers() -> dict[str, str]:
    """JWT token for a different tenant — simulates a cross-tenant request."""
    token = jwt.encode(
        {"sub": "other-user", "tenant_id": "other-tenant", "role": "admin", "iss": settings.auth_issuer},
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


MOCK_SCORE_RESULT = {
    "gate_result": "passed",
    "overall_status": "pass",
    "failed_dimensions": [],
    "summary": "All checks passed.",
}

SAMPLE_CONVERSATION = [
    make_conversation_turn(
        turn_id="t1",
        turn_number=1,
        speaker="harness",
        text="Hello.",
        audio_start_ms=0,
        audio_end_ms=800,
    ),
    make_conversation_turn(
        turn_id="t2",
        turn_number=2,
        speaker="bot",
        text="Hello! How can I help?",
        audio_start_ms=1000,
        audio_end_ms=2500,
    ),
]


def _livekit_mock():
    """AsyncMock instance that acts as a LiveKitAPI with silent async methods."""
    m = MagicMock()
    m.room.create_room = AsyncMock(return_value=MagicMock())
    list_rooms_resp = MagicMock()
    list_rooms_resp.rooms = []
    m.room.list_rooms = AsyncMock(return_value=list_rooms_resp)
    m.room.delete_room = AsyncMock(return_value=MagicMock())
    m.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    m.sip.create_sip_participant = AsyncMock(return_value=MagicMock())
    m.aclose = AsyncMock()
    return m


async def _create_run(client, scenario_id: str, user_auth_headers: dict[str, str]) -> str:
    resp = await client.post(
        "/runs/",
        json=make_run_create_payload(scenario_id),
        headers=user_auth_headers,
    )
    assert resp.status_code == 202
    return resp.json()["run_id"]


async def _set_run_created_at(run_id: str, created_at: datetime) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(RunRow, run_id)
        assert row is not None
        row.created_at = created_at
        await db.commit()


async def _set_run_runtime_snapshot(
    run_id: str,
    *,
    run_started_at: datetime | None = None,
    max_duration_s_at_start: float | None = None,
    last_heartbeat_at: datetime | None = None,
    last_heartbeat_seq: int | None = None,
    state: str | None = None,
    transport: str | None = None,
    sip_slot_held: bool | None = None,
    livekit_room: str | None = None,
) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(RunRow, run_id)
        assert row is not None
        if run_started_at is not None:
            row.run_started_at = run_started_at
        if max_duration_s_at_start is not None:
            row.max_duration_s_at_start = max_duration_s_at_start
        if last_heartbeat_at is not None:
            row.last_heartbeat_at = last_heartbeat_at
        if last_heartbeat_seq is not None:
            row.last_heartbeat_seq = last_heartbeat_seq
        if state is not None:
            row.state = state
        if transport is not None:
            row.transport = transport
        if sip_slot_held is not None:
            row.sip_slot_held = sip_slot_held
        if livekit_room is not None:
            row.livekit_room = livekit_room
        await db.commit()


async def _get_run_heartbeat_snapshot(run_id: str) -> tuple[datetime | None, int | None, str]:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(RunRow, run_id)
        assert row is not None
        return row.last_heartbeat_at, row.last_heartbeat_seq, row.state


async def _set_scenario_cache_status(
    scenario_id: str,
    cache_status: str,
    tenant_id: str = "default",
) -> None:
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        row = await db.get(ScenarioRow, scenario_id)
        assert row is not None
        assert row.tenant_id == tenant_id
        row.cache_status = cache_status
        await db.commit()
