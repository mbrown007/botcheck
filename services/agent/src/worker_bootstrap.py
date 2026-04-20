from __future__ import annotations

import asyncio
import inspect
from datetime import datetime


def run_worker(
    *,
    settings_obj,
    event_logger,
    post_provider_circuit_state_fn,
    cli_module,
    worker_options_cls,
    worker_options_kwargs: dict[str, object] | None = None,
    entrypoint_fn,
    service_heartbeat_module,
    threading_module,
    shutdown_callbacks: tuple[object, ...] = (),
) -> None:
    service_heartbeat_stop = threading_module.Event()
    service_heartbeat_thread = None

    if settings_obj.service_heartbeat_enabled:

        async def _send_service_heartbeat(observed_at: datetime) -> None:
            await post_provider_circuit_state_fn(
                source="agent",
                provider="botcheck",
                service="harness",
                component="worker",
                state="closed",
                observed_at=observed_at,
            )

        service_heartbeat_thread = threading_module.Thread(
            target=service_heartbeat_module.run_service_heartbeat_loop,
            kwargs={
                "stop_event": service_heartbeat_stop,
                "send_heartbeat_fn": _send_service_heartbeat,
                "interval_s": settings_obj.service_heartbeat_interval_s,
                "jitter_s": settings_obj.service_heartbeat_jitter_s,
                "logger_obj": event_logger,
            },
            name="botcheck-agent-service-heartbeat",
            daemon=True,
        )
        service_heartbeat_thread.start()

    try:
        cli_module.run_app(
            worker_options_cls(
                entrypoint_fnc=entrypoint_fn,
                agent_name="botcheck-harness",
                **(worker_options_kwargs or {}),
            )
        )
    finally:
        service_heartbeat_stop.set()
        if service_heartbeat_thread is not None:
            service_heartbeat_thread.join(timeout=2.0)
        for shutdown_callback in shutdown_callbacks:
            try:
                result = shutdown_callback()
                if inspect.isawaitable(result):
                    asyncio.run(result)
            except Exception:
                pass  # shutdown errors must not mask the original exception or skip later callbacks
