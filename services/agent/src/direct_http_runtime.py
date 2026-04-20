from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from copy import deepcopy
from typing import Awaitable, Callable

from botcheck_scenarios import ConversationTurn

from .ai_caller_policy import AICallerDecision, generate_next_ai_caller_decision
from .direct_http import DirectHTTPBotClient
from .metrics import AI_CALLER_REPLY_LATENCY_SECONDS
from .playground_ai_debug import emit_ai_debug_events
from .scenario_ai_loop import (
    _ai_dispatch_context,
    _ai_stop_signal,
    _style_caller_prompt,
    ai_fast_ack_allowed,
    generate_ai_followup_prompt,
    initial_ai_fast_ack_prompt,
    resolve_ai_decision_with_fast_ack,
)
from .scenario_turn_cursor import create_turn_cursor
from .scenario_turn_helpers import (
    ai_prompt_block,
    classify_branch_condition,
    effective_turn_timeout,
    scenario_prompt_text,
)


def _expectation_events(
    *,
    turn_def,
    bot_text: str,
) -> list[dict[str, object]]:
    expect = getattr(turn_def, "expect", None)
    if expect is None:
        return []
    lowered = str(bot_text or "").lower()
    results: list[dict[str, object]] = []
    forbidden = list(getattr(expect, "no_forbidden_phrase", None) or [])
    if forbidden:
        results.append(
            {
                "assertion": "no_forbidden_phrase",
                "passed": all(str(phrase).lower() not in lowered for phrase in forbidden),
                "detail": forbidden,
            }
        )
    transferred_to = str(getattr(expect, "transferred_to", "") or "").strip()
    if transferred_to:
        results.append(
            {
                "assertion": "transferred_to",
                "passed": transferred_to.lower() in lowered,
                "detail": transferred_to,
            }
        )
    call_ended_by_bot = getattr(expect, "call_ended_by_bot", None)
    if call_ended_by_bot is not None:
        results.append(
            {
                "assertion": "call_ended_by_bot",
                "passed": bool(_ai_stop_signal(bot_text)) == bool(call_ended_by_bot),
                "detail": bool(call_ended_by_bot),
            }
        )
    return results


async def _emit_turn_expectations(
    *,
    emitter,
    turn_def,
    bot_text: str,
    turn_id: str,
) -> None:
    for result in _expectation_events(turn_def=turn_def, bot_text=bot_text):
        await emitter.emit(
            "turn.expect",
            {
                "turn_id": turn_id,
                "assertion": result["assertion"],
                "passed": result["passed"],
                "detail": result["detail"],
            },
        )


async def _request_bot_turn(
    *,
    client: DirectHTTPBotClient,
    prompt: str,
    conversation: list[ConversationTurn],
    run_id: str,
    turn_id: str,
    turn_number: int,
    now_ms_fn: Callable[[], int],
    request_context: dict[str, object] | None = None,
) -> ConversationTurn:
    start_ms = now_ms_fn()
    response = await client.respond(
        prompt=prompt,
        conversation=conversation,
        session_id=run_id,
        request_context=request_context,
    )
    end_ms = now_ms_fn()
    # When the call-timer resolution truncates to 0 (fast local endpoints), fall back to
    # the latency measured inside client.respond() which uses monotonic time directly.
    if end_ms <= start_ms and response.latency_ms > 0:
        end_ms = start_ms + response.latency_ms
    bot_turn = ConversationTurn(
        turn_id=turn_id,
        turn_number=turn_number,
        speaker="bot",
        text=response.text,
        audio_start_ms=start_ms,
        audio_end_ms=max(end_ms, start_ms),
    )
    conversation.append(bot_turn)
    return bot_turn


