import json
from contextlib import AbstractContextManager
from types import SimpleNamespace

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
from botcheck_scenarios import ConversationTurn

from src import entrypoint_coordinator


class _FakeSpan(AbstractContextManager[None]):
    def __init__(self, recorder: list[tuple[str, dict[str, str] | None]], name: str, attributes):
        self._recorder = recorder
        self._name = name
        self._attributes = dict(attributes) if attributes is not None else None

    def __enter__(self):
        self._recorder.append((self._name, self._attributes))
        return None

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FakeTracer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def start_as_current_span(self, name: str, *, attributes=None):
        return _FakeSpan(self.calls, name, attributes)


class _MetricObserver:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def labels(self, **kwargs):
        self.calls.append(dict(kwargs))

        class _Observed:
            def inc(self, amount: float = 1.0) -> None:
                del amount

            def observe(self, value: float) -> None:
                del value

        return _Observed()


class _EventLogger:
    def info(self, *args, **kwargs):
        del args, kwargs

    def error(self, *args, **kwargs):
        del args, kwargs

    def warning(self, *args, **kwargs):
        del args, kwargs

    def exception(self, *args, **kwargs):
        del args, kwargs


class _FakeCtx:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.room = SimpleNamespace(name="room-1", metadata=json.dumps(metadata))

    async def connect(self) -> None:
        return None


class _FakeRemoteRoom:
    def __init__(self, name: str = "remote-room-1") -> None:
        self.name = name
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


