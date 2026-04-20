from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from botcheck_scenarios import ConversationTurn

from .ai_caller_policy import AICallerDecision, generate_next_ai_caller_decision
from .direct_http import DirectHTTPBotClient, DirectHTTPTransportContext
from .direct_http_runtime import (
    execute_direct_http_ai_loop,
    execute_direct_http_scenario_loop,
)
from .mock_agent import MockAgent
from .playground_ai_debug import emit_ai_debug_events
from .playground_events import PlaygroundEventEmitter
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


class PlaygroundRunContext(BaseModel):
    run_id: str
    transport_profile_id: str | None = None
    endpoint: str | None = None
    headers: dict[str, object] = Field(default_factory=dict)
    direct_http_config: dict[str, object] = Field(default_factory=dict)
    playground_mode: str | None = None
    playground_system_prompt: str | None = None
    playground_tool_stubs: dict[str, object] | None = None


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


def _conversation_as_history(conversation: list[ConversationTurn]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in conversation:
        role = "assistant" if turn.speaker == "bot" else "user"
        text = str(turn.text or "").strip()
        if text:
            history.append({"role": role, "content": text})
    return history


def _compose_mock_system_prompt(
    *,
    base_prompt: str,
    tool_stubs: dict[str, object] | None,
) -> str:
    prompt = str(base_prompt or "").strip()
    if not tool_stubs:
        return prompt
    lines = [
        prompt,
        "",
        "Available tool stub returns for this playground session:",
    ]
    for name, value in tool_stubs.items():
        lines.append(f"- {name}: {json.dumps(value, sort_keys=True)}")
    lines.append(
        "If you mention or rely on a tool result, use only the stubbed values above."
    )
    return "\n".join(line for line in lines if line)


def _mock_turn_prompt(*, prompt: str, conversation: list[ConversationTurn]) -> str:
    candidate = str(prompt or "").strip()
    if candidate:
        return candidate
    if conversation:
        return "Continue the conversation appropriately."
    return "Start the conversation with an appropriate opening line."


async def _request_mock_bot_turn(
    *,
    mock_agent,
    system_prompt: str,
    tool_stubs: dict[str, object] | None,
    prompt: str,
    conversation: list[ConversationTurn],
    turn_id: str,
    turn_number: int,
    now_ms_fn: Callable[[], int],
) -> ConversationTurn:
    start_ms = now_ms_fn()
    response_text = await mock_agent.respond(
        _compose_mock_system_prompt(base_prompt=system_prompt, tool_stubs=tool_stubs),
        _conversation_as_history(conversation),
        _mock_turn_prompt(prompt=prompt, conversation=conversation),
    )
    end_ms = now_ms_fn()
    bot_turn = ConversationTurn(
        turn_id=turn_id,
        turn_number=turn_number,
        speaker="bot",
        text=response_text,
        audio_start_ms=start_ms,
        audio_end_ms=max(end_ms, start_ms),
    )
    conversation.append(bot_turn)
    return bot_turn


async def _execute_mock_scenario_loop(
    *,
    mock_agent,
    system_prompt: str,
    tool_stubs: dict[str, object] | None,
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
    turn_cursor, graph_traversal = create_turn_cursor(
        scenario=scenario,
        enable_branching_graph=settings_obj.enable_branching_graph,
        max_total_turns_hard_cap=settings_obj.max_total_turns_hard_cap,
    )

    def _emit(next_turn_number: int | None = None, listener_state: str | None = None) -> None:
        if heartbeat_state_callback is not None:
            heartbeat_state_callback(next_turn_number, listener_state)

    def _now_ms() -> int:
        return int((time.monotonic() - call_started) * 1000)

    while True:
        cursor_step = turn_cursor.next_step()
        if cursor_step is None:
            break
        turn_def, turn_visit = cursor_step
        timeout = effective_turn_timeout(turn_def, scenario)
        del timeout

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
            bot_turn = await _request_mock_bot_turn(
                mock_agent=mock_agent,
                system_prompt=system_prompt,
                tool_stubs=tool_stubs,
                prompt="",
                conversation=conversation,
                turn_id=turn_def.id,
                turn_number=turn_number,
                now_ms_fn=_now_ms,
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
        _emit(turn_number, "sending_playground_prompt")
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
            conversation.append(harness_turn)
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
        # Do NOT add harness_turn to conversation before this call — it would
        # duplicate the harness text (history already reflected by prompt_text).
        # Insert it after, just before the bot reply.
        bot_turn = await _request_mock_bot_turn(
            mock_agent=mock_agent,
            system_prompt=system_prompt,
            tool_stubs=tool_stubs,
            prompt=prompt_text,
            conversation=conversation,
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=_now_ms,
        )
        conversation.insert(len(conversation) - 1, harness_turn)
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


async def _execute_mock_ai_loop(
    *,
    mock_agent,
    system_prompt: str,
    tool_stubs: dict[str, object] | None,
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

    def _emit(next_turn_number: int | None = None, listener_state: str | None = None) -> None:
        if heartbeat_state_callback is not None:
            heartbeat_state_callback(next_turn_number, listener_state)

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
        bot_turn = await _request_mock_bot_turn(
            mock_agent=mock_agent,
            system_prompt=system_prompt,
            tool_stubs=tool_stubs,
            prompt="",
            conversation=conversation,
            turn_id="ai_initial_bot",
            turn_number=1,
            now_ms_fn=_now_ms,
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
        _emit(turn_number, "sending_playground_prompt")
        pre_pause = scenario.config.inter_turn_pause_s + turn_def.config.pre_speak_pause_s
        if pre_pause > 0:
            await asyncio.sleep(pre_pause)
        start_ms = _now_ms()
        end_ms = _now_ms()
        harness_turn = ConversationTurn(
            turn_id=turn_def.id,
            turn_number=turn_number,
            speaker="harness",
            text=turn_def.content.text or "",
            audio_start_ms=start_ms,
            audio_end_ms=end_ms,
        )
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
        # Do NOT add harness_turn to conversation before this call — same reason
        # as the graph loop: defer to avoid duplicating harness text in LLM context.
        bot_turn = await _request_mock_bot_turn(
            mock_agent=mock_agent,
            system_prompt=system_prompt,
            tool_stubs=tool_stubs,
            prompt=turn_def.content.text or "",
            conversation=conversation,
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=_now_ms,
        )
        conversation.insert(len(conversation) - 1, harness_turn)
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


async def execute_playground_loop(
    *,
    scenario,
    run_id: str,
    settings_obj,
    report_turn_fn,
    classify_branch_fn,
    classifier_client,
    fetch_run_transport_context_fn,
    run_metadata: dict[str, object] | None = None,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    mock_agent_cls=MockAgent,
    ai_caller_generate_fn: Callable[..., Awaitable[str | None]] | None = None,
    post_playground_event_fn=None,
    playground_event_emitter_cls=PlaygroundEventEmitter,
) -> tuple[list[ConversationTurn], int]:
    if fetch_run_transport_context_fn is None:
        raise RuntimeError("Playground runs require fetch_run_transport_context_fn")
    if post_playground_event_fn is None:
        raise RuntimeError("Playground runs require post_playground_event_fn")
    context = PlaygroundRunContext.model_validate(await fetch_run_transport_context_fn(run_id))
    raw_mode = (
        str((run_metadata or {}).get("playground_mode") or context.playground_mode or "")
        .strip()
        .lower()
    )
    event_emitter = playground_event_emitter_cls(
        run_id=run_id,
        post_event_fn=post_playground_event_fn,
    )

    if raw_mode == "direct_http":
        client = DirectHTTPBotClient(
            context=DirectHTTPTransportContext.model_validate(context.model_dump())
        )
        try:
            if "__ai_runtime__" in scenario.tags:
                conversation, turn_number = await execute_direct_http_ai_loop(
                    client=client,
                    scenario=scenario,
                    run_id=run_id,
                    settings_obj=settings_obj,
                    report_turn_fn=report_turn_fn,
                    heartbeat_state_callback=heartbeat_state_callback,
                    run_metadata=run_metadata,
                    ai_caller_generate_fn=ai_caller_generate_fn,
                    event_emitter=event_emitter,
                )
            else:
                conversation, turn_number = await execute_direct_http_scenario_loop(
                    client=client,
                    scenario=scenario,
                    run_id=run_id,
                    settings_obj=settings_obj,
                    report_turn_fn=report_turn_fn,
                    classify_branch_fn=classify_branch_fn,
                    classifier_client=classifier_client,
                    heartbeat_state_callback=heartbeat_state_callback,
                    scenario_kind="ai" if "__ai_runtime__" in scenario.tags else "graph",
                    event_emitter=event_emitter,
                )
            await event_emitter.emit(
                "run.complete",
                {
                    "run_id": run_id,
                    "gate_passed": None,
                    "summary": f"Playground run completed after {turn_number} turns.",
                },
            )
            return conversation, turn_number
        finally:
            await client.aclose()

    if raw_mode != "mock":
        raise RuntimeError(f"Unsupported playground mode: {raw_mode or '<missing>'}")

    system_prompt = str(context.playground_system_prompt or "").strip()
    if not system_prompt:
        raise RuntimeError("Mock playground context missing system prompt.")
    tool_stubs = dict(context.playground_tool_stubs or {}) or None
    mock_agent = mock_agent_cls(settings_obj=settings_obj)

    if "__ai_runtime__" in scenario.tags:
        conversation, turn_number = await _execute_mock_ai_loop(
            mock_agent=mock_agent,
            system_prompt=system_prompt,
            tool_stubs=tool_stubs,
            scenario=scenario,
            run_id=run_id,
            settings_obj=settings_obj,
            report_turn_fn=report_turn_fn,
            heartbeat_state_callback=heartbeat_state_callback,
            run_metadata=run_metadata,
            ai_caller_generate_fn=ai_caller_generate_fn,
            scenario_kind="ai",
            event_emitter=event_emitter,
        )
    else:
        conversation, turn_number = await _execute_mock_scenario_loop(
            mock_agent=mock_agent,
            system_prompt=system_prompt,
            tool_stubs=tool_stubs,
            scenario=scenario,
            run_id=run_id,
            settings_obj=settings_obj,
            report_turn_fn=report_turn_fn,
            classify_branch_fn=classify_branch_fn,
            classifier_client=classifier_client,
            heartbeat_state_callback=heartbeat_state_callback,
            scenario_kind="graph",
            event_emitter=event_emitter,
        )
    await event_emitter.emit(
        "run.complete",
        {
            "run_id": run_id,
            "gate_passed": None,
            "summary": f"Playground run completed after {turn_number} turns.",
        },
    )
    return conversation, turn_number
