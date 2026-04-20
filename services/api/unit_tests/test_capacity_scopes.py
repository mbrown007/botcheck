from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from botcheck_api import capacity


def test_build_sip_slot_key_uses_tenant_and_scope() -> None:
    key = capacity.build_sip_slot_key(tenant_id="tenant-a", capacity_scope="carrier-1")
    assert key == "sip_slots:tenant-a:carrier-1"


def test_build_sip_slot_key_defaults_scope_when_empty() -> None:
    key = capacity.build_sip_slot_key(tenant_id="tenant-a", capacity_scope="")
    assert key == f"sip_slots:tenant-a:{capacity.DEFAULT_SIP_CAPACITY_SCOPE}"


@pytest.mark.asyncio
async def test_local_fallback_slots_are_isolated_per_slot_key() -> None:
    capacity._local_slots_by_key.clear()
    capacity._local_lock = None  # reset so the lock binds to this test's event loop

    key_a = capacity.build_sip_slot_key(tenant_id="tenant-a", capacity_scope="carrier-a")
    key_b = capacity.build_sip_slot_key(tenant_id="tenant-a", capacity_scope="carrier-b")

    assert (
        await capacity.try_acquire_sip_slot(
            redis_pool=None,
            max_slots=1,
            slot_ttl_s=30,
            slot_key=key_a,
        )
        is True
    )
    assert (
        await capacity.try_acquire_sip_slot(
            redis_pool=None,
            max_slots=1,
            slot_ttl_s=30,
            slot_key=key_a,
        )
        is False
    )
    assert (
        await capacity.try_acquire_sip_slot(
            redis_pool=None,
            max_slots=1,
            slot_ttl_s=30,
            slot_key=key_b,
        )
        is True
    )

    await capacity.release_sip_slot(redis_pool=None, slot_ttl_s=30, slot_key=key_a)
    assert (
        await capacity.try_acquire_sip_slot(
            redis_pool=None,
            max_slots=1,
            slot_ttl_s=30,
            slot_key=key_a,
        )
        is True
    )


@pytest.mark.asyncio
async def test_acquire_with_backoff_passes_slot_key(monkeypatch) -> None:
    key = capacity.build_sip_slot_key(tenant_id="tenant-z", capacity_scope="scope-z")
    acquire = AsyncMock(return_value=True)
    monkeypatch.setattr(capacity, "try_acquire_sip_slot", acquire)

    result = await capacity.acquire_with_backoff(
        redis_pool=None,
        max_slots=3,
        slot_ttl_s=30,
        attempts=1,
        backoff_s=1,
        jitter_s=0,
        slot_key=key,
    )

    assert result is True
    acquire.assert_awaited_once_with(
        redis_pool=None,
        max_slots=3,
        slot_ttl_s=30,
        slot_key=key,
    )


@pytest.mark.asyncio
async def test_count_active_sip_slots_uses_matching_redis_keys() -> None:
    redis_pool = type(
        "RedisPoolStub",
        (),
        {
            "keys": AsyncMock(return_value=[b"sip_slots:tenant-a:one", b"sip_slots:tenant-b:two"]),
            "mget": AsyncMock(return_value=[b"3", b"2"]),
        },
    )()

    count = await capacity.count_active_sip_slots(redis_pool=redis_pool)

    assert count == 5  # sum of slot values (3 + 2), not key count
    redis_pool.keys.assert_awaited_once_with("sip_slots:*")
    redis_pool.mget.assert_awaited_once_with(b"sip_slots:tenant-a:one", b"sip_slots:tenant-b:two")


@pytest.mark.asyncio
async def test_count_active_sip_slots_prefers_scan_when_available() -> None:
    redis_pool = type(
        "RedisPoolStub",
        (),
        {
            "scan": AsyncMock(
                side_effect=[
                    (1, [b"sip_slots:tenant-a:one"]),
                    (0, [b"sip_slots:tenant-b:two", b"sip_slots:tenant-c:three"]),
                ]
            ),
            "mget": AsyncMock(
                side_effect=[
                    [b"2"],       # first scan batch: 1 key with value 2
                    [b"1", b"3"], # second scan batch: 2 keys with values 1 and 3
                ]
            ),
            "keys": AsyncMock(return_value=[]),
        },
    )()

    count = await capacity.count_active_sip_slots(redis_pool=redis_pool)

    assert count == 6  # sum of slot values (2 + 1 + 3), not key count
    assert redis_pool.scan.await_count == 2
    redis_pool.keys.assert_not_awaited()
