from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from botcheck_api import sip_slots_startup


class _GaugeStub:
    def __init__(self) -> None:
        self.values: list[int] = []

    def set(self, value: int) -> None:
        self.values.append(int(value))


@pytest.mark.asyncio
async def test_reconcile_sip_slots_active_gauge_sets_authoritative_count(monkeypatch) -> None:
    gauge = _GaugeStub()
    redis_pool = SimpleNamespace(
        ping=AsyncMock(return_value=True),
        keys=AsyncMock(return_value=[b"sip_slots:tenant-a:one", b"sip_slots:tenant-a:two"]),
        mget=AsyncMock(return_value=[b"3", b"2"]),
    )
    monkeypatch.setattr(sip_slots_startup.api_metrics, "SIP_SLOTS_ACTIVE", gauge)

    count = await sip_slots_startup.reconcile_sip_slots_active_gauge(redis_pool=redis_pool)

    assert count == 5  # sum of slot values (3 + 2), not key count
    assert gauge.values == [5]


@pytest.mark.asyncio
async def test_retry_sip_slot_reconciliation_until_ready_restores_pools_and_clears_pending(monkeypatch) -> None:
    gauge = _GaugeStub()
    created_pool = SimpleNamespace(
        ping=AsyncMock(return_value=True),
        keys=AsyncMock(return_value=[b"sip_slots:tenant-a:one"]),
        mget=AsyncMock(return_value=[b"1"]),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            arq_pool=None,
            arq_cache_pool=None,
            sip_slots_reconcile_pending=True,
        )
    )
    create_pools_fn = AsyncMock(side_effect=[RuntimeError("redis down"), (created_pool, created_pool)])
    sleep_fn = AsyncMock()
    monkeypatch.setattr(sip_slots_startup.api_metrics, "SIP_SLOTS_ACTIVE", gauge)

    reconciled = await sip_slots_startup.retry_sip_slot_reconciliation_until_ready(
        app,
        create_pools_fn=create_pools_fn,
        retry_delay_s=0,
        sleep_fn=sleep_fn,
        max_attempts=2,
    )

    assert reconciled is True
    assert app.state.arq_pool is created_pool
    assert app.state.arq_cache_pool is created_pool
    assert app.state.sip_slots_reconcile_pending is False
    assert gauge.values == [1]
    sleep_fn.assert_awaited_once_with(0)
