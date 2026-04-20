from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from typing import AsyncIterator

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PlaygroundEventRow, RunRow

PLAYGROUND_EVENT_CHANNEL_PREFIX = "botcheck:playground-events"
TERMINAL_PLAYGROUND_EVENT = "run.complete"


def playground_event_channel(run_id: str) -> str:
    return f"{PLAYGROUND_EVENT_CHANNEL_PREFIX}:{run_id}"


def supports_live_playground_pubsub(redis_pool: object | None) -> bool:
    pubsub_factory = getattr(redis_pool, "pubsub", None) if redis_pool is not None else None
    if not callable(pubsub_factory):
        return False
    try:
        pubsub = pubsub_factory()
    except Exception:
        return False
    subscribe = getattr(pubsub, "subscribe", None)
    get_message = getattr(pubsub, "get_message", None)
    return inspect.iscoroutinefunction(subscribe) and inspect.iscoroutinefunction(get_message)


def serialize_playground_event(row: PlaygroundEventRow) -> dict[str, object]:
    return {
        "run_id": row.run_id,
        "sequence_number": row.sequence_number,
        "event_type": row.event_type,
        "payload": dict(row.payload or {}),
        "created_at": row.created_at.astimezone(UTC).isoformat(),
    }


def format_sse_event(event: dict[str, object]) -> str:
    return (
        f"id: {int(event['sequence_number'])}\n"
        f"event: {str(event['event_type'])}\n"
        f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
    )


async def next_playground_event_sequence(db: AsyncSession, *, run_id: str) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(PlaygroundEventRow.sequence_number), 0)).where(
            PlaygroundEventRow.run_id == run_id
        )
    )
    return int(result.scalar_one() or 0) + 1


async def append_playground_event(
    db: AsyncSession,
    *,
    run: RunRow,
    event_type: str,
    payload: dict[str, object] | None,
) -> PlaygroundEventRow:
    sequence_number = await next_playground_event_sequence(db, run_id=run.run_id)
    row = PlaygroundEventRow(
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        sequence_number=sequence_number,
        event_type=event_type.strip(),
        payload=dict(payload or {}),
        created_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


async def list_playground_events(
    db: AsyncSession,
    *,
    run_id: str,
    after_sequence_number: int = 0,
) -> list[PlaygroundEventRow]:
    result = await db.execute(
        select(PlaygroundEventRow)
        .where(
            PlaygroundEventRow.run_id == run_id,
            PlaygroundEventRow.sequence_number > after_sequence_number,
        )
        .order_by(PlaygroundEventRow.sequence_number.asc())
    )
    return list(result.scalars().all())


async def publish_playground_event(redis_pool: object | None, event: dict[str, object]) -> None:
    publish_fn = getattr(redis_pool, "publish", None) if redis_pool is not None else None
    if not callable(publish_fn):
        return
    maybe = publish_fn(playground_event_channel(str(event["run_id"])), json.dumps(event))
    if asyncio.iscoroutine(maybe):
        await maybe


async def iter_live_playground_events(
    *,
    redis_pool: object | None,
    run_id: str,
    after_sequence_number: int,
) -> AsyncIterator[dict[str, object]]:
    pubsub_factory = getattr(redis_pool, "pubsub", None) if redis_pool is not None else None
    if not callable(pubsub_factory):
        return
    pubsub = pubsub_factory()
    subscribe = getattr(pubsub, "subscribe", None)
    unsubscribe = getattr(pubsub, "unsubscribe", None)
    get_message = getattr(pubsub, "get_message", None)
    aclose = getattr(pubsub, "aclose", None)
    close = getattr(pubsub, "close", None)
    if not callable(subscribe) or not callable(get_message):
        if callable(aclose):
            await aclose()
        elif callable(close):
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe
        return

    seen = after_sequence_number
    channel = playground_event_channel(run_id)
    await subscribe(channel)
    try:
        while True:
            message = await get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message:
                continue
            if str(message.get("type")) != "message":
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if not isinstance(raw, str):
                continue
            try:
                event = json.loads(raw)
            except Exception:
                continue
            try:
                sequence_number = int(event.get("sequence_number") or 0)
            except Exception:
                continue
            if sequence_number <= seen:
                continue
            seen = sequence_number
            yield event
    finally:
        if callable(unsubscribe):
            await unsubscribe(channel)
        if callable(aclose):
            await aclose()
        elif callable(close):
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe


def parse_last_event_id(value: str | None) -> int:
    candidate = str(value or "").strip()
    if not candidate:
        return 0
    try:
        parsed = int(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Last-Event-ID must be an integer") from exc
    return max(parsed, 0)
