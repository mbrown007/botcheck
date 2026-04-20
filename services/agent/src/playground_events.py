from __future__ import annotations

from typing import Awaitable, Callable


class PlaygroundEventEmitter:
    def __init__(
        self,
        *,
        run_id: str,
        post_event_fn: Callable[..., Awaitable[None]],
    ) -> None:
        self._run_id = run_id
        self._post_event_fn = post_event_fn

    async def emit(self, event_type: str, payload: dict[str, object]) -> None:
        await self._post_event_fn(
            self._run_id,
            event_type=event_type,
            payload=payload,
        )
