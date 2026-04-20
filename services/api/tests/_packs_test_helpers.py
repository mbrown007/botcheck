from unittest.mock import AsyncMock, MagicMock

from botcheck_api import database
from botcheck_api.models import PackRunItemRow, RunRow
from sqlalchemy import select

from factories import (
    make_pack_upsert_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)


async def _upload_scenario(client, user_auth_headers, *, scenario_id: str, name: str) -> str:
    resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(
            make_scenario_yaml(scenario_id=scenario_id, name=name)
        ),
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]

def _livekit_mock():
    instance = MagicMock()
    instance.room.create_room = AsyncMock(return_value=MagicMock())
    instance.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    list_rooms_resp = MagicMock()
    list_rooms_resp.rooms = []
    instance.room.list_rooms = AsyncMock(return_value=list_rooms_resp)
    instance.room.delete_room = AsyncMock(return_value=MagicMock())
    instance.sip.create_sip_participant = AsyncMock(return_value=MagicMock())
    instance.aclose = AsyncMock()
    return instance

async def _create_pack_and_snapshot(
    client,
    user_auth_headers,
    *,
    name: str,
    scenario_ids: list[str],
) -> tuple[str, str]:
    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(name=name, scenario_ids=scenario_ids),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]
    run_resp = await client.post(f"/packs/{pack_id}/run", headers=user_auth_headers)
    assert run_resp.status_code == 202
    return pack_id, run_resp.json()["pack_run_id"]

async def _link_run_to_pack_item(
    *,
    pack_run_id: str,
    run_id: str,
    item_state: str = "dispatched",
    run_state: str | None = None,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        item = (
            await session.execute(
                select(PackRunItemRow)
                .where(PackRunItemRow.pack_run_id == pack_run_id)
                .order_by(PackRunItemRow.order_index.asc())
            )
        ).scalars().first()
        assert item is not None
        item.run_id = run_id
        item.state = item_state
        run_row = await session.get(RunRow, run_id)
        assert run_row is not None
        run_row.pack_run_id = pack_run_id
        if run_state is not None:
            run_row.state = run_state
        await session.commit()
