from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, TypeAlias

from botcheck_scenarios import (
    AIRunDispatchContext,
    ConversationTurn,
)

from .ai_caller_policy import AICallerDecision, generate_next_ai_caller_utterance
from .loop_runtime_helpers import (
    build_heartbeat_state_emitter,
    build_now_ms_fn,
    init_tts_circuit_bridge,
)
from .media_engine import AgentAiCallerCircuitBridge
from .metrics import (
    AI_CALLER_DECISION_LATENCY_SECONDS,
    AI_CALLER_DECISION_TO_PLAYBACK_START_GAP_SECONDS,
    AI_CALLER_LLM_REQUEST_START_GAP_SECONDS,
    AI_CALLER_REPLY_LATENCY_SECONDS,
    AI_VOICE_EARLY_PLAYBACK_TOTAL,
    AI_VOICE_FAST_ACK_TOTAL,
    AI_VOICE_PREVIEW_EVENTS_TOTAL,
    AI_VOICE_SPECULATIVE_PLANS_TOTAL,
)
from .scenario_bot_listener import listen_bot_turn
from .scenario_harness_audio import HarnessPlaybackResult, play_harness_turn_audio
from .scenario_turn_helpers import ai_prompt_block, scenario_prompt_text

INITIAL_BOT_GREETING_MERGE_WINDOW_S = 3.0
INITIAL_BOT_GREETING_ENDPOINTING_MS = 3500
FastAckSource: TypeAlias = Literal["dataset_input", "heuristic"]


@dataclass(slots=True)
class _SpeculativePlan:
    preview_text: str
    started_monotonic: float
    task: "asyncio.Task[str | None]"


@dataclass(slots=True)
class _EarlyPlaybackAttempt:
    epoch: int
    target_turn_id: str
    target_turn_number: int
    preview_text: str
    prompt_text: str
    prompt_ready_monotonic: float
    llm_started_monotonic: float
    playback_started_monotonic: float
    start_ms: int
    cancel_event: asyncio.Event
    task: "asyncio.Task[tuple[object, int]]"


@dataclass(slots=True)
class _CommittedEarlyPlayback:
    attempt: _EarlyPlaybackAttempt
    end_ms: int


def _metadata_text(metadata: dict[str, object] | None, key: str) -> str:
    if metadata is None:
        return ""
    raw = metadata.get(key)
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""
    return str(raw).strip()


def _ai_dispatch_context(metadata: dict[str, object] | None) -> AIRunDispatchContext:
    return AIRunDispatchContext.model_validate(metadata or {})


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _preview_text_is_eligible(*, text: str, min_chars: int) -> bool:
    normalized = _normalize(text)
    if len(normalized) < max(1, min_chars):
        return False
    return any(char.isalpha() for char in normalized)


def _preview_matches_final(*, preview_text: str, final_text: str) -> bool:
    preview = _normalize(preview_text)
    final = _normalize(final_text)
    if not preview or not final:
        return False
    # Only commit when the preview is a leading prefix of (or equal to) the final
    # transcript. Dropping the reverse arm (preview.startswith(final)) avoids
    # committing a plan built from a longer preview context when the bot actually
    # said something shorter and different.
    return preview == final or final.startswith(preview)


def _ai_stop_signal(bot_text: str) -> bool:
    normalized = _normalize(bot_text)
    if not normalized:
        return False
    stop_markers = (
        "goodbye",
        "bye",
        "thanks for calling",
        "thank you for calling",
        "have a great day",
        "anything else i can help",
    )
    return any(marker in normalized for marker in stop_markers)


def _objective_disallows_fast_ack(objective_hint: str) -> bool:
    normalized = _normalize(objective_hint)
    if not normalized:
        return False
    # Pad with spaces for whole-word matching to prevent single-word markers
    # from matching as substrings (e.g. "reopening" matching "opening").
    # Markers are intentionally broad: when in doubt suppress fast-ack so the
    # harness behaves naturally rather than injecting a scripted response.
    padded = f" {normalized} "
    markers = (
        " opening ",
        " opener ",
        "initial greeting",
        " greeting ",
        " silence ",
        "dead air",
        " pause ",
        " hesitation ",
    )
    return any(marker in padded for marker in markers)


def ai_fast_ack_allowed(
    *,
    use_llm: bool,
    fast_ack_enabled: bool,
    objective_hint: str,
) -> bool:
    """Single eligibility gate for fast-ack behavior across AI runtimes."""
    if not use_llm or not fast_ack_enabled:
        return False
    if _objective_disallows_fast_ack(objective_hint):
        return False
    return True


def initial_ai_fast_ack_prompt(
    *,
    opening_strategy: str,
    dataset_input_prompt: str,
    use_llm: bool,
    fast_ack_enabled: bool,
    objective_hint: str,
) -> str | None:
    if not ai_fast_ack_allowed(
        use_llm=use_llm,
        fast_ack_enabled=fast_ack_enabled,
        objective_hint=objective_hint,
    ):
        return None
    if opening_strategy != "wait_for_bot_greeting":
        return None
    if not dataset_input_prompt:
        return None
    return dataset_input_prompt


