from __future__ import annotations


class HeartbeatContext:
    def __init__(self) -> None:
        self._turn_number: int | None = None
        self._listener_state: str | None = "booting"

    def update(self, turn_number: int | None, listener_state: str | None) -> None:
        if isinstance(turn_number, int) and turn_number > 0:
            self._turn_number = turn_number
        if isinstance(listener_state, str):
            candidate = listener_state.strip().lower()
            self._listener_state = candidate[:64] if candidate else None

    def snapshot(self) -> tuple[int | None, str | None]:
        return self._turn_number, self._listener_state
