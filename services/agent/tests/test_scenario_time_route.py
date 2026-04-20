from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from src.scenario_time_route import execute_time_route_block, resolve_time_route_label

from botcheck_scenarios import TimeRouteBlock


def _time_route_block() -> TimeRouteBlock:
    return TimeRouteBlock(
        id="t_route",
        timezone="UTC",
        windows=[
            {"label": "business_hours", "start": "09:00", "end": "17:00", "next": "t_business"},
            {"label": "after_hours", "start": "22:00", "end": "06:00", "next": "t_after_hours"},
        ],
        default="t_default",
    )


def test_resolve_time_route_label_matches_inclusive_start_exclusive_end() -> None:
    turn_def = _time_route_block()

    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 9, 0, tzinfo=ZoneInfo("UTC")),
        )
        == "business_hours"
    )
    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 16, 59, tzinfo=ZoneInfo("UTC")),
        )
        == "business_hours"
    )
    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 17, 0, tzinfo=ZoneInfo("UTC")),
        )
        == "default"
    )


def test_resolve_time_route_label_matches_midnight_wrapping_window() -> None:
    turn_def = _time_route_block()

    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 23, 30, tzinfo=ZoneInfo("UTC")),
        )
        == "after_hours"
    )
    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 5, 59, tzinfo=ZoneInfo("UTC")),
        )
        == "after_hours"
    )
    assert (
        resolve_time_route_label(
            turn_def=turn_def,
            now=datetime(2026, 4, 13, 6, 0, tzinfo=ZoneInfo("UTC")),
        )
        == "default"
    )


@pytest.mark.asyncio
async def test_execute_time_route_block_advances_graph_with_resolved_label() -> None:
    graph_traversal = SimpleNamespace(advance=AsyncMock())
    logger_obj = SimpleNamespace(info=lambda *args, **kwargs: None)

    turn_number = await execute_time_route_block(
        turn_def=_time_route_block(),
        turn_number=7,
        graph_traversal=graph_traversal,
        logger_obj=logger_obj,
        now_fn=lambda: datetime(2026, 4, 13, 9, 30, tzinfo=ZoneInfo("UTC")),
    )

    assert turn_number == 7
    graph_traversal.advance.assert_awaited_once_with("business_hours")


@pytest.mark.asyncio
async def test_execute_time_route_block_without_graph_keeps_turn_number() -> None:
    turn_number = await execute_time_route_block(
        turn_def=_time_route_block(),
        turn_number=4,
        graph_traversal=None,
        logger_obj=None,
        now_fn=lambda: datetime(2026, 4, 13, 17, 0, tzinfo=ZoneInfo("UTC")),
    )

    assert turn_number == 4
