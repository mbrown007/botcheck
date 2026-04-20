from __future__ import annotations

from typing import Awaitable, Callable, Literal

from botcheck_scenarios import ConversationTurn

from .callback_final_ack import (
    build_loop_guard_payload as _build_loop_guard_payload,
)
from .callback_final_ack import (
    finalize_run_with_greedy_ack as _finalize_run_with_greedy_ack,
)
from .callback_final_ack import (
    persist_unreconciled_final_ack as _persist_unreconciled_final_ack,
)
from .callback_transport import CallbackTransport
from .heartbeat_context import HeartbeatContext


def build_loop_guard_payload(exc: BaseException) -> dict[str, object] | None:
    return _build_loop_guard_payload(exc)


async def persist_unreconciled_final_ack(
    *,
    run_id: str,
    preferred_finalizer: str,
    conversation: list[ConversationTurn],
    end_reason: str,
    primary_error: Exception,
    fallback_error: Exception,
    recovery_enabled: bool,
    recovery_log_path: str,
) -> None:
    await _persist_unreconciled_final_ack(
        run_id=run_id,
        preferred_finalizer=preferred_finalizer,
        conversation=conversation,
        end_reason=end_reason,
        primary_error=primary_error,
        fallback_error=fallback_error,
        recovery_enabled=recovery_enabled,
        recovery_log_path=recovery_log_path,
    )


async def finalize_run_with_greedy_ack(
    *,
    run_id: str,
    conversation: list[ConversationTurn],
    end_reason: str,
    primary: Literal["complete", "fail"] = "complete",
    failure_reason: str = "Harness execution failed",
    failure_error_code: str | None = None,
    failure_loop_guard: dict[str, object] | None = None,
    complete_run_fn: Callable[..., Awaitable[None]],
    fail_run_with_details_fn: Callable[..., Awaitable[None]],
    persist_unreconciled_final_ack_fn: Callable[..., Awaitable[None]],
    final_ack_total,
    event_logger,
) -> str:
    return await _finalize_run_with_greedy_ack(
        run_id=run_id,
        conversation=conversation,
        end_reason=end_reason,
        primary=primary,
        failure_reason=failure_reason,
        failure_error_code=failure_error_code,
        failure_loop_guard=failure_loop_guard,
        complete_run_fn=complete_run_fn,
        fail_run_with_details_fn=fail_run_with_details_fn,
        persist_unreconciled_final_ack_fn=persist_unreconciled_final_ack_fn,
        final_ack_total=final_ack_total,
        event_logger=event_logger,
    )


class CallbackHandler(CallbackTransport):
    def __init__(
        self,
        *,
        botcheck_api_url: str,
        harness_secret: str,
        recording_upload_timeout_s: float,
        final_ack_recovery_enabled: bool,
        final_ack_recovery_log_path: str,
        callbacks_total,
        turns_total,
        final_ack_total,
        event_logger,
    ) -> None:
        super().__init__(
            botcheck_api_url=botcheck_api_url,
            harness_secret=harness_secret,
            recording_upload_timeout_s=recording_upload_timeout_s,
            callbacks_total=callbacks_total,
            turns_total=turns_total,
        )
        self._final_ack_recovery_enabled = final_ack_recovery_enabled
        self._final_ack_recovery_log_path = final_ack_recovery_log_path
        self._final_ack_total = final_ack_total
        self._event_logger = event_logger

    async def fail_run(
        self,
        run_id: str,
        reason: str,
        *,
        end_reason: str = "service_not_available",
    ) -> None:
        await self.fail_run_with_details(
            run_id,
            reason,
            end_reason=end_reason,
            error_code=None,
            loop_guard=None,
        )

    async def persist_unreconciled_final_ack(
        self,
        *,
        run_id: str,
        preferred_finalizer: str,
        conversation: list[ConversationTurn],
        end_reason: str,
        primary_error: Exception,
        fallback_error: Exception,
    ) -> None:
        await persist_unreconciled_final_ack(
            run_id=run_id,
            preferred_finalizer=preferred_finalizer,
            conversation=conversation,
            end_reason=end_reason,
            primary_error=primary_error,
            fallback_error=fallback_error,
            recovery_enabled=self._final_ack_recovery_enabled,
            recovery_log_path=self._final_ack_recovery_log_path,
        )

    async def finalize_run_with_greedy_ack(
        self,
        *,
        run_id: str,
        conversation: list[ConversationTurn],
        end_reason: str,
        primary: Literal["complete", "fail"] = "complete",
        failure_reason: str = "Harness execution failed",
        failure_error_code: str | None = None,
        failure_loop_guard: dict[str, object] | None = None,
    ) -> str:
        return await finalize_run_with_greedy_ack(
            run_id=run_id,
            conversation=conversation,
            end_reason=end_reason,
            primary=primary,
            failure_reason=failure_reason,
            failure_error_code=failure_error_code,
            failure_loop_guard=failure_loop_guard,
            complete_run_fn=self.complete_run,
            fail_run_with_details_fn=self.fail_run_with_details,
            persist_unreconciled_final_ack_fn=self.persist_unreconciled_final_ack,
            final_ack_total=self._final_ack_total,
            event_logger=self._event_logger,
        )
