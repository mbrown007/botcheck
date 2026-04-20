from __future__ import annotations

import asyncio

import pytest

from botcheck_scenarios.circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_breaker_opens_after_failure_threshold_and_rejects() -> None:
    clock = _Clock()
    breaker = AsyncCircuitBreaker[int](
        name="test-breaker",
        failure_threshold=2,
        recovery_timeout_s=30.0,
        monotonic_fn=clock.monotonic,
    )

    async def _fail() -> int:
        raise RuntimeError("provider-down")

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        await breaker.call(_fail)


@pytest.mark.asyncio
async def test_breaker_half_open_then_closes_on_success() -> None:
    clock = _Clock()
    breaker = AsyncCircuitBreaker[int](
        name="test-breaker",
        failure_threshold=1,
        recovery_timeout_s=10.0,
        monotonic_fn=clock.monotonic,
    )

    async def _fail() -> int:
        raise RuntimeError("provider-down")

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        await breaker.call(lambda: asyncio.sleep(0.0, result=1))

    clock.advance(11.0)
    result = await breaker.call(lambda: asyncio.sleep(0.0, result=7))
    assert result == 7
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens() -> None:
    clock = _Clock()
    breaker = AsyncCircuitBreaker[int](
        name="test-breaker",
        failure_threshold=1,
        recovery_timeout_s=5.0,
        monotonic_fn=clock.monotonic,
    )

    async def _fail() -> int:
        raise RuntimeError("provider-down")

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.OPEN

    clock.advance(6.0)
    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_breaker_does_not_count_cancelled_error_as_failure() -> None:
    clock = _Clock()
    breaker = AsyncCircuitBreaker[int](
        name="test-breaker",
        failure_threshold=1,
        recovery_timeout_s=5.0,
        monotonic_fn=clock.monotonic,
    )

    async def _cancelled() -> int:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await breaker.call(_cancelled)

    # Cancelled requests should not trip/open the circuit.
    assert breaker.state == CircuitState.CLOSED