def _fast_ack_decision(
    *,
    fallback_prompt: str,
    fast_ack_source: FastAckSource,
) -> AICallerDecision:
    # Callers must guarantee non-empty prompt; resolve_ai_decision_with_fast_ack
    # only reaches this path when fallback_prompt is truthy.
    assert fallback_prompt, "fallback_prompt must be non-empty for a fast-ack decision"
    source_text = "dataset input" if fast_ack_source == "dataset_input" else "heuristic follow-up"
    return AICallerDecision(
        action="continue",
        utterance=fallback_prompt,
        reasoning_summary=f"Using {source_text} fast-ack fallback while the caller LLM is still pending.",
        confidence=None,
    )


async def resolve_ai_decision_with_fast_ack(
    *,
    generate_decision_fn: Callable[[], Awaitable[AICallerDecision]],
    fallback_prompt: str | None,
    fast_ack_source: FastAckSource,
    fast_ack_trigger_s: float,
    opening_strategy: str,
    scenario_kind: str,
    logger_obj,
    run_id: str,
) -> tuple[AICallerDecision, str]:
    decision_task: "asyncio.Task[AICallerDecision] | None" = None
    try:
        if not fallback_prompt:
            return await generate_decision_fn(), "llm"
        decision_task = asyncio.create_task(generate_decision_fn())
        try:
            return await asyncio.wait_for(asyncio.shield(decision_task), timeout=fast_ack_trigger_s), "llm"
        except asyncio.TimeoutError:
            AI_VOICE_FAST_ACK_TOTAL.labels(
                source=fast_ack_source,
                opening_strategy=opening_strategy,
                scenario_kind=scenario_kind,
            ).inc()
            if logger_obj is not None:
                logger_obj.info(
                    "ai_fast_ack_triggered run_id=%s source=%s timeout_s=%.2f",
                    run_id,
                    fast_ack_source,
                    fast_ack_trigger_s,
                )
            return _fast_ack_decision(
                fallback_prompt=fallback_prompt,
                fast_ack_source=fast_ack_source,
            ), "fast_ack"
    finally:
        if decision_task is not None and not decision_task.done():
            decision_task.cancel()
            try:
                await asyncio.gather(decision_task, return_exceptions=True)
            except asyncio.CancelledError:
                # Re-raise only if the outer task is being cancelled; otherwise
                # the CancelledError originated from decision_task itself (which
                # we just cancelled) and should not propagate further.
                if asyncio.current_task() is not None and asyncio.current_task().cancelling() > 0:
                    raise


def _style_caller_prompt(*, base: str, scenario) -> str:
    prompt = base.strip()
    style = scenario.persona.response_style.value
    mood = scenario.persona.mood.value

    if style == "formal":
        prompt = f"Thank you. {prompt}"
    elif style == "curt":
        prompt = "Next step, please."
    elif style == "verbose":
        prompt = f"{prompt} Please include any key details I should remember."

    if mood in {"frustrated", "impatient"}:
        prompt = f"I need this resolved quickly. {prompt}"
    elif mood == "angry":
        prompt = f"This has been very frustrating. {prompt}"

    return prompt.strip()


def _initial_bot_greeting_listen_settings(
    *,
    merge_window_s: float,
    endpointing_ms: int,
) -> tuple[float, int]:
    return (
        max(float(merge_window_s), INITIAL_BOT_GREETING_MERGE_WINDOW_S),
        max(int(endpointing_ms), INITIAL_BOT_GREETING_ENDPOINTING_MS),
    )


def _effective_ai_listen_settings(
    *,
    scenario,
    settings_obj,
) -> tuple[float, int]:
    merge_window_s = float(scenario.config.transcript_merge_window_s)
    endpointing_ms = int(scenario.config.stt_endpointing_ms)
    if not bool(getattr(settings_obj, "ai_voice_latency_profile_enabled", False)):
        return merge_window_s, endpointing_ms

    _missing = [
        attr
        for attr in (
            "ai_voice_latency_profile_transcript_merge_window_s",
            "ai_voice_latency_profile_stt_endpointing_ms",
        )
        if not hasattr(settings_obj, attr)
    ]
    if _missing:
        logging.getLogger(__name__).warning(
            "ai_voice_latency_profile_enabled=True but settings missing %s; profile has no effect",
            _missing,
        )
        return merge_window_s, endpointing_ms

    tuned_merge_window_s = float(settings_obj.ai_voice_latency_profile_transcript_merge_window_s)
    tuned_endpointing_ms = int(settings_obj.ai_voice_latency_profile_stt_endpointing_ms)
    effective_merge = min(merge_window_s, tuned_merge_window_s)
    effective_endpointing = min(endpointing_ms, tuned_endpointing_ms)
    logging.getLogger(__name__).debug(
        "ai_voice_latency_profile: merge_window %.2f→%.2f s  endpointing %d→%d ms",
        merge_window_s,
        effective_merge,
        endpointing_ms,
        effective_endpointing,
    )
    return effective_merge, effective_endpointing


def _elapsed_from_bot_end_s(
    *,
    bot_turn: ConversationTurn | None,
    timestamp_monotonic: float | None,
    call_started_monotonic: float,
) -> float | None:
    if bot_turn is None or bot_turn.speaker != "bot" or timestamp_monotonic is None:
        return None
    relative_timestamp_s = max(0.0, timestamp_monotonic - call_started_monotonic)
    return max(0.0, relative_timestamp_s - (float(bot_turn.audio_end_ms) / 1000.0))


