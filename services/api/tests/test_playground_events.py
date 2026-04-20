"""Tests for playground event append and SSE replay endpoints."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from botcheck_api import database
from botcheck_api.main import app
from botcheck_api.models import PlaygroundEventRow, RunRow, RunState


async def _store_run_row_direct(
    *,
    scenario_id: str,
    run_type: str = "playground",
    playground_mode: str | None = "mock",
) -> str:
    run_id = f"run_{uuid4().hex[:12]}"
    assert database.AsyncSessionLocal is not None
    async with database.AsyncSessionLocal() as db:
        db.add(
            RunRow(
                run_id=run_id,
                scenario_id=scenario_id,
                tenant_id="default",
                state=RunState.PENDING.value,
                run_type=run_type,
                playground_mode=playground_mode,
                transport="mock",
                livekit_room=f"lk_{run_id}",
                trigger_source="manual",
            )
        )
        await db.commit()
    return run_id


class TestPlaygroundEvents:
    async def test_harness_can_record_playground_event_and_transition_run(
        self,
        client,
        harness_auth_headers,
    ):
        run_id = await _store_run_row_direct(scenario_id="scenario-playground")

        response = await client.post(
            f"/runs/{run_id}/events",
            json={
                "event_type": "turn.start",
                "payload": {"turn_id": "t1", "speaker": "harness", "text": "Hello"},
            },
            headers=harness_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["sequence_number"] == 1

        assert database.AsyncSessionLocal is not None
        async with database.AsyncSessionLocal() as db:
            run = await db.get(RunRow, run_id)
            assert run is not None
            assert run.state == RunState.RUNNING.value
            events = (
                await db.execute(
                    PlaygroundEventRow.__table__.select().where(PlaygroundEventRow.run_id == run_id)
                )
            ).all()
            assert len(events) == 1

    async def test_playground_stream_replays_events_and_last_event_id(
        self,
        client,
        user_auth_headers,
        harness_auth_headers,
    ):
        run_id = await _store_run_row_direct(scenario_id="scenario-playground")

        first = await client.post(
            f"/runs/{run_id}/events",
            json={"event_type": "turn.start", "payload": {"turn_id": "t1", "speaker": "harness"}},
            headers=harness_auth_headers,
        )
        second = await client.post(
            f"/runs/{run_id}/events",
            json={"event_type": "run.complete", "payload": {"run_id": run_id, "summary": "done"}},
            headers=harness_auth_headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200

        replay = await client.get(f"/runs/{run_id}/stream", headers=user_auth_headers)
        assert replay.status_code == 200
        assert replay.headers["content-type"].startswith("text/event-stream")
        assert "id: 1" in replay.text
        assert "event: turn.start" in replay.text
        assert "id: 2" in replay.text
        assert "event: run.complete" in replay.text

        resume = await client.get(
            f"/runs/{run_id}/stream",
            headers={**user_auth_headers, "Last-Event-ID": "1"},
        )
        assert resume.status_code == 200
        assert "event: turn.start" not in resume.text
        assert "id: 2" in resume.text
        assert "event: run.complete" in resume.text

    async def test_playground_stream_polls_persisted_events_without_pubsub(
        self,
        client,
        user_auth_headers,
        harness_auth_headers,
    ):
        run_id = await _store_run_row_direct(scenario_id="scenario-playground")

        mock_pool = MagicMock()
        mock_pool.enqueue_job = AsyncMock()
        mock_pool.set = AsyncMock()
        mock_pool.get = AsyncMock(return_value=None)
        app.state.arq_pool = mock_pool

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as stream_client:

            async def _consume() -> str:
                async with stream_client.stream(
                    "GET",
                    f"/runs/{run_id}/stream",
                    headers=user_auth_headers,
                ) as response:
                    assert response.status_code == 200
                    body = ""
                    async for chunk in response.aiter_text():
                        body += chunk
                    return body

            stream_task = asyncio.create_task(_consume())
            await asyncio.sleep(0.2)
            first = await client.post(
                f"/runs/{run_id}/events",
                json={"event_type": "turn.start", "payload": {"turn_id": "t1", "speaker": "harness"}},
                headers=harness_auth_headers,
            )
            second = await client.post(
                f"/runs/{run_id}/events",
                json={"event_type": "run.complete", "payload": {"run_id": run_id, "summary": "done"}},
                headers=harness_auth_headers,
            )
            assert first.status_code == 200
            assert second.status_code == 200
            body = await asyncio.wait_for(stream_task, timeout=5)

        assert "event: turn.start" in body
        assert "event: run.complete" in body

    async def test_playground_stream_404_for_standard_run(
        self,
        client,
        user_auth_headers,
    ):
        run_id = await _store_run_row_direct(
            scenario_id="scenario-playground",
            run_type="standard",
            playground_mode=None,
        )

        stream_response = await client.get(
            f"/runs/{run_id}/stream",
            headers=user_auth_headers,
        )
        assert stream_response.status_code == 404
