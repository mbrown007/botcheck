from __future__ import annotations

import asyncio

from botcheck_scenarios import ConversationTurn

from .scenario_bot_listener import listen_bot_turn
from .scenario_harness_audio import play_harness_turn_audio
from .scenario_turn_helpers import classify_branch_condition


async def execute_harness_prompt_block(
    *,
    turn_def,
    turn_number: int,
    turn_visit: int,
    run_id: str,
    conversation: list[ConversationTurn],
    response_visit_counts: dict[str, int],
    scenario,
    settings_obj,
    tenant_id: str,
    bot_listener,
    audio_source,
    tts,
    read_cached_turn_wav_fn,
    publish_cached_wav_fn,
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
    tts_live_circuit_breaker=None,
    tts_circuit_bridge=None,
    scenario_kind: str = "graph",
) -> int:
    turn_number += 1
    emit_heartbeat_state_fn(turn_number=turn_number, listener_state="speaking_harness")

    chosen_branch_condition = "default"
    branch_response_snippet: str | None = None
    retry_budget = max(0, int(getattr(turn_def.config, "retry_on_silence", 0)))

    async def _play_prompt_attempt(*, include_pre_pause: bool) -> tuple[int, int]:
        if include_pre_pause:
            pre_pause = scenario.config.inter_turn_pause_s + turn_def.config.pre_speak_pause_s
            if pre_pause > 0:
                await asyncio.sleep(pre_pause)
        start_ms = now_ms_fn()
        if turn_def.content.text:
            _playback = await play_harness_turn_audio(
                turn_number=turn_number,
                turn_def=turn_def,
                scenario=scenario,
                tenant_id=tenant_id,
                audio_source=audio_source,
                tts=tts,
                read_cached_turn_wav_fn=read_cached_turn_wav_fn,
                publish_cached_wav_fn=publish_cached_wav_fn,
                tts_live_circuit_breaker=tts_live_circuit_breaker,
                tts_circuit_bridge=tts_circuit_bridge,
                logger_obj=logger_obj,
                scenario_kind=scenario_kind,
                synthesis_timeout_s=float(
                    getattr(settings_obj, "tts_ai_scenario_synthesis_timeout_s", 30.0)
                ),
            )
        elif turn_def.content.silence_s:
            await asyncio.sleep(turn_def.content.silence_s)
        elif turn_def.content.audio_file:
            raise RuntimeError(
                f"Harness prompt block '{turn_def.id}' uses audio_file, which is not implemented yet"
            )
        elif turn_def.content.dtmf:
            raise RuntimeError(
                f"Harness prompt block '{turn_def.id}' uses dtmf, which is not implemented yet"
            )
        end_ms = now_ms_fn()
        if turn_def.config.post_speak_pause_s > 0:
            await asyncio.sleep(turn_def.config.post_speak_pause_s)
        return start_ms, end_ms

    bot_turn = None
    first_start_ms: int | None = None
    last_end_ms: int | None = None
    attempt = 0
    while True:
        attempt_start_ms, attempt_end_ms = await _play_prompt_attempt(
            include_pre_pause=(attempt == 0)
        )
        if first_start_ms is None:
            first_start_ms = attempt_start_ms
        last_end_ms = attempt_end_ms

        if not turn_def.listen:
            break

        emit_heartbeat_state_fn(turn_number=turn_number + 1, listener_state="awaiting_bot")
        # preview_callback intentionally omitted: graph scenarios have no AI caller
        # planning loop, so preview events serve no purpose here.
        bot_turn = await listen_bot_turn(
            bot_listener=bot_listener,
            timeout_s=timeout,
            merge_window_s=effective_merge_window_s,
            stt_endpointing_ms=effective_endpointing_ms,
            listen_for_s=getattr(turn_def.config, "listen_for_s", None),
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=now_ms_fn,
            logger_obj=logger_obj,
            scenario_kind=scenario_kind,
        )
        if bot_turn.text != "(timeout)" or attempt >= retry_budget:
            break
        attempt += 1
        logger_obj.info(
            "Turn %s timed out; replaying harness prompt (%d/%d)",
            turn_def.id,
            attempt,
            retry_budget,
        )

    # The loop executes at least once, so both timestamps are always set.
    assert first_start_ms is not None and last_end_ms is not None
    harness_turn = ConversationTurn(
        turn_id=turn_def.id,
        turn_number=turn_number,
        speaker="harness",
        text=turn_def.content.text or "",
        audio_start_ms=first_start_ms,
        audio_end_ms=last_end_ms,
        adversarial=turn_def.adversarial,
        technique=turn_def.technique.value if turn_def.technique else None,
    )
    conversation.append(harness_turn)
    harness_reported = False

    if not turn_def.listen:
        await report_turn_fn(
            run_id,
            harness_turn,
            visit=turn_visit,
            branch_condition_matched=(chosen_branch_condition if turn_def.branching is not None else None),
        )
        if graph_traversal is not None:
            graph_traversal.advance(chosen_branch_condition)
        return turn_number

    assert bot_turn is not None
    turn_number += 1
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

    if turn_def.branching is None:
        await report_turn_fn(
            run_id,
            harness_turn,
            visit=turn_visit,
        )
        harness_reported = True

    if not harness_reported:
        await report_turn_fn(
            run_id,
            harness_turn,
            visit=turn_visit,
            branch_condition_matched=(chosen_branch_condition if turn_def.branching is not None else None),
            branch_response_snippet=branch_response_snippet,
        )

    response_visit_counts[bot_turn.turn_id] += 1
    await report_turn_fn(
        run_id,
        bot_turn,
        visit=response_visit_counts[bot_turn.turn_id],
    )

    if graph_traversal is not None:
        graph_traversal.advance(chosen_branch_condition)
    return turn_number