async def test_run_entrypoint_emits_harness_session_span_with_canonical_attrs(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr(entrypoint_coordinator, "_tracer", tracer)

    metadata = {
        "run_id": "run_abc123",
        "scenario_id": "scenario-alpha",
        "scenario_kind": "graph",
        "tenant_id": "tenant-a",
        "trigger_source": "scheduled",
        "transport": "http",
        "transport_profile_id": "dest_http_1",
        "schedule_id": "sched_1",
    }
    ctx = _FakeCtx(metadata)
    detached: list[object | None] = []
    trace_token = object()

    async def _fetch_scenario(_scenario_id: str):
        return object()

    async def _fetch_provider_runtime_context(**kwargs):
        assert kwargs["tenant_id"] == "tenant-a"
        assert kwargs["runtime_scope"] == "agent"
        return {"feature_flags": {}, "tts": None, "stt": None}

    async def _run_scenario(_room, _scenario, _run_id, **kwargs):
        assert kwargs["run_metadata"] == metadata
        assert kwargs["provider_runtime_context"] == {"feature_flags": {}, "tts": None, "stt": None}
        return [ConversationTurn(turn_id="t1", turn_number=1, speaker="bot", text="hello")]

    async def _finalize(**kwargs):
        assert kwargs["run_id"] == "run_abc123"
        return "complete"

    async def _connect_webrtc_room(**_kwargs):
        return remote_room

    await entrypoint_coordinator.run_entrypoint(
        ctx,
        settings_obj=SimpleNamespace(
            run_heartbeat_enabled=False,
            run_heartbeat_interval_s=30,
            run_heartbeat_jitter_s=0,
            tenant_id="default",
        ),
        event_logger=_EventLogger(),
        fetch_scenario_fn=_fetch_scenario,
        fetch_run_transport_context_fn=None,
        fetch_provider_runtime_context_fn=_fetch_provider_runtime_context,
        run_scenario_fn=_run_scenario,
        finalize_run_with_greedy_ack_fn=_finalize,
        post_run_heartbeat_fn=None,
        attach_trace_context_from_room_metadata_fn=lambda _metadata: trace_token,
        detach_trace_context_fn=lambda token: detached.append(token),
        heartbeat_pump_fn=None,
        heartbeat_context_cls=lambda: SimpleNamespace(
            snapshot=lambda: (None, None),
            update=lambda *_args, **_kwargs: None,
        ),
        build_loop_guard_payload_fn=lambda exc: {"error": str(exc)},
        materialize_runtime_scenario_fn=None,
        agent_runs_total=_MetricObserver(),
        agent_run_duration_seconds=_MetricObserver(),
    )

    assert [name for name, _attrs in tracer.calls] == [SPAN_HARNESS_SESSION]
    attrs = tracer.calls[0][1] or {}
    assert attrs == {
        ATTR_RUN_ID: "run_abc123",
        ATTR_SCENARIO_ID: "scenario-alpha",
        ATTR_SCENARIO_KIND: "graph",
        ATTR_TENANT_ID: "tenant-a",
        ATTR_TRIGGER_SOURCE: "scheduled",
        ATTR_TRANSPORT_KIND: "http",
        ATTR_TRANSPORT_PROFILE_ID: "dest_http_1",
        ATTR_SCHEDULE_ID: "sched_1",
    }
    assert detached == [trace_token]


async def test_run_entrypoint_tolerates_provider_runtime_context_fetch_failure(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr(entrypoint_coordinator, "_tracer", tracer)

    metadata = {
        "run_id": "run_ctxfail",
        "scenario_id": "scenario-alpha",
        "scenario_kind": "graph",
        "tenant_id": "tenant-a",
        "trigger_source": "manual",
        "transport": "sip",
        "effective_tts_voice": "openai:alloy",
        "effective_stt_provider": "deepgram",
        "effective_stt_model": "nova-2-general",
    }
    ctx = _FakeCtx(metadata)

    async def _fetch_scenario(_scenario_id: str):
        return object()

    async def _fetch_provider_runtime_context(**_kwargs):
        raise RuntimeError("context fetch unavailable")

    async def _run_scenario(_room, _scenario, _run_id, **kwargs):
        assert kwargs["provider_runtime_context"] is None
        return [ConversationTurn(turn_id="t1", turn_number=1, speaker="bot", text="hello")]

    async def _finalize(**_kwargs):
        return "complete"

    async def _connect_webrtc_room(**_kwargs):
        return remote_room

    await entrypoint_coordinator.run_entrypoint(
        ctx,
        settings_obj=SimpleNamespace(
            run_heartbeat_enabled=False,
            run_heartbeat_interval_s=30,
            run_heartbeat_jitter_s=0,
            tenant_id="default",
        ),
        event_logger=_EventLogger(),
        fetch_scenario_fn=_fetch_scenario,
        fetch_run_transport_context_fn=None,
        fetch_provider_runtime_context_fn=_fetch_provider_runtime_context,
        run_scenario_fn=_run_scenario,
        finalize_run_with_greedy_ack_fn=_finalize,
        post_run_heartbeat_fn=None,
        attach_trace_context_from_room_metadata_fn=lambda _metadata: None,
        detach_trace_context_fn=lambda _token: None,
        heartbeat_pump_fn=None,
        heartbeat_context_cls=lambda: SimpleNamespace(
            snapshot=lambda: (None, None),
            update=lambda *_args, **_kwargs: None,
        ),
        build_loop_guard_payload_fn=lambda exc: {"error": str(exc)},
        materialize_runtime_scenario_fn=None,
        agent_runs_total=_MetricObserver(),
        agent_run_duration_seconds=_MetricObserver(),
    )


async def test_run_entrypoint_uses_remote_webrtc_room_for_webrtc_transport(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr(entrypoint_coordinator, "_tracer", tracer)

    metadata = {
        "run_id": "run_webrtc_1",
        "scenario_id": "scenario-alpha",
        "scenario_kind": "graph",
        "tenant_id": "tenant-a",
        "trigger_source": "manual",
        "transport": "webrtc",
    }
    ctx = _FakeCtx(metadata)
    remote_room = _FakeRemoteRoom()

    async def _fetch_scenario(_scenario_id: str):
        return object()

    async def _run_scenario(room, _scenario, _run_id, **kwargs):
        assert room is remote_room
        assert kwargs["run_metadata"] == metadata
        return [ConversationTurn(turn_id="t1", turn_number=1, speaker="bot", text="hello")]

    async def _finalize(**_kwargs):
        return "complete"

    async def _fetch_run_transport_context(run_id: str):
        assert run_id == "run_webrtc_1"
        return {
            "run_id": run_id,
            "webrtc_provider": "livekit",
            "webrtc_session_mode": "bot_builder_preview",
            "webrtc_remote_room_name": "remote-room-1",
            "webrtc_server_url": "wss://remote.example.test",
            "webrtc_participant_token": "token-123",
        }

    async def _connect_webrtc_room(**kwargs):
        assert kwargs["run_metadata"] == {
            **metadata,
            "run_id": "run_webrtc_1",
            "webrtc_provider": "livekit",
            "webrtc_session_mode": "bot_builder_preview",
            "webrtc_remote_room_name": "remote-room-1",
            "webrtc_server_url": "wss://remote.example.test",
            "webrtc_participant_token": "token-123",
        }
        return remote_room

    await entrypoint_coordinator.run_entrypoint(
        ctx,
        settings_obj=SimpleNamespace(
            run_heartbeat_enabled=False,
            run_heartbeat_interval_s=30,
            run_heartbeat_jitter_s=0,
            tenant_id="default",
        ),
        event_logger=_EventLogger(),
        fetch_scenario_fn=_fetch_scenario,
        fetch_run_transport_context_fn=_fetch_run_transport_context,
        fetch_provider_runtime_context_fn=None,
        run_scenario_fn=_run_scenario,
        finalize_run_with_greedy_ack_fn=_finalize,
        post_run_heartbeat_fn=None,
        attach_trace_context_from_room_metadata_fn=lambda _metadata: None,
        detach_trace_context_fn=lambda _token: None,
        heartbeat_pump_fn=None,
        heartbeat_context_cls=lambda: SimpleNamespace(
            snapshot=lambda: (None, None),
            update=lambda *_args, **_kwargs: None,
        ),
        build_loop_guard_payload_fn=lambda exc: {"error": str(exc)},
        connect_webrtc_room_fn=_connect_webrtc_room,
        materialize_runtime_scenario_fn=None,
        agent_runs_total=_MetricObserver(),
        agent_run_duration_seconds=_MetricObserver(),
    )

    assert remote_room.disconnect_calls == 1
