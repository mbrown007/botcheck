from __future__ import annotations

import asyncio
import inspect


async def execute_wait_block(
    *,
    turn_def,
    turn_number: int,
    graph_traversal,
    logger_obj,
) -> int:
    if logger_obj is not None:
        logger_obj.info("Wait block sleeping for %.3fs: %s", turn_def.wait_s, turn_def.id)
    await asyncio.sleep(turn_def.wait_s)
    if graph_traversal is not None:
        maybe_advance = graph_traversal.advance("default")
        if inspect.isawaitable(maybe_advance):
            await maybe_advance
    return turn_number