async def execute_direct_http_scenario_loop(
    *,
    client: DirectHTTPBotClient,
    scenario,
    run_id: str,
    settings_obj,
    report_turn_fn,
    classify_branch_fn,
    classifier_client,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    scenario_kind: str = "graph",
    event_emitter=None,
) -> tuple[list[ConversationTurn], int]:
    del scenario_kind
    conversation: list[ConversationTurn] = []
    response_visit_counts: dict[str, int] = defaultdict(int)
    turn_number = 0
    call_started = time.monotonic()
    request_context = deepcopy(dict(getattr(scenario, "http_request_context", {}) or {}))
    turn_cursor, graph_traversal = create_turn_cursor(
        scenario=scenario,
        enable_branching_graph=settings_obj.enable_branching_graph,
        max_total_turns_hard_cap=settings_obj.max_total_turns_hard_cap,
    )

    def _emit(turn_number: int | None = None, listener_state: str | None = None) -> None:
        if heartbeat_state_callback is not None:
            heartbeat_state_callback(turn_number, listener_state)

    def _now_ms() -> int:
        return int((time.monotonic() - call_started) * 1000)

    while True:
        cursor_step = turn_cursor.next_step()
        if cursor_step is None:
            break
        turn_def, turn_visit = cursor_step
        timeout = effective_turn_timeout(turn_def, scenario)
        del timeout  # HTTP transport uses per-profile timeout; turn timeout remains future work.

        if turn_def.kind == "bot_listen":
            turn_number += 1
            _emit(turn_number, "awaiting_bot")
            if event_emitter is not None:
                await event_emitter.emit(
                    "turn.start",
                    {
                        "turn_id": turn_def.id,
                        "speaker": "bot",
                        "text": "",
                    },
                )
            if turn_def.config.pre_listen_wait_s > 0:
                await asyncio.sleep(turn_def.config.pre_listen_wait_s)
            bot_turn = await _request_bot_turn(
                client=client,
                prompt="",
                conversation=conversation,
                run_id=run_id,
                turn_id=turn_def.id,
                turn_number=turn_number,
                now_ms_fn=_now_ms,
                request_context=request_context,
            )
            if event_emitter is not None:
                await event_emitter.emit(
                    "turn.response",
                    {
                        "turn_id": bot_turn.turn_id,
                        "transcript": bot_turn.text,
                        "latency_ms": max(0, bot_turn.audio_end_ms - bot_turn.audio_start_ms),
                    },
                )
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
                branch_condition_matched=(
                    chosen_branch_condition if turn_def.branching is not None else None
                ),
                branch_response_snippet=branch_response_snippet,
            )
            if event_emitter is not None and turn_def.branching is not None:
                await event_emitter.emit(
                    "turn.branch",
                    {
                        "turn_id": turn_def.id,
                        "selected_case": chosen_branch_condition,
                    },
                )
            if event_emitter is not None:
                await _emit_turn_expectations(
                    emitter=event_emitter,
                    turn_def=turn_def,
                    bot_text=bot_turn.text,
                    turn_id=bot_turn.turn_id,
                )
            if graph_traversal is not None:
                graph_traversal.advance(chosen_branch_condition)
            continue

        turn_number += 1
        _emit(turn_number, "sending_direct_request")
        pre_pause = scenario.config.inter_turn_pause_s + turn_def.config.pre_speak_pause_s
        if pre_pause > 0:
            await asyncio.sleep(pre_pause)
        start_ms = _now_ms()
        end_ms = start_ms
        if turn_def.kind == "hangup":
            break
        prompt_text = scenario_prompt_text(turn_def)
        if prompt_text:
            end_ms = _now_ms()
        elif turn_def.content.silence_s:
            await asyncio.sleep(turn_def.content.silence_s)
            end_ms = _now_ms()
        if turn_def.config.post_speak_pause_s > 0:
            await asyncio.sleep(turn_def.config.post_speak_pause_s)

        harness_turn = ConversationTurn(
            turn_id=turn_def.id,
            turn_number=turn_number,
            speaker="harness",
            text=prompt_text,
            audio_start_ms=start_ms,
            audio_end_ms=end_ms,
            adversarial=turn_def.adversarial,
            technique=turn_def.technique.value if turn_def.technique else None,
        )
        conversation.append(harness_turn)
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.start",
                {
                    "turn_id": harness_turn.turn_id,
                    "speaker": "harness",
                    "text": harness_turn.text,
                },
            )
            await event_emitter.emit(
                "turn.response",
                {
                    "turn_id": harness_turn.turn_id,
                    "transcript": harness_turn.text,
                    "latency_ms": max(0, harness_turn.audio_end_ms - harness_turn.audio_start_ms),
                },
            )
        harness_reported = False

        if not turn_def.listen:
            await report_turn_fn(run_id, harness_turn, visit=turn_visit)
            if graph_traversal is not None:
                graph_traversal.advance("default")
            continue

        if turn_def.branching is None:
            await report_turn_fn(run_id, harness_turn, visit=turn_visit)
            harness_reported = True

        _emit(turn_number + 1, "awaiting_bot")
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.start",
                {
                    "turn_id": f"{turn_def.id}_bot",
                    "speaker": "bot",
                    "text": "",
                },
            )
        bot_turn = await _request_bot_turn(
            client=client,
            prompt=prompt_text,
            conversation=conversation,
            run_id=run_id,
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=_now_ms,
            request_context=request_context,
        )
        turn_number += 1
        response_visit_counts[bot_turn.turn_id] += 1
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.response",
                {
                    "turn_id": bot_turn.turn_id,
                    "transcript": bot_turn.text,
                    "latency_ms": max(0, bot_turn.audio_end_ms - bot_turn.audio_start_ms),
                },
            )
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
        if not harness_reported:
            await report_turn_fn(
                run_id,
                harness_turn,
                visit=turn_visit,
                branch_condition_matched=(
                    chosen_branch_condition if turn_def.branching is not None else None
                ),
                branch_response_snippet=branch_response_snippet,
            )
        await report_turn_fn(
            run_id,
            bot_turn,
            visit=response_visit_counts[bot_turn.turn_id],
        )
        if event_emitter is not None and turn_def.branching is not None:
            await event_emitter.emit(
                "turn.branch",
                {
                    "turn_id": turn_def.id,
                    "selected_case": chosen_branch_condition,
                },
            )
        if event_emitter is not None:
            await _emit_turn_expectations(
                emitter=event_emitter,
                turn_def=turn_def,
                bot_text=bot_turn.text,
                turn_id=bot_turn.turn_id,
            )
        if graph_traversal is not None:
            graph_traversal.advance(chosen_branch_condition)

    return conversation, turn_number


