from __future__ import annotations

import pytest

from src import worker_bootstrap


class _FakeEvent:
    def __init__(self) -> None:
        self.set_called = False

    def set(self) -> None:
        self.set_called = True


class _FakeThread:
    instances: list["_FakeThread"] = []

    def __init__(self, *, target, kwargs, name: str, daemon: bool) -> None:
        self.target = target
        self.kwargs = kwargs
        self.name = name
        self.daemon = daemon
        self.started = False
        self.join_timeout: float | None = None
        _FakeThread.instances.append(self)

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout


class _FakeThreading:
    Event = _FakeEvent
    Thread = _FakeThread


class _FakeCli:
    def __init__(self, *, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.ran = False
        self.options = None

    def run_app(self, options) -> None:
        self.ran = True
        self.options = options
        if self.should_raise:
            raise RuntimeError("boom")


class _FakeWorkerOptions:
    def __init__(self, *, entrypoint_fnc, agent_name: str, **kwargs) -> None:
        self.entrypoint_fnc = entrypoint_fnc
        self.agent_name = agent_name
        self.kwargs = kwargs


class _FakeServiceHeartbeatModule:
    @staticmethod
    def run_service_heartbeat_loop(**kwargs) -> None:
        return None


def test_run_worker_without_service_heartbeat() -> None:
    _FakeThread.instances.clear()
    cli = _FakeCli()

    worker_bootstrap.run_worker(
        settings_obj=type(
            "S",
            (),
            {
                "service_heartbeat_enabled": False,
                "service_heartbeat_interval_s": 30.0,
                "service_heartbeat_jitter_s": 2.0,
            },
        )(),
        event_logger=object(),
        post_provider_circuit_state_fn=lambda **kwargs: None,
        cli_module=cli,
        worker_options_cls=_FakeWorkerOptions,
        entrypoint_fn=lambda ctx: None,
        service_heartbeat_module=_FakeServiceHeartbeatModule,
        threading_module=_FakeThreading,
    )

    assert cli.ran is True
    assert _FakeThread.instances == []


def test_run_worker_passes_worker_option_overrides() -> None:
    _FakeThread.instances.clear()
    cli = _FakeCli()

    worker_bootstrap.run_worker(
        settings_obj=type(
            "S",
            (),
            {
                "service_heartbeat_enabled": False,
                "service_heartbeat_interval_s": 30.0,
                "service_heartbeat_jitter_s": 2.0,
            },
        )(),
        event_logger=object(),
        post_provider_circuit_state_fn=lambda **kwargs: None,
        cli_module=cli,
        worker_options_cls=_FakeWorkerOptions,
        worker_options_kwargs={"job_executor_type": "thread"},
        entrypoint_fn=lambda ctx: None,
        service_heartbeat_module=_FakeServiceHeartbeatModule,
        threading_module=_FakeThreading,
    )

    assert cli.options is not None
    assert cli.options.kwargs == {"job_executor_type": "thread"}


def test_run_worker_stops_service_heartbeat_on_failure() -> None:
    _FakeThread.instances.clear()
    cli = _FakeCli(should_raise=True)

    with pytest.raises(RuntimeError, match="boom"):
        worker_bootstrap.run_worker(
            settings_obj=type(
                "S",
                (),
                {
                    "service_heartbeat_enabled": True,
                    "service_heartbeat_interval_s": 30.0,
                    "service_heartbeat_jitter_s": 2.0,
                },
            )(),
            event_logger=object(),
            post_provider_circuit_state_fn=lambda **kwargs: None,
            cli_module=cli,
            worker_options_cls=_FakeWorkerOptions,
            entrypoint_fn=lambda ctx: None,
            service_heartbeat_module=_FakeServiceHeartbeatModule,
            threading_module=_FakeThreading,
        )

    assert len(_FakeThread.instances) == 1
    thread = _FakeThread.instances[0]
    assert thread.started is True
    assert isinstance(thread.kwargs["stop_event"], _FakeEvent)
    assert thread.kwargs["stop_event"].set_called is True
    assert thread.join_timeout == 2.0


def test_run_worker_runs_shutdown_callbacks() -> None:
    _FakeThread.instances.clear()
    cli = _FakeCli()
    called: list[str] = []

    async def _async_shutdown() -> None:
        called.append("async")

    def _sync_shutdown() -> None:
        called.append("sync")

    worker_bootstrap.run_worker(
        settings_obj=type(
            "S",
            (),
            {
                "service_heartbeat_enabled": False,
                "service_heartbeat_interval_s": 30.0,
                "service_heartbeat_jitter_s": 2.0,
            },
        )(),
        event_logger=object(),
        post_provider_circuit_state_fn=lambda **kwargs: None,
        cli_module=cli,
        worker_options_cls=_FakeWorkerOptions,
        entrypoint_fn=lambda ctx: None,
        service_heartbeat_module=_FakeServiceHeartbeatModule,
        threading_module=_FakeThreading,
        shutdown_callbacks=(_sync_shutdown, _async_shutdown),
    )

    assert called == ["sync", "async"]
