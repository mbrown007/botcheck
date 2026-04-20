from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit '{name}' is open")
        self.name = name


@dataclass(frozen=True)
class CircuitTransition:
    from_state: CircuitState
    to_state: CircuitState
    reason: str


class AsyncCircuitBreaker(Generic[T]):
    """Minimal async circuit breaker with open/half-open/closed states."""

    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int,
        recovery_timeout_s: float,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout_s <= 0:
            raise ValueError("recovery_timeout_s must be > 0")
        self._name = name
        self._failure_threshold = int(failure_threshold)
        self._recovery_timeout_s = float(recovery_timeout_s)
        self._monotonic = monotonic_fn or time.monotonic
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_in_flight = False

    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        on_transition: Callable[[CircuitTransition], None] | None = None,
        on_reject: Callable[[CircuitState], None] | None = None,
    ) -> T:
        transitions = self._before_call()
        if transitions and on_transition is not None:
            for transition in transitions:
                on_transition(transition)
        if transitions is None:
            if on_reject is not None:
                on_reject(self.state)
            raise CircuitOpenError(self._name)

        try:
            result = await operation()
        except asyncio.CancelledError:
            raise
        except Exception:
            transition = self._after_failure()
            if transition is not None and on_transition is not None:
                on_transition(transition)
            raise
        else:
            transition = self._after_success()
            if transition is not None and on_transition is not None:
                on_transition(transition)
            return result

    def _before_call(self) -> list[CircuitTransition] | None:
        with self._lock:
            transitions: list[CircuitTransition] = []
            now = self._monotonic()
            if self._state == CircuitState.OPEN:
                if self._opened_at is not None and (now - self._opened_at) >= self._recovery_timeout_s:
                    transitions.append(
                        self._transition_locked(CircuitState.HALF_OPEN, "recovery_timeout_elapsed")
                    )
                else:
                    return None

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    return None
                self._half_open_in_flight = True

            return [item for item in transitions if item is not None]

    def _after_success(self) -> CircuitTransition | None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_in_flight = False
                self._failure_count = 0
                return self._transition_locked(CircuitState.CLOSED, "half_open_success")
            if self._state == CircuitState.CLOSED:
                self._failure_count = 0
            return None

    def _after_failure(self) -> CircuitTransition | None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_in_flight = False
                return self._transition_locked(CircuitState.OPEN, "half_open_failure")
            if self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    return self._transition_locked(CircuitState.OPEN, "failure_threshold_reached")
            return None

    def _transition_locked(self, to_state: CircuitState, reason: str) -> CircuitTransition:
        from_state = self._state
        self._state = to_state
        if to_state == CircuitState.OPEN:
            self._opened_at = self._monotonic()
            self._failure_count = 0
            self._half_open_in_flight = False
        elif to_state == CircuitState.CLOSED:
            self._opened_at = None
            self._failure_count = 0
            self._half_open_in_flight = False
        elif to_state == CircuitState.HALF_OPEN:
            self._failure_count = 0
            self._opened_at = None
        return CircuitTransition(from_state=from_state, to_state=to_state, reason=reason)
