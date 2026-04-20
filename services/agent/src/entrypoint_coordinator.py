from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import suppress
from datetime import datetime
from typing import Any, Awaitable, Callable

from botcheck_observability.trace_contract import (
    ATTR_RUN_ID,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_KIND,
    ATTR_SCHEDULE_ID,
    ATTR_TENANT_ID,
    ATTR_TRANSPORT_KIND,
    ATTR_TRANSPORT_PROFILE_ID,
    ATTR_TRIGGER_SOURCE,
    SPAN_HARNESS_SESSION,
)
from botcheck_scenarios import ConversationTurn, ErrorCode, RunRoomMetadata
from pydantic import ValidationError
from opentelemetry import trace as otel_trace

from .graph import HarnessLoopError, HarnessMaxTurnsError

_tracer = otel_trace.get_tracer("botcheck.agent")


def _trace_attrs(
    *,
    run_id: str,
    scenario_id: str,
    scenario_kind: str,
    tenant_id: str,
    trigger_source: str,
    transport_kind: str,
    transport_profile_id: str | None = None,
    schedule_id: str | None = None,
) -> dict[str, str]:
    attrs = {
        ATTR_RUN_ID: run_id,
        ATTR_SCENARIO_ID: scenario_id,
        ATTR_SCENARIO_KIND: scenario_kind,
        ATTR_TENANT_ID: tenant_id,
        ATTR_TRIGGER_SOURCE: trigger_source,
        ATTR_TRANSPORT_KIND: transport_kind,
    }
    if transport_profile_id:
        attrs[ATTR_TRANSPORT_PROFILE_ID] = transport_profile_id
    if schedule_id:
        attrs[ATTR_SCHEDULE_ID] = schedule_id
    return attrs