async def execute_direct_http_ai_loop(
    *,
    client: DirectHTTPBotClient,
    scenario,
    run_id: str,
    settings_obj,
    report_turn_fn,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    run_metadata: dict[str, object] | None = None,
    ai_caller_generate_fn: Callable[..., Awaitable[str | None]] | None = None,
    scenario_kind: str = "ai",
    event_emitter=None,
) -> tuple[list[ConversationTurn], int]:
    del scenario_kind
    conversation: list[ConversationTurn] = []
    response_visit_counts: dict[str, int] = defaultdict(int)
    turn_number = 0
    call_started = time.monotonic()
    request_context = deepcopy(dict(getattr(scenario, "http_request_context", {}) or {}))

    max_total_turns = max(1, int(scenario.config.max_total_turns))
    max_turn_cap = max(1, int(settings_obj.max_total_turns_hard_cap))
    ai_dispatch = _ai_dispatch_context(run_metadata)
    objective_hint = ai_dispatch.objective_hint()
    persona_name = ai_dispatch.ai_persona_name or ""
    opening_strategy = ai_dispatch.effective_opening_strategy()
    use_llm = bool(getattr(settings_obj, "ai_caller_use_llm", True))
    fast_ack_enabled = bool(getattr(settings_obj, "ai_voice_fast_ack_enabled", False))
    fast_ack_trigger_s = float(getattr(settings_obj, "ai_voice_fast_ack_trigger_s", 0.6))
    if opening_strategy == "caller_opens" and not use_llm:
        if not scenario.turns or not scenario_prompt_text(scenario.turns[0]).strip():
            raise ValueError("AI runtime scenario with caller_opens requires a dataset input turn.")

    max_pairs = max(1, min(max_total_turns // 2, max_turn_cap // 2))
    next_prompt_source = "dataset_input"

    def _emit(turn_number: int | None = None, listener_state: str | None = None) -> None:
        if heartbeat_state_callback is not None:
            heartbeat_state_callback(turn_number, listener_state)

    def _now_ms() -> int:
        return int((time.monotonic() - call_started) * 1000)

    next_prompt = scenario_prompt_text(scenario.turns[0]) if scenario.turns else ""
    dataset_input_prompt = next_prompt.strip()
    model = str(getattr(settings_obj, "ai_caller_model", "gpt-4o-mini"))
    timeout_s = float(getattr(settings_obj, "ai_caller_timeout_s", 4.0))
    api_base_url = str(getattr(settings_obj, "ai_caller_api_base_url", "https://api.openai.com/v1"))
    max_context_turns = int(getattr(settings_obj, "ai_caller_max_context_turns", 8))
    logger_obj = logging.getLogger(__name__)

    async def _next_ai_decision(last_bot_text: str) -> AICallerDecision:
        if ai_caller_generate_fn is not None:
            utterance = await ai_caller_generate_fn(
                openai_api_key=str(getattr(settings_obj, "openai_api_key", "")),
                model=model,
                timeout_s=timeout_s,
                api_base_url=api_base_url,
                scenario=scenario,
                conversation=conversation,
                last_bot_text=last_bot_text,
                objective_hint=objective_hint,
                persona_name=persona_name,
                max_context_turns=max_context_turns,
                circuit_breaker=None,
                on_circuit_transition=None,
                on_circuit_reject=None,
            )
            if utterance:
                return AICallerDecision(
                    action="continue",
                    utterance=utterance,
                    reasoning_summary="Continuing based on the latest bot reply and the scenario objective.",
                    confidence=None,
                )
            return AICallerDecision(
                action="end",
                utterance=None,
                reasoning_summary="Ending because the caller objective appears satisfied.",
                confidence=None,
            )
        return await generate_next_ai_caller_decision(
            openai_api_key=str(getattr(settings_obj, "openai_api_key", "")),
            model=model,
            timeout_s=timeout_s,
            api_base_url=api_base_url,
            scenario=scenario,
            conversation=conversation,
            last_bot_text=last_bot_text,
            objective_hint=objective_hint,
            persona_name=persona_name,
            max_context_turns=max_context_turns,
            circuit_breaker=None,
            on_circuit_transition=None,
            on_circuit_reject=None,
        )

    if opening_strategy == "wait_for_bot_greeting":
        _emit(1, "awaiting_bot")
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.start",
                {
                    "turn_id": "ai_initial_bot",
                    "speaker": "bot",
                    "text": "",
                },
            )
        bot_turn = await _request_bot_turn(
            client=client,
            prompt="",
            conversation=conversation,
            run_id=run_id,
            turn_id="ai_initial_bot",
            turn_number=1,
            now_ms_fn=_now_ms,
            request_context=request_context,
        )
        turn_number = 1
        response_visit_counts[bot_turn.turn_id] += 1
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.response",
                {
                    "turn_id": bot_turn.turn_id,
                    "transcript": bot_turn.text,
                    "latency_ms": max(0, bot_turn.audio_end_ms - bot_turn.audio_start_ms),
                },
            )
        await report_turn_fn(run_id, bot_turn, visit=1)
        if use_llm:
            decision, next_prompt_source = await resolve_ai_decision_with_fast_ack(
                generate_decision_fn=lambda bt=bot_turn.text: _next_ai_decision(bt),
                fallback_prompt=initial_ai_fast_ack_prompt(
                    opening_strategy=opening_strategy,
                    dataset_input_prompt=dataset_input_prompt,
                    use_llm=use_llm,
                    fast_ack_enabled=fast_ack_enabled,
                    objective_hint=objective_hint,
                ),
                fast_ack_source="dataset_input",
                fast_ack_trigger_s=fast_ack_trigger_s,
                opening_strategy=opening_strategy,
                scenario_kind="ai",
                logger_obj=logger_obj,
                run_id=run_id,
            )
            await emit_ai_debug_events(
                event_emitter=event_emitter,
                bot_transcript=bot_turn.text,
                decision=decision,
            )
            if decision.action == "continue" and decision.utterance:
                next_prompt = decision.utterance
            else:
                next_prompt = ""

    for pair_index in range(max_pairs):
        if not next_prompt.strip():
            break

        turn_def = ai_prompt_block(
            turn_id=("ai_record_input" if pair_index == 0 else f"ai_followup_{pair_index}"),
            prompt_text=next_prompt.strip(),
        )
        turn_number += 1
        _emit(turn_number, "sending_direct_request")
        pre_pause = scenario.config.inter_turn_pause_s + turn_def.config.pre_speak_pause_s
        if pre_pause > 0:
            await asyncio.sleep(pre_pause)
        start_ms = _now_ms()
        previous_turn = conversation[-1] if conversation else None
        if previous_turn is not None and previous_turn.speaker == "bot":
            AI_CALLER_REPLY_LATENCY_SECONDS.labels(
                opening_strategy=opening_strategy,
                source=next_prompt_source,
                scenario_kind="ai",
            ).observe(max(0.0, float(start_ms - previous_turn.audio_end_ms) / 1000.0))
        end_ms = _now_ms()
        harness_turn = ConversationTurn(
            turn_id=turn_def.id,
            turn_number=turn_number,
            speaker="harness",
            text=turn_def.content.text or "",
            audio_start_ms=start_ms,
            audio_end_ms=end_ms,
        )
        conversation.append(harness_turn)
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.start",
                {
                    "turn_id": harness_turn.turn_id,
                    "speaker": "harness",
                    "text": harness_turn.text,
                },
            )
            await event_emitter.emit(
                "turn.response",
                {
                    "turn_id": harness_turn.turn_id,
                    "transcript": harness_turn.text,
                    "latency_ms": max(0, harness_turn.audio_end_ms - harness_turn.audio_start_ms),
                },
            )
        await report_turn_fn(run_id, harness_turn, visit=1)

        _emit(turn_number + 1, "awaiting_bot")
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.start",
                {
                    "turn_id": f"{turn_def.id}_bot",
                    "speaker": "bot",
                    "text": "",
                },
            )
        bot_turn = await _request_bot_turn(
            client=client,
            prompt=turn_def.content.text or "",
            conversation=conversation,
            run_id=run_id,
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=_now_ms,
            request_context=request_context,
        )
        turn_number += 1
        response_visit_counts[bot_turn.turn_id] += 1
        if event_emitter is not None:
            await event_emitter.emit(
                "turn.response",
                {
                    "turn_id": bot_turn.turn_id,
                    "transcript": bot_turn.text,
                    "latency_ms": max(0, bot_turn.audio_end_ms - bot_turn.audio_start_ms),
                },
            )
        await report_turn_fn(run_id, bot_turn, visit=response_visit_counts[bot_turn.turn_id])

        if _ai_stop_signal(bot_turn.text):
            break

        if use_llm:
            heuristic_fast_ack_prompt = (
                generate_ai_followup_prompt(
                    last_bot_text=bot_turn.text,
                    conversation=conversation,
                    scenario=scenario,
                    objective_hint=objective_hint,
                    persona_name=persona_name,
                )
                if ai_fast_ack_allowed(
                    use_llm=use_llm,
                    fast_ack_enabled=fast_ack_enabled,
                    objective_hint=objective_hint,
                )
                else None
            )
            decision, next_prompt_source = await resolve_ai_decision_with_fast_ack(
                generate_decision_fn=lambda bt=bot_turn.text: _next_ai_decision(bt),
                fallback_prompt=heuristic_fast_ack_prompt,
                fast_ack_source="heuristic",
                fast_ack_trigger_s=fast_ack_trigger_s,
                opening_strategy=opening_strategy,
                scenario_kind="ai",
                logger_obj=logger_obj,
                run_id=run_id,
            )
            await emit_ai_debug_events(
                event_emitter=event_emitter,
                bot_transcript=bot_turn.text,
                decision=decision,
            )
            next_prompt = decision.utterance or ""
        else:
            if "anything else" in bot_turn.text.lower():
                next_prompt = _style_caller_prompt(
                    base="No, that's all I needed. Thank you.",
                    scenario=scenario,
                )
            else:
                next_prompt = ""
                next_prompt_source = "dataset_input"

    return conversation, turn_number
