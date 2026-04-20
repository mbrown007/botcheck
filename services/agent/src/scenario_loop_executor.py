from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from botcheck_scenarios import ConversationTurn

from .loop_runtime_helpers import (
    build_heartbeat_state_emitter,
    build_now_ms_fn,
    init_tts_circuit_bridge,
)
from .scenario_bot_turn import execute_bot_listen_block
from .scenario_hangup import execute_hangup_block
from .scenario_harness_turn import execute_harness_prompt_block
from .scenario_time_route import execute_time_route_block
from .scenario_turn_cursor import create_turn_cursor
from .scenario_turn_helpers import effective_stt_settings, effective_turn_timeout
from .scenario_wait import execute_wait_block


async def execute_scenario_loop(
    *,
    scenario,
    run_id: str,
    tenant_id: str,
    settings_obj,
    bot_listener,
    audio_source,
    tts,
    read_cached_turn_wav_fn,
    publish_cached_wav_fn,
    report_turn_fn,
    classify_branch_fn,
    classifier_client,
    logger_obj,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    tts_live_circuit_breaker=None,
    provider_circuit_state_callback: (
        Callable[
            ...,
            Awaitable[None],
        ]
        | None
    ) = None,
    call_started_monotonic: float | None = None,
    scenario_kind: str = "graph",
) -> tuple[list[ConversationTurn], int]:
    conversation: list[ConversationTurn] = []
    response_visit_counts: dict[str, int] = defaultdict(int)
    turn_number = 0
    call_started = call_started_monotonic or time.monotonic()
    turn_cursor, graph_traversal = create_turn_cursor(
        scenario=scenario,
        enable_branching_graph=settings_obj.enable_branching_graph,
        max_total_turns_hard_cap=settings_obj.max_total_turns_hard_cap,
    )

    _emit_heartbeat_state = build_heartbeat_state_emitter(heartbeat_state_callback)
    _now_ms = build_now_ms_fn(call_started_monotonic=call_started)
    tts_circuit_bridge = init_tts_circuit_bridge(
        tts=tts,
        logger_obj=logger_obj,
        provider_circuit_state_callback=provider_circuit_state_callback,
    )

    while True:
        cursor_step = turn_cursor.next_step()
        if cursor_step is None:
            break
        turn_def, turn_visit = cursor_step

        match turn_def.kind:
            case "bot_listen":
                timeout = effective_turn_timeout(turn_def, scenario)
                effective_endpointing_ms, effective_merge_window_s = effective_stt_settings(
                    turn_def,
                    scenario,
                )
                turn_number, _ = await execute_bot_listen_block(
                    turn_def=turn_def,
                    turn_number=turn_number,
                    turn_visit=turn_visit,
                    run_id=run_id,
                    conversation=conversation,
                    scenario=scenario,
                    settings_obj=settings_obj,
                    bot_listener=bot_listener,
                    timeout=timeout,
                    effective_merge_window_s=effective_merge_window_s,
                    effective_endpointing_ms=effective_endpointing_ms,
                    classify_branch_fn=classify_branch_fn,
                    classifier_client=classifier_client,
                    report_turn_fn=report_turn_fn,
                    graph_traversal=graph_traversal,
                    now_ms_fn=_now_ms,
                    emit_heartbeat_state_fn=_emit_heartbeat_state,
                    logger_obj=logger_obj,
                    scenario_kind=scenario_kind,
                )
            case "harness_prompt":
                timeout = effective_turn_timeout(turn_def, scenario)
                effective_endpointing_ms, effective_merge_window_s = effective_stt_settings(
                    turn_def,
                    scenario,
                )
                turn_number = await execute_harness_prompt_block(
                    turn_def=turn_def,
                    turn_number=turn_number,
                    turn_visit=turn_visit,
                    run_id=run_id,
                    conversation=conversation,
                    response_visit_counts=response_visit_counts,
                    scenario=scenario,
                    settings_obj=settings_obj,
                    tenant_id=tenant_id,
                    bot_listener=bot_listener,
                    audio_source=audio_source,
                    tts=tts,
                    read_cached_turn_wav_fn=read_cached_turn_wav_fn,
                    publish_cached_wav_fn=publish_cached_wav_fn,
                    timeout=timeout,
                    effective_merge_window_s=effective_merge_window_s,
                    effective_endpointing_ms=effective_endpointing_ms,
                    classify_branch_fn=classify_branch_fn,
                    classifier_client=classifier_client,
                    report_turn_fn=report_turn_fn,
                    graph_traversal=graph_traversal,
                    now_ms_fn=_now_ms,
                    emit_heartbeat_state_fn=_emit_heartbeat_state,
                    logger_obj=logger_obj,
                    tts_live_circuit_breaker=tts_live_circuit_breaker,
                    tts_circuit_bridge=tts_circuit_bridge,
                    scenario_kind=scenario_kind,
                )
            case "hangup":
                turn_number = await execute_hangup_block(
                    turn_def=turn_def,
                    turn_number=turn_number,
                    graph_traversal=graph_traversal,
                    logger_obj=logger_obj,
                )
                # Hangup is terminal — stop regardless of cursor mode.
                # In graph mode the graph already wires no successor for HangupBlock;
                # in linear mode the cursor would advance to the next turn without this break.
                break
            case "wait":
                turn_number = await execute_wait_block(
                    turn_def=turn_def,
                    turn_number=turn_number,
                    graph_traversal=graph_traversal,
                    logger_obj=logger_obj,
                )
            case "time_route":
                turn_number = await execute_time_route_block(
                    turn_def=turn_def,
                    turn_number=turn_number,
                    graph_traversal=graph_traversal,
                    logger_obj=logger_obj,
                )
            case _:
                raise RuntimeError(f"Unknown block kind: {turn_def.kind!r}")

    return conversation, turn_number
