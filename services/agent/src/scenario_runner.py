from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from livekit import rtc

from botcheck_scenarios import ConversationTurn, RunExecutionMetadata, ScenarioDefinition

from .direct_http import DirectHTTPBotClient, DirectHTTPTransportContext
from .direct_http_runtime import (
    execute_direct_http_ai_loop,
    execute_direct_http_scenario_loop,
)
from .media_engine import (
    AgentSttCircuitBridge,
    publish_harness_audio_track,
    remove_participant_from_room,
)
from .metrics import SIP_CALL_DURATION_SECONDS, SIP_CALL_OUTCOMES_TOTAL
from .playground_runtime import execute_playground_loop
from .scenario_ai_loop import execute_ai_scenario_loop
from .loop_runtime_helpers import HeartbeatStateCallback, build_heartbeat_state_emitter
from .scenario_kind import AI_RUNTIME_TAG
from .scenario_loop_executor import execute_scenario_loop
from .scenario_run_finalize import finalize_run_media
from .stt_provider import resolve_live_stt_provider
from .tts_provider import resolve_live_tts_provider

ProviderCircuitStateCallback = Callable[..., Awaitable[None]]


@dataclass(slots=True)
class ScenarioRunContext:
    tenant_id: str
    settings_obj: Any
    wait_for_bot_fn: Any
    bot_listener_cls: Any
    bot_audio_recorder_cls: Any
    read_cached_turn_wav_fn: Any
    publish_cached_wav_fn: Any
    report_turn_fn: Any
    upload_run_recording_fn: Any
    classify_branch_fn: Any
    classifier_client: Any
    livekit_api_cls: Any
    room_participant_identity_cls: Any
    rtc_module: Any
    openai_module: Any
    stt_plugin_modules: dict[str, Any]
    logger_obj: Any
    fetch_run_transport_context_fn: Any = None
    heartbeat_state_callback: HeartbeatStateCallback | None = None
    run_metadata: dict[str, object] | None = None
    tts_live_circuit_breaker: Any = None
    ai_caller_circuit_breaker: Any = None
    provider_circuit_state_callback: ProviderCircuitStateCallback | None = None
    mock_agent_cls: Any = None
    post_playground_event_fn: Any = None