def generate_ai_followup_prompt(
    *,
    last_bot_text: str,
    conversation: list[ConversationTurn],
    scenario,
    objective_hint: str,
    persona_name: str,
) -> str | None:
    if _ai_stop_signal(last_bot_text):
        return None

    normalized = _normalize(last_bot_text)
    if "anything else" in normalized or "any other" in normalized:
        return _style_caller_prompt(base="No, that's all I needed. Thank you.", scenario=scenario)

    bot_turns = [turn for turn in conversation if turn.speaker == "bot"]
    if "?" in last_bot_text:
        if len(bot_turns) >= 2:
            return _style_caller_prompt(
                base="Thanks, can you confirm the final next step before we end the call?",
                scenario=scenario,
            )
        if objective_hint:
            return _style_caller_prompt(
                base=f"Yes, that's right. I need help with: {objective_hint[:180]}. What should I do next?",
                scenario=scenario,
            )
        return _style_caller_prompt(
            base="Yes, that's right. Can you help me with the next step?",
            scenario=scenario,
        )

    if len(bot_turns) == 1 and objective_hint:
        subject = f" for {persona_name}" if persona_name else ""
        return _style_caller_prompt(
            base=f"Understood{subject}. How should we proceed to achieve: {objective_hint[:180]}?",
            scenario=scenario,
        )

    if len(bot_turns) >= 2:
        return _style_caller_prompt(base="Great, please summarize what happens next.", scenario=scenario)

    return _style_caller_prompt(base="Understood. What should I do next?", scenario=scenario)


