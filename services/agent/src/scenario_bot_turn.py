from __future__ import annotations

import asyncio

from botcheck_scenarios import ConversationTurn

from .scenario_bot_listener import listen_bot_turn
from .scenario_turn_helpers import classify_branch_condition


async def execute_bot_listen_block(
    *,
    turn_def,
    turn_number: int,
    turn_visit: int,
    run_id: str,
    conversation: list[ConversationTurn],
    scenario,
    settings_obj,
    bot_listener,
    timeout: float,
    effective_merge_window_s: float,
    effective_endpointing_ms: int,
    classify_branch_fn,
    classifier_client,
    report_turn_fn,
    graph_traversal,
    now_ms_fn,
    emit_heartbeat_state_fn,
    logger_obj,
    scenario_kind: str = "graph",
) -> tuple[int, str]:
    turn_number += 1
    emit_heartbeat_state_fn(turn_number=turn_number, listener_state="awaiting_bot")
    if turn_def.config.pre_listen_wait_s > 0:
        await asyncio.sleep(turn_def.config.pre_listen_wait_s)

    # preview_callback intentionally omitted: graph scenarios have no AI caller
    # planning loop, so preview events serve no purpose here.
    bot_turn = await listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=timeout,
        merge_window_s=effective_merge_window_s,
        stt_endpointing_ms=effective_endpointing_ms,
        listen_for_s=getattr(turn_def.config, "listen_for_s", None),
        turn_id=turn_def.id,
        turn_number=turn_number,
        now_ms_fn=now_ms_fn,
        logger_obj=logger_obj,
        scenario_kind=scenario_kind,
    )
    conversation.append(bot_turn)

    chosen_branch_condition, branch_response_snippet = await classify_branch_condition(
        turn_def=turn_def,
        bot_text=bot_turn.text,
        conversation=conversation,
        scenario=scenario,
        classify_branch_fn=classify_branch_fn,
        classifier_client=classifier_client,
        classifier_model=settings_obj.branch_classifier_model,
        classifier_timeout_s=settings_obj.branch_classifier_timeout_s,
    )

    await report_turn_fn(
        run_id,
        bot_turn,
        visit=turn_visit,
        branch_condition_matched=(chosen_branch_condition if turn_def.branching is not None else None),
        branch_response_snippet=branch_response_snippet,
    )

    if graph_traversal is not None:
        graph_traversal.advance(chosen_branch_condition)

    return turn_number, chosen_branch_condition