async def run_entrypoint(
    ctx,
    *,
    settings_obj,
    event_logger,
    fetch_scenario_fn: Callable[[str], Awaitable[Any]],
    fetch_provider_runtime_context_fn: Callable[..., Awaitable[dict[str, object]]] | None,
    run_scenario_fn: Callable[..., Awaitable[list[ConversationTurn]]],
    finalize_run_with_greedy_ack_fn: Callable[..., Awaitable[str]],
    post_run_heartbeat_fn: Callable[..., Awaitable[None]],
    attach_trace_context_from_room_metadata_fn: Callable[[dict[str, object]], object | None],
    detach_trace_context_fn: Callable[[object | None], None],
    heartbeat_pump_fn: Callable[..., Awaitable[None]],
    heartbeat_context_cls,
    build_loop_guard_payload_fn: Callable[[BaseException], dict[str, object] | None],
    connect_webrtc_room_fn: Callable[..., Awaitable[Any]] | None = None,
    materialize_runtime_scenario_fn: Callable[..., Any] | None = None,
    agent_runs_total,
    agent_run_duration_seconds,
    fetch_run_transport_context_fn: Callable[[str], Awaitable[dict[str, object]]] | None = None,
) -> None:
    await ctx.connect()
    heartbeat_stop = asyncio.Event()
    heartbeat_task: asyncio.Task[None] | None = None
    trace_context_token: object | None = None
    heartbeat_context = heartbeat_context_cls()

    # Sentinel values so outer except-branches can always reference these names
    # even if the parse block exits early via ValidationError.
    run_id = ""
    scenario_id = ""
    scenario_kind = "graph"
    tenant_id = ""
    trigger_source = "manual"
    transport = "sip"
    transport_profile_id: str | None = None
    schedule_id: str | None = None
    execution_room = ctx.room
    remote_webrtc_room = None

    # Parse run metadata from room metadata.
    try:
        raw_metadata = ctx.room.metadata
        if not raw_metadata:
            event_logger.error("run_metadata_missing", room=ctx.room.name)
            return
        run_metadata = RunRoomMetadata.model_validate_json(raw_metadata)
        metadata = run_metadata.model_dump(mode="json", exclude_none=True)
        run_id = run_metadata.run_id
        scenario_id = run_metadata.scenario_id
        scenario_kind = str(run_metadata.scenario_kind or "graph").strip().lower()
        tenant_id = str(run_metadata.tenant_id or settings_obj.tenant_id)
        trigger_source = str(run_metadata.trigger_source or "manual").strip().lower()
        transport = str(run_metadata.transport or run_metadata.bot_protocol or "sip").strip().lower()
        transport_profile_id = str(run_metadata.transport_profile_id or "").strip() or None
        schedule_id = str(run_metadata.schedule_id or "").strip() or None
    except ValidationError as e:
        event_logger.error(
            "run_metadata_invalid",
            room=ctx.room.name,
            error=str(e),
        )
        return
    trace_context_token = attach_trace_context_from_room_metadata_fn(metadata)
    span_attrs = _trace_attrs(
        run_id=run_id,
        scenario_id=scenario_id,
        scenario_kind=scenario_kind,
        tenant_id=tenant_id,
        trigger_source=trigger_source,
        transport_kind=transport,
        transport_profile_id=transport_profile_id,
        schedule_id=schedule_id,
    )
    started = time.monotonic()
    conversation: list[ConversationTurn] = []

    try:
        with _tracer.start_as_current_span(SPAN_HARNESS_SESSION, attributes=span_attrs):
            event_logger.info(
                "run_started",
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_kind=scenario_kind,
                tenant_id=tenant_id,
                transport=transport,
            )

            if settings_obj.run_heartbeat_enabled:

                async def _send_heartbeat(seq: int, sent_at: datetime) -> None:
                    turn_number, listener_state = heartbeat_context.snapshot()
                    await post_run_heartbeat_fn(
                        run_id=run_id,
                        seq=seq,
                        sent_at=sent_at,
                        turn_number=turn_number,
                        listener_state=listener_state,
                    )

                heartbeat_task = asyncio.create_task(
                    heartbeat_pump_fn(
                        run_id=run_id,
                        stop_event=heartbeat_stop,
                        send_heartbeat_fn=_send_heartbeat,
                        interval_s=settings_obj.run_heartbeat_interval_s,
                        jitter_s=settings_obj.run_heartbeat_jitter_s,
                        logger_obj=event_logger,
                    )
                )
            scenario = await fetch_scenario_fn(scenario_id)
            if materialize_runtime_scenario_fn is not None:
                scenario = materialize_runtime_scenario_fn(
                    scenario=scenario,
                    metadata=metadata,
                )
            if transport == "webrtc":
                if connect_webrtc_room_fn is None:
                    raise RuntimeError(
                        "WebRTC transport requested without connect_webrtc_room_fn"
                    )
                if fetch_run_transport_context_fn is None:
                    raise RuntimeError(
                        "WebRTC transport requested without fetch_run_transport_context_fn"
                    )
                transport_context = await fetch_run_transport_context_fn(run_id)
                remote_webrtc_room = await connect_webrtc_room_fn(
                    run_metadata={**metadata, **transport_context},
                )
                execution_room = remote_webrtc_room
            provider_runtime_context: dict[str, object] | None = None
            if fetch_provider_runtime_context_fn is not None:
                try:
                    provider_runtime_context = await fetch_provider_runtime_context_fn(
                        tenant_id=tenant_id,
                        runtime_scope="agent",
                        tts_voice=str(run_metadata.effective_tts_voice or "").strip() or None,
                        stt_provider=str(run_metadata.effective_stt_provider or "").strip() or None,
                        stt_model=str(run_metadata.effective_stt_model or "").strip() or None,
                    )
                except Exception:
                    event_logger.warning(
                        "provider_runtime_context_fetch_failed",
                        run_id=run_id,
                        tenant_id=tenant_id,
                    )
            heartbeat_context.update(None, "running")
            run_kwargs: dict[str, object] = {
                "tenant_id": tenant_id,
                "heartbeat_state_callback": heartbeat_context.update,
            }
            if "run_metadata" in inspect.signature(run_scenario_fn).parameters:
                run_kwargs["run_metadata"] = metadata
            if "provider_runtime_context" in inspect.signature(run_scenario_fn).parameters:
                run_kwargs["provider_runtime_context"] = provider_runtime_context
            conversation = await run_scenario_fn(
                execution_room,
                scenario,
                run_id,
                **run_kwargs,
            )
            heartbeat_context.update(len(conversation), "finalizing")
            end_reason = (
                "timeout"
                if any(t.speaker == "bot" and t.text == "(timeout)" for t in conversation)
                else "max_turns_reached"
            )
            finalizer_used = await finalize_run_with_greedy_ack_fn(
                run_id=run_id,
                conversation=conversation,
                end_reason=end_reason,
                primary="complete",
                failure_reason="complete callback failed after successful scenario execution",
            )
            event_logger.info(
                "run_final_callback_acknowledged",
                run_id=run_id,
                finalizer=finalizer_used,
            )
            elapsed = time.monotonic() - started
            agent_runs_total.labels(outcome="success").inc()
            agent_run_duration_seconds.labels(outcome="success").observe(elapsed)
            event_logger.info(
                "run_completed",
                run_id=run_id,
                turn_count=len(conversation),
                elapsed_s=round(elapsed, 3),
            )
    except (HarnessLoopError, HarnessMaxTurnsError) as exc:
        heartbeat_context.update(None, "finalizing")
        elapsed = time.monotonic() - started
        agent_runs_total.labels(outcome="error").inc()
        agent_run_duration_seconds.labels(outcome="error").observe(elapsed)
        event_logger.exception(
            "run_failed_loop_guard",
            run_id=run_id,
            elapsed_s=round(elapsed, 3),
            error_type=type(exc).__name__,
        )
        end_reason = (
            "max_turns_reached"
            if isinstance(exc, HarnessMaxTurnsError)
            else "per_turn_loop_limit"
        )
        loop_guard_payload = build_loop_guard_payload_fn(exc)
        try:
            finalizer_used = await finalize_run_with_greedy_ack_fn(
                run_id=run_id,
                conversation=conversation,
                end_reason=end_reason,
                primary="fail",
                failure_reason=str(exc) or type(exc).__name__,
                failure_loop_guard=loop_guard_payload,
            )
            event_logger.info(
                "run_failure_callback_acknowledged",
                run_id=run_id,
                finalizer=finalizer_used,
                end_reason=end_reason,
            )
        except Exception:
            event_logger.warning(
                "run_failure_callback_unreconciled",
                run_id=run_id,
                end_reason=end_reason,
            )
    except asyncio.CancelledError:
        heartbeat_context.update(None, "cancelled")
        elapsed = time.monotonic() - started
        agent_runs_total.labels(outcome="error").inc()
        agent_run_duration_seconds.labels(outcome="error").observe(elapsed)
        event_logger.warning(
            "run_cancelled",
            run_id=run_id,
            elapsed_s=round(elapsed, 3),
        )
        try:
            finalizer_used = await finalize_run_with_greedy_ack_fn(
                run_id=run_id,
                conversation=conversation,
                end_reason="service_not_available",
                primary="fail",
                failure_reason="Harness task cancelled before terminal callback",
            )
            event_logger.info(
                "run_failure_callback_acknowledged",
                run_id=run_id,
                finalizer=finalizer_used,
                end_reason="service_not_available",
            )
        except Exception:
            event_logger.warning(
                "run_failure_callback_unreconciled",
                run_id=run_id,
                end_reason="service_not_available",
            )
        raise
    except Exception as exc:
        heartbeat_context.update(None, "finalizing")
        elapsed = time.monotonic() - started
        agent_runs_total.labels(outcome="error").inc()
        agent_run_duration_seconds.labels(outcome="error").observe(elapsed)
        event_logger.exception(
            "run_failed_unhandled",
            run_id=run_id,
            elapsed_s=round(elapsed, 3),
            error_type=type(exc).__name__,
        )
        failure_error_code = (
            ErrorCode.AI_CALLER_UNAVAILABLE.value
            if scenario_kind == "ai"
            else None
        )
        try:
            finalizer_used = await finalize_run_with_greedy_ack_fn(
                run_id=run_id,
                conversation=conversation,
                end_reason="service_not_available",
                primary="fail",
                failure_reason=str(exc) or type(exc).__name__,
                failure_error_code=failure_error_code,
            )
            event_logger.info(
                "run_failure_callback_acknowledged",
                run_id=run_id,
                finalizer=finalizer_used,
                end_reason="service_not_available",
            )
        except Exception:
            event_logger.warning(
                "run_failure_callback_unreconciled",
                run_id=run_id,
                end_reason="service_not_available",
            )
    finally:
        if remote_webrtc_room is not None:
            try:
                await remote_webrtc_room.disconnect()
            except Exception:
                event_logger.warning(
                    "webrtc_room_disconnect_failed",
                    run_id=run_id,
                    room=getattr(remote_webrtc_room, "name", None),
                )
        if heartbeat_task is not None:
            heartbeat_stop.set()
            try:
                await asyncio.wait_for(heartbeat_task, timeout=2.0)
            except asyncio.TimeoutError:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
        detach_trace_context_fn(trace_context_token)
