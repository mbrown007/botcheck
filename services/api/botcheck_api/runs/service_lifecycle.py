"""Run creation and dispatch orchestration helpers."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, NamedTuple

import httpx

import structlog
from botcheck_scenarios import AIRunContextSnapshot, RunRoomMetadata, ScenarioDefinition, parse_stt_config, parse_tts_voice
from botcheck_observability.trace_contract import (
    ATTR_RUN_ID,
    ATTR_SCENARIO_ID,
    ATTR_SCENARIO_KIND,
    ATTR_SCHEDULE_ID,
    ATTR_TENANT_ID,
    ATTR_TRANSPORT_KIND,
    ATTR_TRANSPORT_PROFILE_ID,
    ATTR_TRIGGER_SOURCE,
    SPAN_LIVEKIT_DISPATCH,
    SPAN_RUN_LIFECYCLE,
    SPAN_SIP_DISPATCH,
    current_w3c_trace_context,
)
from fastapi import HTTPException, Request
from livekit import api as lk_api
from opentelemetry import trace as otel_trace
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..admin.quota_service import assert_tenant_quota_available
from ..audit import write_audit_event
from ..auth.core import get_tenant_row, require_active_tenant_context
from ..capacity import (
    DEFAULT_SIP_CAPACITY_SCOPE,
    acquire_with_backoff,
    build_sip_slot_key,
    release_sip_slot,
    try_acquire_sip_slot,
)
from ..config import settings
from ..exceptions import (
    AI_SCENARIO_DISPATCH_UNAVAILABLE,
    ApiProblem,
    DESTINATION_INACTIVE,
    DESTINATION_NOT_FOUND,
    DESTINATIONS_DISABLED,
    HARNESS_UNAVAILABLE,
    SIP_CAPACITY_EXHAUSTED,
    SCHEDULED_RUN_THROTTLED,
    TTS_CACHE_UNAVAILABLE,
    WEBRTC_BOOTSTRAP_FAILED,
)
from ..models import (
    CacheStatus,
    DestinationProtocol,
    PlaygroundMode,
    RetentionProfile,
    RunRow,
    RunState,
    RunType,
    ScenarioKind,
    TenantRow,
)
from ..providers.service import resolve_tenant_provider_state
from ..providers.usage_service import assert_provider_quota_available
from ..runs.provider_state import harness_worker_snapshot, read_provider_circuit_snapshots
from ..scenarios.service import inspect_scenario_tts_cache, scenario_requires_tts_cache_preflight
from ..sip import SIPCredentials, load_sip_credentials
from ..stt_provider import assert_tenant_stt_config_available
from ..tts_provider import assert_tenant_tts_voice_available
from ..packs.service import get_bot_destination
from ..scenarios.store_service import (
    StoredAIScenario,
    get_ai_persona,
    get_preferred_ai_scenario_record_for_dispatch,
    get_ai_scenario,
    get_ai_scenario_by_scenario_id,
    get_scenario,
    get_scenario_cache_status,
    get_scenario_kind,
    reconcile_scenario_cache_status,
)
from .service_models import ResolvedRunTarget, RunResponse
from .service_state import normalize_cache_status
from .service_telephony import dispatch_sip_call, is_explicit_sip_endpoint, validate_sip_destination
from .service_trunk_pools import resolve_sip_trunk_for_dispatch
from .service_webrtc import resolve_bot_builder_preview_bootstrap
from .store_service import append_run_event, store_run

logger = logging.getLogger("botcheck.api.runs")
event_logger = structlog.get_logger("botcheck.api.runs.lifecycle")
_tracer = otel_trace.get_tracer("botcheck.api.runs")


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


def _cache_preflight_detail(*, scenario_id: str, status: str, missing_turn_ids: list[str]) -> str:
    if missing_turn_ids:
        missing = ", ".join(missing_turn_ids[:5])
        return (
            f"Scenario '{scenario_id}' requires prewarmed TTS cache before dispatch "
            f"(status={status}; missing turns: {missing}). Rebuild cache and retry."
        )
    return (
        f"Scenario '{scenario_id}' requires prewarmed TTS cache before dispatch "
        f"(status={status}). Rebuild cache and retry."
    )


def ai_room_metadata(snapshot: AIRunContextSnapshot | None) -> dict[str, str]:
    if snapshot is None:
        return {}
    return snapshot.room_metadata_items()


class ResolvedRunScenarioContext(NamedTuple):
    requested_ai_scenario_id: str | None
    internal_scenario_id: str
    scenario: ScenarioDefinition
    scenario_kind: str
    ai_scenario: StoredAIScenario | None
    ai_context_snapshot: AIRunContextSnapshot | None
    effective_tts_voice: str
    effective_stt_provider: str
    effective_stt_model: str


class PreparedRunDispatch(NamedTuple):
    bot_endpoint: str | None
    room_transport: str
    resolved_transport: str
    should_dispatch_sip: bool
    should_dispatch_mock: bool
    sip_creds: SIPCredentials | None
    slot_acquired: bool
    sip_capacity_scope: str
    sip_capacity_limit: int
    sip_slot_key: str
    redis_pool: object | None
    run_id: str
    room_name: str
    room_metadata: RunRoomMetadata
    webrtc_bootstrap_detail: dict[str, object] | None


async def _dispatch_prepared_run(
    *,
    tenant_id: str,
    scenario_id: str,
    scenario_kind: str,
    trigger_source: str,
    schedule_id: str | None,
    target: ResolvedRunTarget,
    prepared: PreparedRunDispatch,
    span_attrs: dict[str, Any],
) -> str | None:
    lkapi = lk_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    sip_trunk_id: str | None = None
    try:
        with _tracer.start_as_current_span(SPAN_LIVEKIT_DISPATCH, attributes=span_attrs):
            room_metadata = prepared.room_metadata.model_copy(update=current_w3c_trace_context())
            await lkapi.room.create_room(
                lk_api.CreateRoomRequest(
                    name=prepared.room_name,
                    metadata=room_metadata.model_dump_json(exclude_none=True),
                )
            )
            await lkapi.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    room=prepared.room_name,
                    agent_name="botcheck-harness",
                )
            )
            if prepared.should_dispatch_mock:
                await lkapi.agent_dispatch.create_dispatch(
                    lk_api.CreateAgentDispatchRequest(
                        room=prepared.room_name,
                        agent_name="botcheck-mockbot",
                    )
                )
        if prepared.should_dispatch_sip and prepared.sip_creds is not None:
            with _tracer.start_as_current_span(SPAN_SIP_DISPATCH, attributes=span_attrs):
                sip_trunk_id = await dispatch_sip_call(
                    lkapi=lkapi,
                    run_id=prepared.run_id,
                    creds=prepared.sip_creds,
                    bot_endpoint=prepared.bot_endpoint,
                    dial_target=target.dial_target,
                    room_name=prepared.room_name,
                    caller_id=target.caller_id,
                    trunk_id_override=target.trunk_id,
                )
            api_metrics.SIP_DISPATCH_TOTAL.labels(outcome="success").inc()
            event_logger.info(
                "run_sip_participant_dispatched",
                run_id=prepared.run_id,
                tenant_id=tenant_id,
                transport="sip",
                sip_trunk_id=sip_trunk_id,
            )
        elif prepared.should_dispatch_mock:
            event_logger.info(
                "run_mock_bot_dispatched",
                run_id=prepared.run_id,
                tenant_id=tenant_id,
                transport="mock",
                room=prepared.room_name,
            )
        event_logger.info(
            "run_room_created_harness_dispatched",
            run_id=prepared.run_id,
            tenant_id=tenant_id,
            room=prepared.room_name,
            transport=prepared.resolved_transport,
        )
        return sip_trunk_id
    except Exception:
        if prepared.slot_acquired:
            # Cannot use release_run_sip_slot_if_held() here — the RunRow has not
            # been persisted yet so there is no row to update or attach an event to.
            # Release the slot directly and log via the structured event logger so
            # capacity accounting remains traceable even without a persisted run event.
            await release_sip_slot(
                redis_pool=prepared.redis_pool,
                slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
                slot_key=prepared.sip_slot_key,
            )
            api_metrics.SIP_SLOTS_ACTIVE.dec()
            event_logger.info(
                "sip_slot_released_pre_persist",
                run_id=prepared.run_id,
                tenant_id=tenant_id,
                reason="dispatch_failed",
            )
        if prepared.should_dispatch_sip:
            api_metrics.SIP_DISPATCH_TOTAL.labels(outcome="error").inc()
            api_metrics.SIP_DISPATCH_ERRORS_TOTAL.labels(error_class="livekit_api_error").inc()
            event_logger.exception(
                "run_sip_dispatch_failed",
                run_id=prepared.run_id,
                tenant_id=tenant_id,
                room=prepared.room_name,
            )
            raise HTTPException(status_code=502, detail="SIP dispatch failed — run not created")
        event_logger.exception(
            "run_livekit_dispatch_failed_without_sip",
            run_id=prepared.run_id,
            tenant_id=tenant_id,
            room=prepared.room_name,
        )
        raise HTTPException(status_code=502, detail="LiveKit dispatch failed — run not created")
    finally:
        await lkapi.aclose()


async def _resolve_run_scenario_context(
    *,
    db: AsyncSession,
    body: Any,
    tenant_id: str,
    run_type: RunType,
    playground_mode: PlaygroundMode | None,
) -> ResolvedRunScenarioContext:
    requested_ai_scenario_id = str(getattr(body, "ai_scenario_id", "") or "").strip() or None
    requested_scenario_id = str(getattr(body, "scenario_id", "") or "").strip() or None
    internal_scenario_id = requested_scenario_id
    ai_scenario = None
    if requested_ai_scenario_id:
        ai_scenario = await get_ai_scenario(
            db,
            ai_scenario_id=requested_ai_scenario_id,
            tenant_id=tenant_id,
        )
        if ai_scenario is None:
            raise HTTPException(
                status_code=404,
                detail=f"AI scenario '{requested_ai_scenario_id}' not found",
            )
        internal_scenario_id = ai_scenario.scenario_id
        if requested_scenario_id and requested_scenario_id != internal_scenario_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Run target mismatch between scenario_id and ai_scenario_id "
                    f"({requested_scenario_id!r} != {internal_scenario_id!r})"
                ),
            )
    if not internal_scenario_id:
        raise HTTPException(status_code=422, detail="Either scenario_id or ai_scenario_id is required")

    scenario_data = await get_scenario(db, internal_scenario_id, tenant_id)
    if scenario_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{internal_scenario_id}' not found — POST /scenarios first",
        )
    scenario_kind = (
        await get_scenario_kind(db, internal_scenario_id, tenant_id)
    ) or ScenarioKind.GRAPH.value
    if scenario_kind == ScenarioKind.AI.value and not settings.feature_ai_scenarios_enabled:
        raise ApiProblem(
            status=503,
            error_code=AI_SCENARIO_DISPATCH_UNAVAILABLE,
            detail="AI scenarios are disabled",
        )

    ai_context_snapshot: AIRunContextSnapshot | None = None
    if scenario_kind == ScenarioKind.AI.value:
        if ai_scenario is None:
            ai_scenario = await get_ai_scenario_by_scenario_id(
                db,
                scenario_id=internal_scenario_id,
                tenant_id=tenant_id,
            )
        ai_context_snapshot = await build_ai_context_snapshot_for_run(
            db=db,
            scenario_id=internal_scenario_id,
            tenant_id=tenant_id,
            ai_scenario=ai_scenario,
        )
    scenario, _ = scenario_data
    scenario_protocol = str(scenario.bot.protocol.value).strip().lower()
    if run_type == RunType.PLAYGROUND:
        if scenario_protocol in {DestinationProtocol.SIP.value, DestinationProtocol.WEBRTC.value}:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Scenario protocol '{scenario_protocol}' is not supported for playground runs. "
                    "Use a mock or HTTP-backed scenario."
                ),
            )
        if playground_mode is None:
            raise HTTPException(status_code=422, detail="playground_mode is required for playground runs")

    effective_tts_voice = scenario.config.tts_voice
    effective_stt_provider = scenario.config.stt_provider
    effective_stt_model = scenario.config.stt_model
    if ai_scenario is not None:
        ai_tts_voice = ai_scenario.config.get("tts_voice")
        if isinstance(ai_tts_voice, str) and ai_tts_voice.strip():
            effective_tts_voice = ai_tts_voice
        ai_stt_provider = ai_scenario.config.get("stt_provider")
        if isinstance(ai_stt_provider, str) and ai_stt_provider.strip():
            effective_stt_provider = ai_stt_provider
        ai_stt_model = ai_scenario.config.get("stt_model")
        if isinstance(ai_stt_model, str) and ai_stt_model.strip():
            effective_stt_model = ai_stt_model

    return ResolvedRunScenarioContext(
        requested_ai_scenario_id=requested_ai_scenario_id,
        internal_scenario_id=internal_scenario_id,
        scenario=scenario,
        scenario_kind=scenario_kind,
        ai_scenario=ai_scenario,
        ai_context_snapshot=ai_context_snapshot,
        effective_tts_voice=effective_tts_voice,
        effective_stt_provider=effective_stt_provider,
        effective_stt_model=effective_stt_model,
    )


async def _run_runtime_preflight(
    *,
    db: AsyncSession,
    tenant: TenantRow | None,
    tenant_id: str,
    internal_scenario_id: str,
    scenario: ScenarioDefinition,
    run_type: RunType,
    direct_http_transport: bool,
    effective_tts_voice: str,
    effective_stt_provider: str,
    effective_stt_model: str,
) -> str:
    if not direct_http_transport and run_type != RunType.PLAYGROUND:
        await assert_tenant_tts_voice_available(
            db,
            tenant_id=tenant_id,
            tts_voice=effective_tts_voice,
            status_code=503,
            runtime_scope="agent",
        )
        await assert_tenant_stt_config_available(
            db,
            tenant_id=tenant_id,
            stt_provider=effective_stt_provider,
            stt_model=effective_stt_model,
            status_code=503,
            runtime_scope="agent",
        )
        parsed_tts_voice = parse_tts_voice(effective_tts_voice)
        resolved_tts = await resolve_tenant_provider_state(
            db,
            tenant_id=tenant_id,
            capability="tts",
            vendor=parsed_tts_voice.provider,
            runtime_scope="agent",
        )
        tts_provider_id = str(resolved_tts.get("provider_id") or "").strip()
        if tts_provider_id:
            try:
                await assert_provider_quota_available(
                    db,
                    tenant_id=tenant_id,
                    provider_id=tts_provider_id,
                    runtime_scope="agent",
                    capability="tts",
                    source="run_launch_tts",
                    estimated_usage={"requests": 1},
                )
            except ValueError:
                logger.warning(
                    "run.quota_preflight.skipped_unknown_provider",
                    extra={"provider_id": tts_provider_id, "tenant_id": tenant_id, "capability": "tts"},
                )
        parsed_stt_config = parse_stt_config(effective_stt_provider, effective_stt_model)
        resolved_stt = await resolve_tenant_provider_state(
            db,
            tenant_id=tenant_id,
            capability="stt",
            vendor=parsed_stt_config.provider,
            runtime_scope="agent",
        )
        stt_provider_id = str(resolved_stt.get("provider_id") or "").strip()
        if stt_provider_id:
            try:
                await assert_provider_quota_available(
                    db,
                    tenant_id=tenant_id,
                    provider_id=stt_provider_id,
                    runtime_scope="agent",
                    capability="stt",
                    source="run_launch_stt",
                    estimated_usage={"requests": 1},
                )
            except ValueError:
                logger.warning(
                    "run.quota_preflight.skipped_unknown_provider",
                    extra={"provider_id": stt_provider_id, "tenant_id": tenant_id, "capability": "stt"},
                )
    await assert_tenant_quota_available(
        db,
        tenant=tenant,
        tenant_id=tenant_id,
        quota_name="max_concurrent_runs",
    )
    await assert_tenant_quota_available(
        db,
        tenant=tenant,
        tenant_id=tenant_id,
        quota_name="max_runs_per_day",
    )
    scenario_cache_status = normalize_cache_status(
        await get_scenario_cache_status(db, internal_scenario_id, tenant_id),
        default=CacheStatus.COLD.value,
    )
    cache_inspection = None
    if not direct_http_transport and run_type != RunType.PLAYGROUND:
        if scenario_requires_tts_cache_preflight(scenario) and not settings.tts_cache_enabled:
            raise ApiProblem(
                status=503,
                error_code=TTS_CACHE_UNAVAILABLE,
                detail=(
                    f"Scenario '{internal_scenario_id}' requires prewarmed TTS cache before dispatch, "
                    "but TTS cache is disabled on this instance."
                ),
            )
        should_verify_cache = settings.tts_cache_enabled and (
            scenario_cache_status == CacheStatus.WARM.value
            or scenario_requires_tts_cache_preflight(scenario)
        )
        if should_verify_cache:
            cache_inspection = await inspect_scenario_tts_cache(
                settings,
                scenario=scenario,
                tenant_id=tenant_id,
            )
            scenario_cache_status = normalize_cache_status(
                cache_inspection.cache_status,
                default=CacheStatus.COLD.value,
            )
            await reconcile_scenario_cache_status(
                db,
                scenario_id=internal_scenario_id,
                tenant_id=tenant_id,
                cache_status=scenario_cache_status,
            )
        if scenario_requires_tts_cache_preflight(scenario):
            if cache_inspection is None:
                cache_inspection = await inspect_scenario_tts_cache(
                    settings,
                    scenario=scenario,
                    tenant_id=tenant_id,
                )
                scenario_cache_status = normalize_cache_status(
                    cache_inspection.cache_status,
                    default=CacheStatus.COLD.value,
                )
                await reconcile_scenario_cache_status(
                    db,
                    scenario_id=internal_scenario_id,
                    tenant_id=tenant_id,
                    cache_status=scenario_cache_status,
                )
            if scenario_cache_status != CacheStatus.WARM.value:
                missing_turn_ids = [
                    str(row["turn_id"])
                    for row in cache_inspection.turn_states
                    if row.get("status") != "cached"
                ]
                raise ApiProblem(
                    status=409,
                    error_code=TTS_CACHE_UNAVAILABLE,
                    detail=_cache_preflight_detail(
                        scenario_id=internal_scenario_id,
                        status=scenario_cache_status,
                        missing_turn_ids=missing_turn_ids,
                    ),
                )
    return scenario_cache_status


async def _prepare_run_dispatch(
    *,
    request: Request,
    tenant_id: str,
    trigger_source: str,
    schedule_id: str | None,
    run_type: RunType,
    playground_mode: PlaygroundMode | None,
    internal_scenario_id: str,
    scenario_kind: str,
    requested_ai_scenario_id: str | None,
    target: ResolvedRunTarget,
    ai_context_snapshot: AIRunContextSnapshot | None,
    effective_tts_voice: str,
    effective_stt_provider: str,
    effective_stt_model: str,
) -> PreparedRunDispatch:
    bot_endpoint = target.endpoint
    scenario_protocol = target.protocol
    room_transport = scenario_protocol
    if run_type == RunType.PLAYGROUND and playground_mode == PlaygroundMode.MOCK:
        room_transport = DestinationProtocol.MOCK.value
    elif run_type == RunType.PLAYGROUND and playground_mode == PlaygroundMode.DIRECT_HTTP:
        room_transport = DestinationProtocol.HTTP.value
    if scenario_protocol == "sip" and not settings.enable_outbound_sip:
        raise HTTPException(
            status_code=422,
            detail=(
                "Scenario protocol is 'sip' but outbound SIP is disabled on this instance. "
                "Set ENABLE_OUTBOUND_SIP=true or change the scenario bot.protocol to 'mock'."
            ),
        )
    await assert_harness_available_for_dispatch(request=request)
    should_dispatch_sip = (
        run_type != RunType.PLAYGROUND and settings.enable_outbound_sip and scenario_protocol == "sip"
    )
    should_dispatch_mock = run_type != RunType.PLAYGROUND and scenario_protocol == "mock"
    resolved_transport = (
        room_transport
        if run_type == RunType.PLAYGROUND
        else (
            "sip"
            if should_dispatch_sip
            else (
                "mock"
                if should_dispatch_mock
                else (
                    "http"
                    if target.protocol == DestinationProtocol.HTTP.value
                    else (
                        "webrtc"
                        if target.protocol == DestinationProtocol.WEBRTC.value
                        else "none"
                    )
                )
            )
        )
    )
    sip_creds: SIPCredentials | None = None
    slot_acquired = False
    sip_capacity_scope = target.capacity_scope
    sip_capacity_limit = target.capacity_limit
    sip_slot_key = build_sip_slot_key(tenant_id=tenant_id, capacity_scope=sip_capacity_scope)
    redis_pool = redis_pool_from_request(request)
    if should_dispatch_sip:
        validate_sip_destination(bot_endpoint)
        try:
            sip_creds = await load_sip_credentials(settings)
        except RuntimeError as exc:
            api_metrics.SIP_DISPATCH_ERRORS_TOTAL.labels(error_class="credential_error").inc()
            raise HTTPException(status_code=500, detail=f"SIP credentials error: {exc}") from exc
        if trigger_source in {"scheduled", "pack"}:
            slot_acquired = await acquire_with_backoff(
                redis_pool=redis_pool,
                max_slots=sip_capacity_limit,
                slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
                attempts=settings.schedule_dispatch_max_attempts,
                backoff_s=settings.schedule_dispatch_backoff_s,
                jitter_s=settings.schedule_dispatch_backoff_jitter_s,
                slot_key=sip_slot_key,
            )
        else:
            slot_acquired = await try_acquire_sip_slot(
                redis_pool=redis_pool,
                max_slots=sip_capacity_limit,
                slot_ttl_s=settings.sip_dispatch_slot_ttl_s,
                slot_key=sip_slot_key,
            )
        if slot_acquired:
            api_metrics.SIP_SLOTS_ACTIVE.inc()
        else:
            api_metrics.SIP_DISPATCH_TOTAL.labels(outcome="throttled").inc()
            if trigger_source == "scheduled":
                raise ApiProblem(
                    status=429,
                    error_code=SCHEDULED_RUN_THROTTLED,
                    detail="Scheduled run throttled by outbound SIP capacity",
                )
            if trigger_source == "pack":
                raise ApiProblem(
                    status=429,
                    error_code=SIP_CAPACITY_EXHAUSTED,
                    detail="Pack run item throttled by outbound SIP capacity",
                )
            raise ApiProblem(
                status=429,
                error_code=SIP_CAPACITY_EXHAUSTED,
                detail="Outbound SIP capacity exhausted; retry later",
            )

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    room_name = f"botcheck-{run_id}"
    room_metadata = RunRoomMetadata(
        run_id=run_id,
        scenario_id=internal_scenario_id,
        scenario_kind=scenario_kind,
        tenant_id=tenant_id,
        trigger_source=trigger_source,
        run_type=run_type.value,
        bot_protocol=room_transport,
        transport=room_transport,
        effective_tts_voice=effective_tts_voice,
        effective_stt_provider=effective_stt_provider,
        effective_stt_model=effective_stt_model,
        schedule_id=schedule_id,
        playground_mode=playground_mode.value if playground_mode is not None else None,
        ai_scenario_id=requested_ai_scenario_id,
        destination_id=target.destination_id,
        transport_profile_id=target.transport_profile_id,
        trunk_pool_id=target.trunk_pool_id,
        dial_target=target.dial_target,
        **ai_room_metadata(ai_context_snapshot),
    )
    webrtc_bootstrap_detail: dict[str, object] | None = None
    if target.protocol == DestinationProtocol.WEBRTC.value and target.webrtc_config is not None:
        try:
            bootstrap = await resolve_bot_builder_preview_bootstrap(
                webrtc_config=target.webrtc_config
            )
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            raise ApiProblem(
                status=502,
                error_code=WEBRTC_BOOTSTRAP_FAILED,
                detail=f"Bot-builder preview bootstrap failed: {type(exc).__name__}",
            ) from exc
        except ValueError as exc:
            raise ApiProblem(
                status=502,
                error_code=WEBRTC_BOOTSTRAP_FAILED,
                detail=f"Bot-builder preview bootstrap returned an invalid response: {exc}",
            ) from exc
        # Audit record: only non-session-specific fields. Bearer credentials are
        # never included, and only the room/session identifiers required for the
        # harness to re-locate the preview room remain in transient run-room metadata.
        webrtc_bootstrap_detail = {
            "provider": bootstrap.provider,
            "session_mode": bootstrap.session_mode,
            "agent_id": bootstrap.agent_id,
            "version_id": bootstrap.version_id,
            "join_timeout_s": bootstrap.join_timeout_s,
        }
        room_metadata = room_metadata.model_copy(
            update={
                "webrtc_provider": bootstrap.provider,
                "webrtc_session_mode": bootstrap.session_mode,
                "webrtc_session_id": bootstrap.session_id,
                "webrtc_remote_room_name": bootstrap.room_name,
                "webrtc_participant_name": bootstrap.participant_name,
                "webrtc_join_timeout_s": bootstrap.join_timeout_s,
                "webrtc_agent_id": bootstrap.agent_id,
                "webrtc_version_id": bootstrap.version_id,
            }
        )

    return PreparedRunDispatch(
        bot_endpoint=bot_endpoint,
        room_transport=room_transport,
        resolved_transport=resolved_transport,
        should_dispatch_sip=should_dispatch_sip,
        should_dispatch_mock=should_dispatch_mock,
        sip_creds=sip_creds,
        slot_acquired=slot_acquired,
        sip_capacity_scope=sip_capacity_scope,
        sip_capacity_limit=sip_capacity_limit,
        sip_slot_key=sip_slot_key,
        redis_pool=redis_pool,
        run_id=run_id,
        room_name=room_name,
        room_metadata=room_metadata,
        webrtc_bootstrap_detail=webrtc_bootstrap_detail,
    )


async def _persist_created_run(
    *,
    db: AsyncSession,
    body: Any,
    tenant_id: str,
    trigger_source: str,
    triggered_by: str | None,
    schedule_id: str | None,
    pack_run_id: str | None,
    auto_commit: bool,
    run_type: RunType,
    playground_mode: PlaygroundMode | None,
    playground_system_prompt: str | None,
    playground_tool_stubs: dict[str, object] | None,
    internal_scenario_id: str,
    requested_ai_scenario_id: str | None,
    scenario_kind: str,
    scenario: ScenarioDefinition,
    target: ResolvedRunTarget,
    scenario_cache_status: str,
    prepared: PreparedRunDispatch,
    ai_context_snapshot: AIRunContextSnapshot | None,
    sip_trunk_id: str | None,
) -> RunResponse:
    direct_http_transport = target.protocol == DestinationProtocol.HTTP.value
    webrtc_transport = target.protocol == DestinationProtocol.WEBRTC.value
    run = RunRow(
        run_id=prepared.run_id,
        scenario_id=internal_scenario_id,
        tenant_id=tenant_id,
        state="pending",
        livekit_room=prepared.room_name,
        trigger_source=trigger_source,
        run_type=run_type.value,
        playground_mode=playground_mode.value if playground_mode is not None else None,
        playground_system_prompt=playground_system_prompt if run_type == RunType.PLAYGROUND else None,
        playground_tool_stubs=playground_tool_stubs if run_type == RunType.PLAYGROUND else None,
        schedule_id=schedule_id,
        pack_run_id=pack_run_id,
        triggered_by=triggered_by,
        transport=prepared.resolved_transport,
        sip_slot_held=bool(prepared.slot_acquired and prepared.should_dispatch_sip),
        tts_cache_status_at_start=scenario_cache_status,
        destination_id_at_start=target.destination_id,
        transport_profile_id_at_start=target.transport_profile_id,
        dial_target_at_start=target.dial_target,
        direct_http_headers_at_start=target.headers if direct_http_transport else None,
        direct_http_config_at_start=target.direct_http_config if direct_http_transport else None,
        webrtc_config_at_start=target.webrtc_config if webrtc_transport else None,
        capacity_scope_at_start=prepared.sip_capacity_scope if prepared.should_dispatch_sip else None,
        capacity_limit_at_start=prepared.sip_capacity_limit if prepared.should_dispatch_sip else None,
        max_duration_s_at_start=scenario.config.max_duration_s,
        retention_profile=(
            body.retention_profile.value
            if body.retention_profile is not None
            else settings.default_retention_profile
        ),
    )
    await store_run(db, run)
    run_created_detail: dict[str, object] = {
        "to": RunState.PENDING.value,
        "scenario_id": internal_scenario_id,
        "scenario_kind": scenario_kind,
        "trigger": trigger_source,
        "run_type": run_type.value,
    }
    if playground_mode is not None:
        run_created_detail["playground_mode"] = playground_mode.value
    if requested_ai_scenario_id:
        run_created_detail["ai_scenario_id"] = requested_ai_scenario_id
    if schedule_id:
        run_created_detail["schedule_id"] = schedule_id
    if pack_run_id:
        run_created_detail["pack_run_id"] = pack_run_id
    if sip_trunk_id:
        run_created_detail["sip_trunk_id"] = sip_trunk_id
    if target.destination_id:
        run_created_detail["destination_id"] = target.destination_id
    if target.transport_profile_id:
        run_created_detail["transport_profile_id"] = target.transport_profile_id
    if target.trunk_pool_id:
        run_created_detail["trunk_pool_id"] = target.trunk_pool_id
    run_created_detail["dial_target"] = target.dial_target
    if prepared.webrtc_bootstrap_detail is not None:
        run_created_detail["webrtc_bootstrap"] = prepared.webrtc_bootstrap_detail
    if prepared.should_dispatch_sip:
        run_created_detail["sip_capacity_scope"] = prepared.sip_capacity_scope
        run_created_detail["sip_capacity_limit"] = prepared.sip_capacity_limit
        run_created_detail["sip_slot_key"] = prepared.sip_slot_key
    if ai_context_snapshot is not None:
        run_created_detail["ai_context"] = ai_context_snapshot.model_dump(
            mode="json",
            exclude_none=True,
        )
    await append_run_event(db, prepared.run_id, "run_created", run_created_detail)
    actor_type = "user" if trigger_source == "manual" else "service"
    actor_id = triggered_by or ("scheduler" if trigger_source == "scheduled" else "system")
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action="run.create",
        resource_type="run",
        resource_id=prepared.run_id,
        detail={
            "scenario_id": internal_scenario_id,
            "ai_scenario_id": requested_ai_scenario_id,
            "scenario_kind": scenario_kind,
            "run_type": run_type.value,
            "playground_mode": playground_mode.value if playground_mode is not None else None,
            "trigger_source": trigger_source,
            "schedule_id": schedule_id,
            "pack_run_id": pack_run_id,
            "destination_id": target.destination_id,
            "transport_profile_id": target.transport_profile_id,
            "trunk_pool_id": target.trunk_pool_id,
            "dial_target": target.dial_target,
            "transport": run.transport,
            "retention_profile": run.retention_profile,
        },
    )
    transport = run.transport
    api_metrics.RUNS_CREATED_TOTAL.labels(trigger_source=trigger_source, transport=transport).inc()
    if auto_commit:
        await db.commit()

    return RunResponse(
        run_id=prepared.run_id,
        scenario_id=internal_scenario_id,
        state=RunState.PENDING,
        run_type=run_type,
        playground_mode=playground_mode,
        livekit_room=prepared.room_name,
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        triggered_by=triggered_by,
        transport=transport,
        tts_cache_status_at_start=run.tts_cache_status_at_start,
        destination_id_at_start=run.destination_id_at_start,
        transport_profile_id_at_start=run.transport_profile_id_at_start,
        dial_target_at_start=run.dial_target_at_start,
        capacity_scope_at_start=run.capacity_scope_at_start,
        capacity_limit_at_start=run.capacity_limit_at_start,
        retention_profile=RetentionProfile(run.retention_profile),
    )


async def build_ai_context_snapshot_for_run(
    *,
    db: AsyncSession,
    scenario_id: str,
    tenant_id: str,
    ai_scenario: StoredAIScenario | None = None,
) -> AIRunContextSnapshot:
    if ai_scenario is None:
        ai_scenario = await get_ai_scenario_by_scenario_id(
            db,
            scenario_id=scenario_id,
            tenant_id=tenant_id,
        )
    selected = (
        await get_preferred_ai_scenario_record_for_dispatch(
            db,
            scenario_id=ai_scenario.scenario_id,
            tenant_id=tenant_id,
        )
        if ai_scenario is not None
        else None
    )
    persona_id = (
        (ai_scenario.persona_id if ai_scenario is not None else "").strip() or "persona_unknown"
    )
    persona_name: str | None = None
    if ai_scenario is not None:
        persona = await get_ai_persona(
            db,
            persona_id=ai_scenario.persona_id,
            tenant_id=tenant_id,
        )
        if persona is not None:
            persona_name = persona.display_name

    dataset_input = (
        (selected.input_text if selected is not None else "").strip()
        or f"AI scenario context unavailable for {scenario_id}"
    )
    expected_output = (
        (selected.expected_output if selected is not None else "").strip()
        or "Evaluate objective completion and policy compliance from transcript evidence."
    )
    scenario_objective = None
    if ai_scenario is not None:
        scenario_objective = (
            (ai_scenario.evaluation_objective or "").strip()
            or (ai_scenario.scenario_brief or "").strip()
            or (ai_scenario.scoring_profile or "").strip()
            or (ai_scenario.dataset_source or "").strip()
            or None
        )
    return AIRunContextSnapshot(
        dataset_input=dataset_input,
        expected_output=expected_output,
        persona_id=persona_id,
        persona_name=persona_name,
        scenario_brief=(ai_scenario.scenario_brief if ai_scenario is not None else "").strip() or None,
        scenario_objective=scenario_objective,
        opening_strategy=(
            (ai_scenario.opening_strategy if ai_scenario is not None else "").strip()
            or "wait_for_bot_greeting"
        ),
    )


def redis_pool_from_request(request: Request) -> object | None:
    return getattr(request.app.state, "arq_pool", None)


async def assert_harness_available_for_dispatch(*, request: Request) -> None:
    if not settings.run_dispatch_require_harness_healthy:
        return
    snapshots = await read_provider_circuit_snapshots(
        redis_pool_from_request(request),
        stale_after_s=settings.provider_circuit_snapshot_stale_s,
    )
    harness_snapshot = harness_worker_snapshot(snapshots)
    if harness_snapshot.state == "closed":
        return
    raise ApiProblem(
        status=503,
        error_code=HARNESS_UNAVAILABLE,
        detail=(
            "Harness agent unavailable — run dispatch is temporarily disabled "
            f"(state={harness_snapshot.state})"
        ),
    )


async def resolve_run_target(
    *,
    db: AsyncSession,
    tenant_id: str,
    scenario,
    body: Any,
) -> ResolvedRunTarget:
    request_destination_id = str(getattr(body, "destination_id", "") or "").strip() or None
    request_transport_profile_id = (
        str(getattr(body, "transport_profile_id", "") or "").strip() or None
    )
    request_trunk_pool_id = str(getattr(body, "trunk_pool_id", "") or "").strip() or None
    if (
        request_destination_id is not None
        and request_transport_profile_id is not None
        and request_destination_id != request_transport_profile_id
    ):
        raise HTTPException(
            status_code=422,
            detail="destination_id does not match transport_profile_id",
        )
    if request_trunk_pool_id is not None and (
        request_destination_id is not None or request_transport_profile_id is not None
    ):
        raise HTTPException(
            status_code=422,
            detail="trunk_pool_id cannot be combined with transport_profile_id",
        )
    transport_profile_id = request_transport_profile_id or request_destination_id
    destination_id = transport_profile_id
    protocol = scenario.bot.protocol.value
    endpoint = str(scenario.bot.endpoint)
    headers: dict[str, object] = {}
    direct_http_config: dict[str, object] | None = None
    webrtc_config: dict[str, object] | None = None
    caller_id = scenario.bot.caller_id or None
    trunk_id = scenario.bot.trunk_id or None
    trunk_pool_id: str | None = None
    capacity_scope = DEFAULT_SIP_CAPACITY_SCOPE
    capacity_limit = settings.max_concurrent_outbound_calls

    if transport_profile_id:
        if not settings.feature_destinations_enabled:
            raise ApiProblem(
                status=503,
                error_code=DESTINATIONS_DISABLED,
                detail="Destinations are disabled",
            )
        destination = await get_bot_destination(db, transport_profile_id, tenant_id)
        if destination is None:
            raise ApiProblem(
                status=404,
                error_code=DESTINATION_NOT_FOUND,
                detail="Destination not found",
            )
        if not destination.is_active:
            raise ApiProblem(
                status=422,
                error_code=DESTINATION_INACTIVE,
                detail="Destination is inactive",
            )

        protocol = destination.protocol
        if destination.endpoint:
            endpoint = destination.endpoint
        headers = dict(destination.headers or {})
        direct_http_config = dict(destination.direct_http_config or {}) or None
        webrtc_config = dict(destination.webrtc_config or {}) or None
        caller_id = destination.caller_id
        trunk_id = destination.trunk_id
        trunk_pool_id = destination.trunk_pool_id
        if protocol == "sip":
            if destination.capacity_scope:
                capacity_scope = destination.capacity_scope
            if isinstance(destination.effective_channels, int) and destination.effective_channels > 0:
                capacity_limit = destination.effective_channels
    elif request_trunk_pool_id is not None:
        trunk_pool_id = request_trunk_pool_id

    body_dial_target = str(getattr(body, "dial_target", "") or "").strip()
    body_bot_endpoint = str(getattr(body, "bot_endpoint", "") or "").strip()
    if body_dial_target and body_bot_endpoint and body_dial_target != body_bot_endpoint:
        raise HTTPException(
            status_code=422,
            detail="bot_endpoint does not match dial_target",
        )
    explicit_target = body_dial_target or body_bot_endpoint
    dial_target = endpoint
    if explicit_target:
        dial_target = explicit_target
        if is_explicit_sip_endpoint(explicit_target):
            endpoint = explicit_target

    if protocol == "sip":
        resolved_trunk = await resolve_sip_trunk_for_dispatch(
            db,
            tenant_id=tenant_id,
            trunk_id=trunk_id,
            trunk_pool_id=trunk_pool_id,
        )
        trunk_id = resolved_trunk.trunk_id or None
        trunk_pool_id = resolved_trunk.trunk_pool_id
    elif request_trunk_pool_id is not None:
        raise HTTPException(
            status_code=422,
            detail="trunk_pool_id is only valid for sip runs",
        )

    return ResolvedRunTarget(
        destination_id=destination_id,
        transport_profile_id=transport_profile_id,
        protocol=protocol,
        endpoint=endpoint,
        dial_target=dial_target,
        headers=headers,
        direct_http_config=direct_http_config,
        webrtc_config=webrtc_config,
        caller_id=caller_id,
        trunk_id=trunk_id,
        trunk_pool_id=trunk_pool_id,
        capacity_scope=capacity_scope,
        capacity_limit=capacity_limit,
    )


async def create_run_internal(
    *,
    request: Request,
    body: Any,
    tenant_id: str,
    trigger_source: str,
    triggered_by: str | None,
    schedule_id: str | None,
    db: AsyncSession,
    pack_run_id: str | None = None,
    auto_commit: bool = True,
    run_type: RunType = RunType.STANDARD,
    playground_mode: PlaygroundMode | None = None,
    playground_system_prompt: str | None = None,
    playground_tool_stubs: dict[str, object] | None = None,
) -> RunResponse:
    tenant = await get_tenant_row(db, tenant_id=tenant_id)
    await require_active_tenant_context(
        db,
        tenant_id=tenant_id,
        enforce_instance_tenant=not settings.shared_instance_mode,
    )
    scenario_context = await _resolve_run_scenario_context(
        db=db,
        body=body,
        tenant_id=tenant_id,
        run_type=run_type,
        playground_mode=playground_mode,
    )
    requested_ai_scenario_id = scenario_context.requested_ai_scenario_id
    internal_scenario_id = scenario_context.internal_scenario_id
    scenario = scenario_context.scenario
    scenario_kind = scenario_context.scenario_kind
    ai_scenario = scenario_context.ai_scenario
    ai_context_snapshot = scenario_context.ai_context_snapshot
    effective_tts_voice = scenario_context.effective_tts_voice
    effective_stt_provider = scenario_context.effective_stt_provider
    effective_stt_model = scenario_context.effective_stt_model
    target = await resolve_run_target(db=db, tenant_id=tenant_id, scenario=scenario, body=body)
    direct_http_transport = target.protocol == "http"
    if run_type == RunType.PLAYGROUND:
        if playground_mode == PlaygroundMode.DIRECT_HTTP and not direct_http_transport:
            raise HTTPException(
                status_code=422,
                detail="direct_http playground runs require an active HTTP transport profile",
            )
    scenario_cache_status = await _run_runtime_preflight(
        db=db,
        tenant=tenant,
        tenant_id=tenant_id,
        internal_scenario_id=internal_scenario_id,
        scenario=scenario,
        run_type=run_type,
        direct_http_transport=direct_http_transport,
        effective_tts_voice=effective_tts_voice,
        effective_stt_provider=effective_stt_provider,
        effective_stt_model=effective_stt_model,
    )
    dispatch = await _prepare_run_dispatch(
        request=request,
        tenant_id=tenant_id,
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        run_type=run_type,
        playground_mode=playground_mode,
        internal_scenario_id=internal_scenario_id,
        scenario_kind=scenario_kind,
        requested_ai_scenario_id=requested_ai_scenario_id,
        target=target,
        ai_context_snapshot=ai_context_snapshot,
        effective_tts_voice=effective_tts_voice,
        effective_stt_provider=effective_stt_provider,
        effective_stt_model=effective_stt_model,
    )
    span_attrs = _trace_attrs(
        run_id=dispatch.run_id,
        scenario_id=internal_scenario_id,
        scenario_kind=scenario_kind,
        tenant_id=tenant_id,
        trigger_source=trigger_source,
        transport_kind=dispatch.room_transport,
        transport_profile_id=target.transport_profile_id,
        schedule_id=schedule_id,
    )
    with _tracer.start_as_current_span(SPAN_RUN_LIFECYCLE, attributes=span_attrs):
        sip_trunk_id = await _dispatch_prepared_run(
            tenant_id=tenant_id,
            scenario_id=internal_scenario_id,
            scenario_kind=scenario_kind,
            trigger_source=trigger_source,
            schedule_id=schedule_id,
            target=target,
            prepared=dispatch,
            span_attrs=span_attrs,
        )
        return await _persist_created_run(
            db=db,
            body=body,
            tenant_id=tenant_id,
            trigger_source=trigger_source,
            triggered_by=triggered_by,
            schedule_id=schedule_id,
            pack_run_id=pack_run_id,
            auto_commit=auto_commit,
            run_type=run_type,
            playground_mode=playground_mode,
            playground_system_prompt=playground_system_prompt,
            playground_tool_stubs=playground_tool_stubs,
            internal_scenario_id=internal_scenario_id,
            requested_ai_scenario_id=requested_ai_scenario_id,
            scenario_kind=scenario_kind,
            scenario=scenario,
            target=target,
            scenario_cache_status=scenario_cache_status,
            prepared=dispatch,
            ai_context_snapshot=ai_context_snapshot,
            sip_trunk_id=sip_trunk_id,
        )
