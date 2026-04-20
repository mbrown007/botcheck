from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.scenario_wait import execute_wait_block

from botcheck_scenarios import WaitBlock


@pytest.mark.asyncio
async def test_execute_wait_block_sleeps_and_advances_graph(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr("src.scenario_wait.asyncio.sleep", sleep)
    graph_traversal = SimpleNamespace(advance=AsyncMock())

    turn_number = await execute_wait_block(
        turn_def=WaitBlock(id="t_wait", wait_s=2.5),
        turn_number=3,
        graph_traversal=graph_traversal,
        logger_obj=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert turn_number == 3
    sleep.assert_awaited_once_with(2.5)
    graph_traversal.advance.assert_awaited_once_with("default")


@pytest.mark.asyncio
async def test_execute_wait_block_without_graph_keeps_turn_number(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr("src.scenario_wait.asyncio.sleep", sleep)

    turn_number = await execute_wait_block(
        turn_def=WaitBlock(id="t_wait", wait_s=1.25),
        turn_number=5,
        graph_traversal=None,
        logger_obj=None,
    )

    assert turn_number == 5
    sleep.assert_awaited_once_with(1.25)
