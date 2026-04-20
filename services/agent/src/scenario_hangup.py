from __future__ import annotations


async def execute_hangup_block(
    *,
    turn_def,
    turn_number: int,
    graph_traversal,
    logger_obj,
) -> int:
    if logger_obj is not None:
        logger_obj.info("Hangup block reached: %s", turn_def.id)
    # HangupBlock has no successors in the graph (enforced in ScenarioGraph._build).
    # Advancing the cursor here would move to None, stopping the loop on the *next*
    # iteration rather than immediately. Call advance so the cursor is consistent, but
    # the loop will exit at the top of the next iteration when cursor_step is None.
    if graph_traversal is not None:
        graph_traversal.advance("default")
    return turn_number
