from __future__ import annotations

import inspect
from datetime import datetime
from zoneinfo import ZoneInfo


def _minutes_since_midnight(hhmm: str) -> int:
    hours_text, minutes_text = hhmm.split(":", 1)
    return int(hours_text) * 60 + int(minutes_text)


def resolve_time_route_label(*, turn_def, now: datetime | None = None) -> str:
    tz = ZoneInfo(turn_def.timezone)
    localized_now = (now or datetime.now(tz)).astimezone(tz)
    current_minute = localized_now.hour * 60 + localized_now.minute

    for window in turn_def.windows:
        start = _minutes_since_midnight(window.start)
        end = _minutes_since_midnight(window.end)
        if start < end:
            matches = start <= current_minute < end
        else:
            matches = current_minute >= start or current_minute < end
        if matches:
            return window.label
    return "default"


async def execute_time_route_block(
    *,
    turn_def,
    turn_number: int,
    graph_traversal,
    logger_obj,
    now_fn=None,
) -> int:
    chosen_label = resolve_time_route_label(turn_def=turn_def, now=now_fn() if now_fn else None)
    if logger_obj is not None:
        logger_obj.info(
            "Time route block selected path '%s' in timezone %s: %s",
            chosen_label,
            turn_def.timezone,
            turn_def.id,
        )
    if graph_traversal is not None:
        maybe_advance = graph_traversal.advance(chosen_label)
        if inspect.isawaitable(maybe_advance):
            await maybe_advance
    return turn_number