async def run_scenario(
    room: rtc.Room,
    scenario: ScenarioDefinition,
    run_id: str,
    *,
    context: ScenarioRunContext,
) -> list[ConversationTurn]:
    """Execute harness scenario turns and return the full conversation."""
    execution_metadata = RunExecutionMetadata.model_validate(context.run_metadata or {})
    raw_scenario_kind = execution_metadata.normalized_scenario_kind()
    raw_ai_opening_strategy = execution_metadata.effective_opening_strategy()
    raw_run_type = execution_metadata.normalized_run_type()
    if raw_run_type == "playground":
        return (
            await execute_playground_loop(
                scenario=scenario,
                run_id=run_id,
                settings_obj=context.settings_obj,
                report_turn_fn=context.report_turn_fn,
                classify_branch_fn=context.classify_branch_fn,
                classifier_client=context.classifier_client,
                fetch_run_transport_context_fn=context.fetch_run_transport_context_fn,
                run_metadata=context.run_metadata,
                heartbeat_state_callback=context.heartbeat_state_callback,
                mock_agent_cls=context.mock_agent_cls,
                post_playground_event_fn=context.post_playground_event_fn,
            )
        )[0]
    scenario_kind = raw_scenario_kind or ("ai" if AI_RUNTIME_TAG in scenario.tags else "graph")
    transport_protocol = execution_metadata.transport_protocol()
    if transport_protocol == "http":
        if context.fetch_run_transport_context_fn is None:
            raise RuntimeError("Direct HTTP transport requested without fetch_run_transport_context_fn")
        transport_context = DirectHTTPTransportContext.model_validate(
            await context.fetch_run_transport_context_fn(run_id)
        )
        client = DirectHTTPBotClient(context=transport_context)
        try:
            if AI_RUNTIME_TAG in scenario.tags:
                if not context.settings_obj.feature_ai_scenarios_enabled:
                    raise RuntimeError("AI caller runtime is disabled on this harness worker.")
                return (
                    await execute_direct_http_ai_loop(
                        client=client,
                        scenario=scenario,
                        run_id=run_id,
                        settings_obj=context.settings_obj,
                        report_turn_fn=context.report_turn_fn,
                        heartbeat_state_callback=context.heartbeat_state_callback,
                        run_metadata=context.run_metadata,
                    )
                )[0]
            return (
                await execute_direct_http_scenario_loop(
                    client=client,
                    scenario=scenario,
                    run_id=run_id,
                    settings_obj=context.settings_obj,
                    report_turn_fn=context.report_turn_fn,
                    classify_branch_fn=context.classify_branch_fn,
                    classifier_client=context.classifier_client,
                    heartbeat_state_callback=context.heartbeat_state_callback,
                    scenario_kind=scenario_kind,
                )
            )[0]
        finally:
            await client.aclose()
    tts_provider = resolve_live_tts_provider(
        tts_voice=scenario.config.tts_voice,
        settings_obj=context.settings_obj,
    )
    tts = tts_provider.create_live_tts(
        openai_module=context.openai_module,
        rtc_module=context.rtc_module,
    )
    selected_tts_live_circuit_breaker = context.tts_live_circuit_breaker
    get_breaker = getattr(context.tts_live_circuit_breaker, "get", None)
    if callable(get_breaker):
        selected_tts_live_circuit_breaker = get_breaker(tts_provider.provider_id)

    stt_provider = resolve_live_stt_provider(
        stt_provider=scenario.config.stt_provider,
        stt_model=scenario.config.stt_model,
        language=scenario.config.language,
        settings_obj=context.settings_obj,
    )
    try:
        stt_plugin_module = context.stt_plugin_modules[stt_provider.provider_id]
    except KeyError as exc:
        raise RuntimeError(f"No STT plugin module configured for provider: {stt_provider.provider_id}") from exc
    stt_circuit_bridge = AgentSttCircuitBridge(
        provider=stt_provider.provider_id,
        logger_obj=context.logger_obj,
        provider_circuit_state_callback=context.provider_circuit_state_callback,
    )
    stt_circuit_bridge.init_gauge()

    recorder = context.bot_audio_recorder_cls(enabled=bool(scenario.config.record_audio))
    audio_source = await publish_harness_audio_track(
        room=room,
        rtc_module=context.rtc_module,
        recorder=recorder,
    )

    context.logger_obj.info("Run %s: waiting for bot participant", run_id)
    is_sip = scenario.bot.protocol.value == "sip"
    try:
        bot_participant = await context.wait_for_bot_fn(
            room,
            timeout_s=scenario.config.bot_join_timeout_s,
        )
    except asyncio.TimeoutError:
        if is_sip:
            SIP_CALL_OUTCOMES_TOTAL.labels(outcome="no_answer").inc()
        raise
    context.logger_obj.info("Run %s: bot joined as %s", run_id, bot_participant.identity)
    if is_sip:
        SIP_CALL_OUTCOMES_TOTAL.labels(outcome="answered").inc()
    sip_join_time = time.monotonic()

    try:
        bot_listener = context.bot_listener_cls(
            bot_participant,
            stt_provider,
            stt_plugin_module,
            on_audio_frame=recorder.capture_frame,
            endpointing_ms=scenario.config.stt_endpointing_ms,
            stt_circuit_bridge=stt_circuit_bridge,
        )
        await bot_listener.start()

        await asyncio.sleep(1.0)
        skip_initial_drain = AI_RUNTIME_TAG in scenario.tags and raw_ai_opening_strategy == "wait_for_bot_greeting"
        if scenario.turns[0].kind == "harness_prompt" and not skip_initial_drain:
            await bot_listener.drain(scenario.config.initial_drain_s)
            recorder.reset()

        call_started = time.monotonic()
        mark_recorder_timing_origin = getattr(recorder, "mark_timing_origin", None)
        if callable(mark_recorder_timing_origin):
            mark_recorder_timing_origin(call_started)
        mark_timing_origin = getattr(bot_listener, "mark_timing_origin", None)
        if callable(mark_timing_origin):
            mark_timing_origin()

        _emit_heartbeat_state = build_heartbeat_state_emitter(context.heartbeat_state_callback)

        if AI_RUNTIME_TAG in scenario.tags:
            if not context.settings_obj.feature_ai_scenarios_enabled:
                raise RuntimeError("AI caller runtime is disabled on this harness worker.")
            conversation, turn_number = await execute_ai_scenario_loop(
                scenario=scenario,
                run_id=run_id,
                tenant_id=context.tenant_id,
                settings_obj=context.settings_obj,
                bot_listener=bot_listener,
                audio_source=audio_source,
                tts=tts,
                read_cached_turn_wav_fn=context.read_cached_turn_wav_fn,
                publish_cached_wav_fn=context.publish_cached_wav_fn,
                report_turn_fn=context.report_turn_fn,
                logger_obj=context.logger_obj,
                heartbeat_state_callback=context.heartbeat_state_callback,
                run_metadata=context.run_metadata,
                tts_live_circuit_breaker=selected_tts_live_circuit_breaker,
                provider_circuit_state_callback=context.provider_circuit_state_callback,
                ai_caller_circuit_breaker=context.ai_caller_circuit_breaker,
                call_started_monotonic=call_started,
                scenario_kind=scenario_kind,
            )
        else:
            conversation, turn_number = await execute_scenario_loop(
                scenario=scenario,
                run_id=run_id,
                tenant_id=context.tenant_id,
                settings_obj=context.settings_obj,
                bot_listener=bot_listener,
                audio_source=audio_source,
                tts=tts,
                read_cached_turn_wav_fn=context.read_cached_turn_wav_fn,
                publish_cached_wav_fn=context.publish_cached_wav_fn,
                report_turn_fn=context.report_turn_fn,
                classify_branch_fn=context.classify_branch_fn,
                classifier_client=context.classifier_client,
                logger_obj=context.logger_obj,
                heartbeat_state_callback=context.heartbeat_state_callback,
                tts_live_circuit_breaker=selected_tts_live_circuit_breaker,
                provider_circuit_state_callback=context.provider_circuit_state_callback,
                call_started_monotonic=call_started,
                scenario_kind=scenario_kind,
            )
        _emit_heartbeat_state(turn_number=turn_number, listener_state="finalizing")
        await finalize_run_media(
            run_id=run_id,
            room=room,
            bot_participant=bot_participant,
            is_sip=is_sip,
            call_started_monotonic=call_started,
            bot_listener=bot_listener,
            recorder=recorder,
            settings_obj=context.settings_obj,
            livekit_api_cls=context.livekit_api_cls,
            room_participant_identity_cls=context.room_participant_identity_cls,
            remove_participant_from_room_fn=remove_participant_from_room,
            upload_run_recording_fn=context.upload_run_recording_fn,
            logger_obj=context.logger_obj,
            participant_removal_enabled=transport_protocol != "webrtc",
        )

        return conversation
    finally:
        if is_sip:
            sip_duration_s = max(0.0, time.monotonic() - sip_join_time)
            SIP_CALL_DURATION_SECONDS.observe(sip_duration_s)
