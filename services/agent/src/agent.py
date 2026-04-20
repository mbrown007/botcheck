"""
BotCheck Harness Agent

Joins a LiveKit room as a synthetic caller, executes a scenario turn-by-turn,
and reports each exchange back to the BotCheck API for judging.

Lifecycle:
  1. JobContext created by LiveKit — room metadata contains run_id + scenario_id
  2. Agent fetches scenario definition from BotCheck API
  3. For each harness turn:
     a. Synthesise text → TTS audio → publish to room
     b. Wait for bot audio → ASR transcript
     c. POST turn record to /runs/{run_id}/turns
  4. POST /runs/{run_id}/complete
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Literal

import aioboto3
import structlog
from livekit import api as lk_api
from livekit import rtc
from livekit.agents import JobContext, JobExecutorType, WorkerOptions, cli
from livekit.plugins import azure, deepgram, openai

from botcheck_scenarios import (
    AsyncCircuitBreaker,
    ConversationTurn,
    ProviderKeyedRegistry,
    RunExecutionMetadata,
    ScenarioDefinition,
    Turn,
)

from . import agent_cache_surface as _cache_surface
from . import agent_final_ack_surface as _final_ack_surface
from . import callback_handler as _callback_handler
from . import heartbeat as _heartbeat
from . import service_heartbeat as _service_heartbeat
from .audio import (
    BotAudioRecorder as _BotAudioRecorder,
    BotListener as _BotListener,
    wait_for_bot as _wait_for_bot,
)
from .branch_classifier import HeuristicBranchClassifierClient, classify_branch
from .config import settings
from .entrypoint_coordinator import run_entrypoint as _run_entrypoint
from .logging_setup import configure_logging
from .metrics import (
    AGENT_API_CALLBACKS_TOTAL,
    AGENT_FINAL_ACK_TOTAL,
    AGENT_RUN_DURATION_SECONDS,
    AGENT_RUNS_TOTAL,
    AGENT_TURNS_TOTAL,
    TTS_CACHE_FALLBACK_TOTAL,
    TTS_CACHE_HITS_TOTAL,
    TTS_CACHE_MISSES_TOTAL,
    start_metrics_server_if_enabled,
)
from .mock_agent import MockAgent
from .openai_chat_client import aclose_shared_chat_clients
from .provider_runtime_context import RuntimeSettingsOverlay, build_settings_overrides
from .scenario_runner import ScenarioRunContext, run_scenario as _run_scenario_impl
from .scenario_kind import materialize_runtime_scenario as _materialize_runtime_scenario
from .telemetry import (
    detach_trace_context,
)
from .telemetry_bridge import (
    attach_trace_context_from_room_metadata as _attach_trace_context_from_room_metadata_impl,
    bootstrap_telemetry as _bootstrap_telemetry,
    trace_carrier_from_room_metadata as _trace_carrier_from_room_metadata_impl,
)
from .webrtc_room import connect_webrtc_room as _connect_webrtc_room
from .worker_bootstrap import run_worker as _run_worker

configure_logging(
    service="botcheck-agent",
    level=settings.log_level,
    json_logs=settings.log_json,
)

logger = logging.getLogger("botcheck.agent")
event_logger = structlog.get_logger("botcheck.agent.lifecycle")
_BRANCH_CLASSIFIER_CLIENT = HeuristicBranchClassifierClient()
_AGENT_TTS_BREAKERS = ProviderKeyedRegistry[AsyncCircuitBreaker[None]](
    lambda provider: AsyncCircuitBreaker[None](
        name=f"agent.live_tts.{provider}",
        failure_threshold=settings.tts_live_circuit_failure_threshold,
        recovery_timeout_s=settings.tts_live_circuit_recovery_s,
    )
)
_AGENT_AI_CALLER_BREAKER = AsyncCircuitBreaker[dict[str, object]](
    name="agent.ai_caller.openai",
    failure_threshold=settings.ai_caller_circuit_failure_threshold,
    recovery_timeout_s=settings.ai_caller_circuit_recovery_s,
)
_CALLBACK_HANDLER = _callback_handler.CallbackHandler(
    botcheck_api_url=settings.botcheck_api_url,
    harness_secret=settings.harness_secret,
    recording_upload_timeout_s=settings.recording_upload_timeout_s,
    final_ack_recovery_enabled=settings.final_ack_recovery_enabled,
    final_ack_recovery_log_path=settings.final_ack_recovery_log_path,
    callbacks_total=AGENT_API_CALLBACKS_TOTAL,
    turns_total=AGENT_TURNS_TOTAL,
    final_ack_total=AGENT_FINAL_ACK_TOTAL,
    event_logger=event_logger,
)
# Keep aioboto3 as a module attribute for existing test monkeypatch targets.
_AIOBOTO3_MODULE = aioboto3
# Callback transport surface aliases (kept as module symbols for monkeypatching).
_api_headers = _CALLBACK_HANDLER.api_headers
_is_retryable = _CALLBACK_HANDLER.is_retryable
_post_with_retry = _CALLBACK_HANDLER.post_with_retry
fetch_scenario = _CALLBACK_HANDLER.fetch_scenario
fetch_provider_runtime_context = _CALLBACK_HANDLER.fetch_provider_runtime_context
fetch_run_transport_context = _CALLBACK_HANDLER.fetch_run_transport_context
report_turn = _CALLBACK_HANDLER.report_turn
complete_run = _CALLBACK_HANDLER.complete_run
fail_run = _CALLBACK_HANDLER.fail_run
fail_run_with_details = _CALLBACK_HANDLER.fail_run_with_details
post_run_heartbeat = _CALLBACK_HANDLER.post_run_heartbeat
post_playground_event = _CALLBACK_HANDLER.post_playground_event
post_provider_circuit_state = _CALLBACK_HANDLER.post_provider_circuit_state
upload_run_recording = _CALLBACK_HANDLER.upload_run_recording
_trace_carrier_from_room_metadata = _trace_carrier_from_room_metadata_impl
_attach_trace_context_from_room_metadata = _attach_trace_context_from_room_metadata_impl
_build_loop_guard_payload = _final_ack_surface.build_loop_guard_payload


async def _read_cached_turn_wav(
    *,
    scenario: ScenarioDefinition,
    turn: Turn,
    tenant_id: str,
) -> bytes | None:
    return await _cache_surface.read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id=tenant_id,
        settings_obj=settings,
        hits_total=TTS_CACHE_HITS_TOTAL,
        misses_total=TTS_CACHE_MISSES_TOTAL,
        fallback_total=TTS_CACHE_FALLBACK_TOTAL,
    )


async def _publish_cached_wav(audio_source: rtc.AudioSource, wav_bytes: bytes) -> None:
    await _cache_surface.publish_cached_wav(audio_source, wav_bytes)


def _transport_protocol(run_metadata: dict[str, object] | None) -> str:
    return RunExecutionMetadata.model_validate(run_metadata or {}).transport_protocol()


def _build_prefetched_read_cached_turn_wav(
    *,
    scenario: ScenarioDefinition,
    tenant_id: str,
    run_metadata: dict[str, object] | None = None,
):
    if _transport_protocol(run_metadata) == "http":
        return _read_cached_turn_wav, None
    if not getattr(settings, "tts_cache_prefetch_enabled", True):
        return _read_cached_turn_wav, None
    if not _cache_surface.cache_client_configured(settings_obj=settings):
        return _read_cached_turn_wav, None

    prefetcher = _cache_surface.TurnAudioCachePrefetcher(
        scenario=scenario,
        tenant_id=tenant_id,
        settings_obj=settings,
        hits_total=TTS_CACHE_HITS_TOTAL,
        misses_total=TTS_CACHE_MISSES_TOTAL,
        fallback_total=TTS_CACHE_FALLBACK_TOTAL,
        logger_obj=logger,
        max_concurrency=getattr(settings, "tts_cache_prefetch_max_concurrency", 4),
    )
    prefetcher.start()
    scenario_id = scenario.id
    tenant_key = tenant_id

    async def _prefetched_read_cached_turn_wav(
        *,
        scenario: ScenarioDefinition,
        turn: Turn,
        tenant_id: str,
    ) -> bytes | None:
        if scenario.id != scenario_id or tenant_id != tenant_key:
            return await _read_cached_turn_wav(
                scenario=scenario,
                turn=turn,
                tenant_id=tenant_id,
            )
        return await prefetcher.get(turn=turn)

    return _prefetched_read_cached_turn_wav, prefetcher

# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------


_HeartbeatContext = _callback_handler.HeartbeatContext


async def finalize_run_with_greedy_ack(
    *,
    run_id: str,
    conversation: list[ConversationTurn],
    end_reason: str,
    primary: Literal["complete", "fail"] = "complete",
    failure_reason: str = "Harness execution failed",
    failure_error_code: str | None = None,
    failure_loop_guard: dict[str, object] | None = None,
) -> str:
    return await _final_ack_surface.finalize_run_with_greedy_ack(
        run_id=run_id,
        conversation=conversation,
        end_reason=end_reason,
        primary=primary,
        failure_reason=failure_reason,
        failure_error_code=failure_error_code,
        failure_loop_guard=failure_loop_guard,
        complete_run_fn=complete_run,
        fail_run_with_details_fn=fail_run_with_details,
        settings_obj=settings,
        final_ack_total=AGENT_FINAL_ACK_TOTAL,
        event_logger=event_logger,
    )


async def run_scenario(
    room: rtc.Room,
    scenario: ScenarioDefinition,
    run_id: str,
    *,
    tenant_id: str,
    heartbeat_state_callback: Callable[[int | None, str | None], None] | None = None,
    run_metadata: dict[str, object] | None = None,
    provider_runtime_context: dict[str, object] | None = None,
) -> list[ConversationTurn]:
    runtime_settings = RuntimeSettingsOverlay(
        base_settings=settings,
        overrides=build_settings_overrides(provider_runtime_context),
    )
    # Build the context from agent-level deps before delegating to the runner.
    read_cached_turn_wav_fn, cache_prefetcher = _build_prefetched_read_cached_turn_wav(
        scenario=scenario,
        tenant_id=tenant_id,
        run_metadata=run_metadata,
    )
    context = ScenarioRunContext(
        tenant_id=tenant_id,
        settings_obj=runtime_settings,
        wait_for_bot_fn=_wait_for_bot,
        bot_listener_cls=_BotListener,
        bot_audio_recorder_cls=_BotAudioRecorder,
        read_cached_turn_wav_fn=read_cached_turn_wav_fn,
        publish_cached_wav_fn=_publish_cached_wav,
        report_turn_fn=report_turn,
        upload_run_recording_fn=upload_run_recording,
        classify_branch_fn=classify_branch,
        classifier_client=_BRANCH_CLASSIFIER_CLIENT,
        livekit_api_cls=lk_api.LiveKitAPI,
        room_participant_identity_cls=lk_api.RoomParticipantIdentity,
        rtc_module=rtc,
        openai_module=openai,
        stt_plugin_modules={
            "deepgram": deepgram,
            "azure": azure,
        },
        logger_obj=logger,
        fetch_run_transport_context_fn=fetch_run_transport_context,
        heartbeat_state_callback=heartbeat_state_callback,
        run_metadata=run_metadata,
        tts_live_circuit_breaker=_AGENT_TTS_BREAKERS,
        ai_caller_circuit_breaker=_AGENT_AI_CALLER_BREAKER,
        provider_circuit_state_callback=post_provider_circuit_state,
        mock_agent_cls=MockAgent,
        post_playground_event_fn=post_playground_event,
    )
    try:
        return await _run_scenario_impl(
            room,
            scenario,
            run_id,
            context=context,
        )
    finally:
        if cache_prefetcher is not None:
            cache_prefetcher.cancel()


# ---------------------------------------------------------------------------
# LiveKit agent entrypoint
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext) -> None:
    await _run_entrypoint(
        ctx,
        settings_obj=settings,
        event_logger=event_logger,
        fetch_scenario_fn=fetch_scenario,
        fetch_run_transport_context_fn=fetch_run_transport_context,
        fetch_provider_runtime_context_fn=fetch_provider_runtime_context,
        run_scenario_fn=run_scenario,
        finalize_run_with_greedy_ack_fn=finalize_run_with_greedy_ack,
        post_run_heartbeat_fn=post_run_heartbeat,
        attach_trace_context_from_room_metadata_fn=_attach_trace_context_from_room_metadata,
        detach_trace_context_fn=detach_trace_context,
        heartbeat_pump_fn=_heartbeat.heartbeat_pump,
        heartbeat_context_cls=_HeartbeatContext,
        build_loop_guard_payload_fn=_build_loop_guard_payload,
        connect_webrtc_room_fn=lambda **kwargs: _connect_webrtc_room(
            rtc_module=rtc,
            logger_obj=logger,
            **kwargs,
        ),
        materialize_runtime_scenario_fn=_materialize_runtime_scenario,
        agent_runs_total=AGENT_RUNS_TOTAL,
        agent_run_duration_seconds=AGENT_RUN_DURATION_SECONDS,
    )


if __name__ == "__main__":
    _bootstrap_telemetry("botcheck-agent")
    start_metrics_server_if_enabled()
    _run_worker(
        settings_obj=settings,
        event_logger=event_logger,
        post_provider_circuit_state_fn=post_provider_circuit_state,
        cli_module=cli,
        worker_options_cls=WorkerOptions,
        # Keep harness run execution in-process so Prometheus counters updated by
        # the job entrypoint are visible on the main metrics endpoint.
        worker_options_kwargs={"job_executor_type": JobExecutorType.THREAD},
        entrypoint_fn=entrypoint,
        service_heartbeat_module=_service_heartbeat,
        threading_module=threading,
        shutdown_callbacks=(aclose_shared_chat_clients,),
    )