async def execute_ai_scenario_loop(
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
    logger_obj,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    run_metadata: dict[str, object] | None = None,
    tts_live_circuit_breaker=None,
    provider_circuit_state_callback=None,
    ai_caller_circuit_breaker=None,
    ai_caller_generate_fn: (
        Callable[..., Awaitable[str | None]]
        | None
    ) = None,
    call_started_monotonic: float | None = None,
    scenario_kind: str = "ai",
) -> tuple[list[ConversationTurn], int]:
    conversation: list[ConversationTurn] = []
    response_visit_counts: dict[str, int] = defaultdict(int)
    turn_number = 0
    call_started = call_started_monotonic or time.monotonic()

    max_total_turns = max(1, int(scenario.config.max_total_turns))
    max_turn_cap = max(1, int(settings_obj.max_total_turns_hard_cap))
    ai_dispatch = _ai_dispatch_context(run_metadata)
    objective_hint = ai_dispatch.objective_hint()
    persona_name = ai_dispatch.ai_persona_name or ""
    opening_strategy = ai_dispatch.effective_opening_strategy()
    use_llm = bool(getattr(settings_obj, "ai_caller_use_llm", True))

    # caller_opens without LLM requires a seed dataset input turn to speak first.
    if opening_strategy == "caller_opens" and not use_llm:
        if not scenario.turns or not scenario_prompt_text(scenario.turns[0]).strip():
            raise ValueError("AI runtime scenario with caller_opens requires a dataset input turn.")

    # Both strategies run multi-turn; wait_for_bot_greeting just listens first.
    max_pairs = max(1, min(max_total_turns // 2, max_turn_cap // 2))
    next_prompt_source = "dataset_input"

    _emit_heartbeat_state = build_heartbeat_state_emitter(heartbeat_state_callback)
    _now_ms = build_now_ms_fn(call_started_monotonic=call_started)
    tts_circuit_bridge = init_tts_circuit_bridge(
        tts=tts,
        logger_obj=logger_obj,
        provider_circuit_state_callback=provider_circuit_state_callback,
    )
    ai_caller_circuit_bridge = AgentAiCallerCircuitBridge(
        logger_obj=logger_obj,
        provider_circuit_state_callback=provider_circuit_state_callback,
    )
    ai_caller_circuit_bridge.init_gauge()

    next_prompt = scenario_prompt_text(scenario.turns[0]) if scenario.turns else ""
    dataset_input_prompt = next_prompt.strip()
    model = str(getattr(settings_obj, "ai_caller_model", "gpt-4o-mini"))
    timeout_s = float(getattr(settings_obj, "ai_caller_timeout_s", 4.0))
    tts_synthesis_timeout_s = float(
        getattr(settings_obj, "tts_ai_scenario_synthesis_timeout_s", 30.0)
    )
    api_base_url = str(getattr(settings_obj, "ai_caller_api_base_url", "https://api.openai.com/v1"))
    max_context_turns = int(getattr(settings_obj, "ai_caller_max_context_turns", 8))
    generator = ai_caller_generate_fn or generate_next_ai_caller_utterance
    next_prompt_ready_monotonic: float | None = None
    next_prompt_decision_latency_s: float | None = None
    next_prompt_llm_start_gap_s: float | None = None
    speculative_planning_enabled = bool(
        getattr(settings_obj, "ai_voice_speculative_planning_enabled", False)
    )
    speculative_min_preview_chars = int(
        getattr(settings_obj, "ai_voice_speculative_min_preview_chars", 24)
    )
    fast_ack_enabled = bool(getattr(settings_obj, "ai_voice_fast_ack_enabled", False))
    fast_ack_trigger_s = float(getattr(settings_obj, "ai_voice_fast_ack_trigger_s", 0.6))
    early_playback_enabled = bool(getattr(settings_obj, "ai_voice_early_playback_enabled", False))
    speculative_plan: _SpeculativePlan | None = None
    early_playback: _EarlyPlaybackAttempt | None = None
    committed_early_playback: _CommittedEarlyPlayback | None = None
    active_preview_epoch = 0

    async def _generate_ai_prompt(last_bot_text: str) -> str | None:
        return await generator(
            openai_api_key=str(getattr(settings_obj, "openai_api_key", "")),
            model=model,
            timeout_s=timeout_s,
            api_base_url=api_base_url,
            scenario=scenario,
            conversation=list(conversation),
            last_bot_text=last_bot_text,
            objective_hint=objective_hint,
            persona_name=persona_name,
            max_context_turns=max_context_turns,
            circuit_breaker=ai_caller_circuit_breaker,
            on_circuit_transition=ai_caller_circuit_bridge.on_transition,
            on_circuit_reject=ai_caller_circuit_bridge.on_reject,
        )

    async def _cancel_speculative_plan(*, outcome: str) -> None:
        nonlocal speculative_plan
        if speculative_plan is None:
            return
        task = speculative_plan.task
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # Emit unconditionally — the task may already be done (e.g. LLM responded
        # before the final transcript arrived and we are discarding the result).
        AI_VOICE_SPECULATIVE_PLANS_TOTAL.labels(
            outcome=outcome,
            scenario_kind=scenario_kind,
        ).inc()
        speculative_plan = None

    def _mark_speculative_plan_committed(plan: _SpeculativePlan) -> None:
        nonlocal speculative_plan
        AI_VOICE_SPECULATIVE_PLANS_TOTAL.labels(
            outcome="committed",
            scenario_kind=scenario_kind,
        ).inc()
        speculative_plan = None
        if logger_obj is not None:
            logger_obj.debug(
                "ai_speculative_plan_committed run_id=%s preview=%s",
                run_id,
                plan.preview_text[:120],
            )

    async def _consume_speculative_plan(*, final_bot_text: str) -> str | None:
        nonlocal speculative_plan
        if speculative_plan is None:
            return None
        plan = speculative_plan
        if not _preview_matches_final(
            preview_text=plan.preview_text,
            final_text=final_bot_text,
        ):
            if logger_obj is not None:
                logger_obj.debug(
                    "ai_speculative_plan_discarded run_id=%s preview=%s final=%s",
                    run_id,
                    plan.preview_text[:120],
                    final_bot_text[:120],
                )
            await _cancel_speculative_plan(outcome="discarded")
            return None
        try:
            result = await plan.task
        except asyncio.CancelledError:
            AI_VOICE_SPECULATIVE_PLANS_TOTAL.labels(
                outcome="cancelled",
                scenario_kind=scenario_kind,
            ).inc()
            speculative_plan = None
            # Re-raise if the outer coroutine is itself being cancelled so that
            # cooperative cancellation propagates to the parent task.
            current = asyncio.current_task()
            if current is not None and current.cancelling() > 0:
                raise
            return None
        except Exception:
            AI_VOICE_SPECULATIVE_PLANS_TOTAL.labels(
                outcome="error",
                scenario_kind=scenario_kind,
            ).inc()
            speculative_plan = None
            return None
        _mark_speculative_plan_committed(plan)
        return result

    async def _maybe_start_speculative_plan(preview_text: str, event_type: str) -> None:
        nonlocal speculative_plan
        if (
            not speculative_planning_enabled
            or not use_llm
            or not _preview_text_is_eligible(
                text=preview_text,
                min_chars=speculative_min_preview_chars,
            )
        ):
            return
        normalized_preview = _normalize(preview_text)
        if speculative_plan is not None and _normalize(speculative_plan.preview_text) == normalized_preview:
            return
        if speculative_plan is not None:
            await _cancel_speculative_plan(outcome="cancelled")
        started_monotonic = time.monotonic()
        task = asyncio.create_task(_generate_ai_prompt(preview_text))
        speculative_plan = _SpeculativePlan(
            preview_text=preview_text,
            started_monotonic=started_monotonic,
            task=task,
        )
        AI_VOICE_SPECULATIVE_PLANS_TOTAL.labels(
            outcome="started",
            scenario_kind=scenario_kind,
        ).inc()
        if logger_obj is not None:
            logger_obj.debug(
                "ai_speculative_plan_started run_id=%s event_type=%s preview=%s",
                run_id,
                event_type,
                preview_text[:120],
            )

    async def _cancel_early_playback(*, outcome: str) -> None:
        nonlocal early_playback
        if early_playback is None:
            return
        early_playback.cancel_event.set()
        await asyncio.gather(early_playback.task, return_exceptions=True)
        AI_VOICE_EARLY_PLAYBACK_TOTAL.labels(
            outcome=outcome,
            scenario_kind=scenario_kind,
        ).inc()
        early_playback = None

    async def _maybe_start_early_playback(
        preview_text: str,
        event_type: str,
        *,
        epoch: int,
        target_turn_id: str,
        target_turn_number: int,
    ) -> None:
        nonlocal early_playback
        if (
            not early_playback_enabled
            or event_type != "final"
            or speculative_plan is None
            or epoch != active_preview_epoch
        ):
            return
        normalized_preview = _normalize(preview_text)
        if (
            early_playback is not None
            and early_playback.epoch == epoch
            and _normalize(early_playback.preview_text) == normalized_preview
        ):
            return
        if not speculative_plan.task.done():
            return
        try:
            prompt_text = speculative_plan.task.result() or ""
        except asyncio.CancelledError:
            # Re-raise if the *outer* task is being cancelled so cooperative
            # cancellation is not swallowed (mirrors _consume_speculative_plan).
            current = asyncio.current_task()
            if current is not None and current.cancelling() > 0:
                raise
            return
        except Exception:
            AI_VOICE_EARLY_PLAYBACK_TOTAL.labels(
                outcome="error",
                scenario_kind=scenario_kind,
            ).inc()
            if logger_obj is not None:
                logger_obj.warning(
                    "ai_early_playback_plan_result_error run_id=%s", run_id, exc_info=True
                )
            return
        if not prompt_text.strip():
            return
        if early_playback is not None:
            await _cancel_early_playback(outcome="cancelled")
        prompt_ready_monotonic = time.monotonic()
        playback_started_monotonic = prompt_ready_monotonic
        start_ms = max(0, int((playback_started_monotonic - call_started) * 1000))
        cancel_event = asyncio.Event()
        # Use target_turn_id (not the hardcoded "ai_record_input") so TTS cache
        # lookups use the correct turn key for both initial and follow-up turns.
        early_turn = ai_prompt_block(
            turn_id=target_turn_id,
            prompt_text=prompt_text.strip(),
        )

        async def _run_early_playback() -> tuple[object, int]:
            playback = await play_harness_turn_audio(
                turn_number=target_turn_number,
                turn_def=early_turn,
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
                synthesis_timeout_s=tts_synthesis_timeout_s,
                cancel_event=cancel_event,
            )
            return playback, _now_ms()

        early_playback = _EarlyPlaybackAttempt(
            epoch=epoch,
            target_turn_id=target_turn_id,
            target_turn_number=target_turn_number,
            preview_text=preview_text,
            prompt_text=prompt_text.strip(),
            prompt_ready_monotonic=prompt_ready_monotonic,
            llm_started_monotonic=speculative_plan.started_monotonic,
            playback_started_monotonic=playback_started_monotonic,
            start_ms=start_ms,
            cancel_event=cancel_event,
            task=asyncio.create_task(_run_early_playback()),
        )
        AI_VOICE_EARLY_PLAYBACK_TOTAL.labels(
            outcome="started",
            scenario_kind=scenario_kind,
        ).inc()
        if logger_obj is not None:
            logger_obj.debug(
                "ai_early_playback_started run_id=%s preview=%s",
                run_id,
                preview_text[:120],
            )

    def _fast_ack_allowed() -> bool:
        """Single source of truth for fast-ack eligibility."""
        return ai_fast_ack_allowed(
            use_llm=use_llm,
            fast_ack_enabled=fast_ack_enabled,
            objective_hint=objective_hint,
        )

    def _next_preview_epoch() -> int:
        nonlocal active_preview_epoch
        active_preview_epoch += 1
        return active_preview_epoch

    async def _on_preview(
        preview_text: str,
        event_type: str,
        *,
        epoch: int,
        target_turn_id: str,
        target_turn_number: int,
    ) -> None:
        if epoch != active_preview_epoch:
            return
        AI_VOICE_PREVIEW_EVENTS_TOTAL.labels(
            event_type=event_type,
            scenario_kind=scenario_kind,
        ).inc()
        if logger_obj is not None:
            logger_obj.debug(
                "ai_bot_preview run_id=%s event_type=%s text=%s epoch=%d target_turn=%s",
                run_id,
                event_type,
                preview_text[:160],
                epoch,
                target_turn_id,
            )
        await _maybe_start_speculative_plan(preview_text, event_type)
        await _maybe_start_early_playback(
            preview_text,
            event_type,
            epoch=epoch,
            target_turn_id=target_turn_id,
            target_turn_number=target_turn_number,
        )

    def _make_preview_callback(
        *,
        epoch: int,
        target_turn_id: str,
        target_turn_number: int,
    ):
        async def _callback(preview_text: str, event_type: str) -> None:
            await _on_preview(
                preview_text,
                event_type,
                epoch=epoch,
                target_turn_id=target_turn_id,
                target_turn_number=target_turn_number,
            )

        return _callback

    async def _resolve_committed_early_playback(
        *,
        final_bot_turn: ConversationTurn,
        epoch: int,
    ) -> _CommittedEarlyPlayback | None:
        nonlocal early_playback, speculative_plan
        if early_playback is None or early_playback.epoch != epoch:
            return None
        if not _preview_matches_final(
            preview_text=early_playback.preview_text,
            final_text=final_bot_turn.text,
        ):
            await _cancel_early_playback(outcome="stale_suppressed")
            return None
        playback_attempt = early_playback
        try:
            playback_result, playback_end_ms = await playback_attempt.task
        except Exception:
            AI_VOICE_EARLY_PLAYBACK_TOTAL.labels(
                outcome="error",
                scenario_kind=scenario_kind,
            ).inc()
            early_playback = None
            return None
        early_playback = None
        if not bool(getattr(playback_result, "completed", False)) or bool(
            getattr(playback_result, "cancelled", False)
        ):
            return None
        AI_VOICE_EARLY_PLAYBACK_TOTAL.labels(
            outcome="committed",
            scenario_kind=scenario_kind,
        ).inc()
        if speculative_plan is not None:
            # The speculative plan's preview_text was already validated to match
            # the final bot turn text (via _preview_matches_final above), so the
            # plan is confirmed fresh. Mark it committed so _consume_speculative_plan
            # can return its LLM result on the next turn instead of re-requesting.
            _mark_speculative_plan_committed(speculative_plan)
        return _CommittedEarlyPlayback(attempt=playback_attempt, end_ms=playback_end_ms)

    def _fast_ack_prompt_for_initial_turn() -> str | None:
        return initial_ai_fast_ack_prompt(
            opening_strategy=opening_strategy,
            dataset_input_prompt=dataset_input_prompt,
            use_llm=use_llm,
            fast_ack_enabled=fast_ack_enabled,
            objective_hint=objective_hint,
        )

    async def _resolve_llm_prompt_with_fast_ack(
        *,
        bot_text: str,
        fallback_prompt: str | None,
        fast_ack_source: FastAckSource,
    ) -> tuple[str, str, float | None, float | None]:
        llm_started_monotonic = time.monotonic()
        speculative_result = await _consume_speculative_plan(final_bot_text=bot_text)
        if speculative_result is not None:
            # An empty speculative result means the plan committed but the LLM
            # returned nothing. Label as "llm" to avoid contaminating speculative
            # latency metrics with a zero-latency noop.
            return (
                speculative_result,
                "llm_speculative" if speculative_result else "llm",
                llm_started_monotonic,
                time.monotonic(),
            )

        llm_task: asyncio.Task[str | None] | None = None
        try:
            if not fallback_prompt:
                # None means fast-ack is disabled for this slot; "" would also
                # be invalid (generate_ai_followup_prompt never returns "").
                generated = (await _generate_ai_prompt(bot_text)) or ""
                return generated, "llm", llm_started_monotonic, time.monotonic()
            llm_task = asyncio.create_task(_generate_ai_prompt(bot_text))
            try:
                generated = await asyncio.wait_for(asyncio.shield(llm_task), timeout=fast_ack_trigger_s)
            except asyncio.TimeoutError:
                AI_VOICE_FAST_ACK_TOTAL.labels(
                    source=fast_ack_source,
                    opening_strategy=opening_strategy,
                    scenario_kind=scenario_kind,
                ).inc()
                if logger_obj is not None:
                    logger_obj.info(
                        "ai_fast_ack_triggered run_id=%s source=%s timeout_s=%.2f",
                        run_id,
                        fast_ack_source,
                        fast_ack_trigger_s,
                    )
                return fallback_prompt, "fast_ack", llm_started_monotonic, time.monotonic()
            return (generated or ""), "llm", llm_started_monotonic, time.monotonic()
        finally:
            # Cancel and drain the background LLM task if it is still running.
            # Using finally (not except CancelledError) ensures exactly one
            # cancel+drain regardless of whether the exit path is TimeoutError,
            # CancelledError, or a clean return.
            if llm_task is not None and not llm_task.done():
                llm_task.cancel()
                await asyncio.gather(llm_task, return_exceptions=True)

    preview_events_enabled = bool(getattr(settings_obj, "ai_voice_preview_events_enabled", False))

    if opening_strategy == "wait_for_bot_greeting":
        tuned_merge_window_s, tuned_endpointing_ms = _effective_ai_listen_settings(
            scenario=scenario,
            settings_obj=settings_obj,
        )
        greeting_merge_window_s, greeting_endpointing_ms = _initial_bot_greeting_listen_settings(
            merge_window_s=tuned_merge_window_s,
            endpointing_ms=tuned_endpointing_ms,
        )
        _emit_heartbeat_state(turn_number=1, listener_state="awaiting_bot")
        initial_preview_epoch = _next_preview_epoch()
        bot_turn = await listen_bot_turn(
            bot_listener=bot_listener,
            timeout_s=scenario.config.turn_timeout_s,
            merge_window_s=greeting_merge_window_s,
            stt_endpointing_ms=greeting_endpointing_ms,
            turn_id="ai_initial_bot",
            turn_number=1,
            now_ms_fn=_now_ms,
            logger_obj=logger_obj,
            scenario_kind=scenario_kind,
            preview_callback=(
                _make_preview_callback(
                    epoch=initial_preview_epoch,
                    target_turn_id="ai_record_input",
                    target_turn_number=2,
                )
                if preview_events_enabled
                else None
            ),
        )
        turn_number = 1
        conversation.append(bot_turn)
        response_visit_counts[bot_turn.turn_id] += 1
        await report_turn_fn(
            run_id,
            bot_turn,
            visit=response_visit_counts[bot_turn.turn_id],
        )
        committed_early_playback = await _resolve_committed_early_playback(
            final_bot_turn=bot_turn,
            epoch=initial_preview_epoch,
        )
        if bot_turn.text == "(timeout)" and logger_obj is not None:
            logger_obj.warning(
                "Bot greeting timed out; proceeding with dataset input for run %s", run_id
            )
        # Generate the first caller utterance from the bot's greeting using the LLM.
        # Falls back to dataset_input if LLM is disabled, returns end immediately,
        # or the bot greeting timed out (passing synthetic "(timeout)" to the LLM
        # would produce a contextually wrong response).
        if committed_early_playback is not None:
            next_prompt = committed_early_playback.attempt.prompt_text
            next_prompt_source = "llm_early"
            next_prompt_ready_monotonic = committed_early_playback.attempt.prompt_ready_monotonic
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=committed_early_playback.attempt.prompt_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=committed_early_playback.attempt.llm_started_monotonic,
                call_started_monotonic=call_started,
            )
        elif use_llm and bot_turn.text != "(timeout)":
            (
                generated,
                next_prompt_source,
                llm_started_monotonic,
                decision_ready_monotonic,
            ) = await _resolve_llm_prompt_with_fast_ack(
                bot_text=bot_turn.text,
                fallback_prompt=_fast_ack_prompt_for_initial_turn(),
                fast_ack_source="dataset_input",
            )
            if generated:
                next_prompt = generated
            else:
                # LLM signalled end immediately (action="end") — nothing to say.
                next_prompt = ""
            next_prompt_ready_monotonic = decision_ready_monotonic
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=decision_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=llm_started_monotonic,
                call_started_monotonic=call_started,
            )
            if next_prompt_decision_latency_s is not None:
                AI_CALLER_DECISION_LATENCY_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_decision_latency_s)
            if next_prompt_llm_start_gap_s is not None:
                AI_CALLER_LLM_REQUEST_START_GAP_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_llm_start_gap_s)
        else:
            next_prompt_ready_monotonic = time.monotonic()
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=next_prompt_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = None
            if next_prompt_decision_latency_s is not None:
                AI_CALLER_DECISION_LATENCY_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_decision_latency_s)

    for pair_index in range(max_pairs):
        if not next_prompt.strip():
            break

        # Cancel any speculative plan that survived from a previous iteration.
        # This guards against async STT preview events that arrive fractionally
        # after listen_bot_turn() returns and before the next listen window opens.
        await _cancel_speculative_plan(outcome="cancelled")

        effective_merge_window_s, effective_endpointing_ms = _effective_ai_listen_settings(
            scenario=scenario,
            settings_obj=settings_obj,
        )

        turn_def = ai_prompt_block(
            turn_id=("ai_record_input" if pair_index == 0 else f"ai_followup_{pair_index}"),
            prompt_text=next_prompt.strip(),
        )

        turn_number += 1
        reused_early_playback = (
            committed_early_playback is not None
            and committed_early_playback.attempt.target_turn_id == turn_def.id
            and committed_early_playback.attempt.target_turn_number == turn_number
        )
        _emit_heartbeat_state(turn_number=turn_number, listener_state="speaking_harness")
        previous_turn = conversation[-1] if conversation else None
        if reused_early_playback:
            playback_started_monotonic = committed_early_playback.attempt.playback_started_monotonic
            start_ms = committed_early_playback.attempt.start_ms
        else:
            pre_pause = scenario.config.inter_turn_pause_s + turn_def.config.pre_speak_pause_s
            if pre_pause > 0:
                await asyncio.sleep(pre_pause)
            playback_started_monotonic = time.monotonic()
            start_ms = max(0, int((playback_started_monotonic - call_started) * 1000))
        if previous_turn is not None and previous_turn.speaker == "bot":
            bot_to_playback_start_s = max(
                0.0,
                float(start_ms - previous_turn.audio_end_ms) / 1000.0,
            )
            # next_prompt_source was set by the LLM/heuristic decision block above and
            # must not be reassigned before this observe() call. Any refactor moving the
            # source assignment must keep it before this block.
            AI_CALLER_REPLY_LATENCY_SECONDS.labels(
                opening_strategy=opening_strategy,
                source=next_prompt_source,
                scenario_kind=scenario_kind,
            ).observe(bot_to_playback_start_s)
            decision_to_playback_start_s = None
            if next_prompt_ready_monotonic is not None:
                decision_to_playback_start_s = max(
                    0.0,
                    playback_started_monotonic - next_prompt_ready_monotonic,
                )
                AI_CALLER_DECISION_TO_PLAYBACK_START_GAP_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(decision_to_playback_start_s)
            if logger_obj is not None:
                logger_obj.info(
                    "ai_turn_latency run_id=%s turn_number=%d opening_strategy=%s source=%s "
                    "bot_to_llm_start_s=%.3f bot_to_decision_s=%.3f "
                    "decision_to_playback_start_s=%.3f bot_to_playback_start_s=%.3f",
                    run_id,
                    turn_number,
                    opening_strategy,
                    next_prompt_source,
                    next_prompt_llm_start_gap_s if next_prompt_llm_start_gap_s is not None else -1.0,
                    next_prompt_decision_latency_s if next_prompt_decision_latency_s is not None else -1.0,
                    decision_to_playback_start_s if decision_to_playback_start_s is not None else -1.0,
                    bot_to_playback_start_s,
                )
        if reused_early_playback:
            _playback = HarnessPlaybackResult(completed=True, cancelled=False, source="live")
            end_ms = committed_early_playback.end_ms
            committed_early_playback = None
        else:
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
                synthesis_timeout_s=tts_synthesis_timeout_s,
            )
            end_ms = _now_ms()

        harness_turn = ConversationTurn(
            turn_id=turn_def.id,
            turn_number=turn_number,
            speaker="harness",
            text=turn_def.content.text or "",
            audio_start_ms=start_ms,
            audio_end_ms=end_ms,
            adversarial=False,
            technique=None,
        )
        conversation.append(harness_turn)
        await report_turn_fn(run_id, harness_turn, visit=1)

        _emit_heartbeat_state(turn_number=turn_number + 1, listener_state="awaiting_bot")
        response_preview_epoch = _next_preview_epoch()
        bot_turn = await listen_bot_turn(
            bot_listener=bot_listener,
            timeout_s=scenario.config.turn_timeout_s,
            merge_window_s=effective_merge_window_s,
            stt_endpointing_ms=effective_endpointing_ms,
            turn_id=f"{turn_def.id}_bot",
            turn_number=turn_number + 1,
            now_ms_fn=_now_ms,
            logger_obj=logger_obj,
            scenario_kind=scenario_kind,
            preview_callback=(
                _make_preview_callback(
                    epoch=response_preview_epoch,
                    target_turn_id=f"ai_followup_{pair_index + 1}",  # targets the harness turn in the next loop iteration
                    target_turn_number=turn_number + 2,
                )
                if preview_events_enabled
                else None
            ),
        )
        turn_number += 1
        conversation.append(bot_turn)

        response_visit_counts[bot_turn.turn_id] += 1
        await report_turn_fn(
            run_id,
            bot_turn,
            visit=response_visit_counts[bot_turn.turn_id],
        )
        if committed_early_playback is not None:
            # Defensive: should have been consumed by the reused_early_playback
            # guard above. Reaching here means the epoch or turn guards missed a
            # stale attempt — log and discard before overwriting.
            if logger_obj is not None:
                logger_obj.warning(
                    "ai_early_playback_overwrite run_id=%s target=%s/%d current=%s/%d",
                    run_id,
                    committed_early_playback.attempt.target_turn_id,
                    committed_early_playback.attempt.target_turn_number,
                    turn_def.id,
                    turn_number,
                )
            committed_early_playback = None
        committed_early_playback = await _resolve_committed_early_playback(
            final_bot_turn=bot_turn,
            epoch=response_preview_epoch,
        )

        if bot_turn.text == "(timeout)":
            await _cancel_speculative_plan(outcome="cancelled")
            break
        if committed_early_playback is not None:
            next_prompt = committed_early_playback.attempt.prompt_text
            next_prompt_source = "llm_early"
            next_prompt_ready_monotonic = committed_early_playback.attempt.prompt_ready_monotonic
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=committed_early_playback.attempt.prompt_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=committed_early_playback.attempt.llm_started_monotonic,
                call_started_monotonic=call_started,
            )
            if next_prompt_decision_latency_s is not None:
                AI_CALLER_DECISION_LATENCY_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_decision_latency_s)
            if next_prompt_llm_start_gap_s is not None:
                AI_CALLER_LLM_REQUEST_START_GAP_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_llm_start_gap_s)
            # `continue` skips the LLM-prompt generation block below but NOT the
            # _cancel_speculative_plan call at the top of the next iteration —
            # speculative plan cleanup always runs at the start of each pair loop.
            continue
        if use_llm:
            # generate_ai_followup_prompt is synchronous and pure — it must
            # remain cheap (no I/O, no external calls) so the LLM task starts
            # promptly and the fast_ack_trigger_s window is not silently eaten.
            heuristic_fast_ack_prompt = (
                generate_ai_followup_prompt(
                    last_bot_text=bot_turn.text,
                    conversation=conversation,
                    scenario=scenario,
                    objective_hint=objective_hint,
                    persona_name=persona_name,
                )
                if _fast_ack_allowed()
                else None
            )
            (
                next_prompt,
                next_prompt_source,
                llm_started_monotonic,
                next_prompt_ready_monotonic,
            ) = await _resolve_llm_prompt_with_fast_ack(
                bot_text=bot_turn.text,
                fallback_prompt=heuristic_fast_ack_prompt,
                fast_ack_source="heuristic",
            )
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=next_prompt_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=llm_started_monotonic,
                call_started_monotonic=call_started,
            )
            if next_prompt_decision_latency_s is not None:
                AI_CALLER_DECISION_LATENCY_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_decision_latency_s)
            if next_prompt_llm_start_gap_s is not None:
                AI_CALLER_LLM_REQUEST_START_GAP_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_llm_start_gap_s)
        else:
            next_prompt = generate_ai_followup_prompt(
                last_bot_text=bot_turn.text,
                conversation=conversation,
                scenario=scenario,
                objective_hint=objective_hint,
                persona_name=persona_name,
            ) or ""
            next_prompt_ready_monotonic = time.monotonic()
            next_prompt_source = "heuristic"
            next_prompt_decision_latency_s = _elapsed_from_bot_end_s(
                bot_turn=bot_turn,
                timestamp_monotonic=next_prompt_ready_monotonic,
                call_started_monotonic=call_started,
            )
            next_prompt_llm_start_gap_s = None
            if next_prompt_decision_latency_s is not None:
                AI_CALLER_DECISION_LATENCY_SECONDS.labels(
                    opening_strategy=opening_strategy,
                    source=next_prompt_source,
                    scenario_kind=scenario_kind,
                ).observe(next_prompt_decision_latency_s)
        if not next_prompt:
            break

    await _cancel_early_playback(outcome="cancelled")
    await _cancel_speculative_plan(outcome="cancelled")
    # Defensive clear: committed_early_playback should normally be consumed by the
    # next harness turn, but an unexpected early break should not leak state.
    committed_early_playback = None
    return conversation, turn_number
