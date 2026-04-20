from __future__ import annotations

from typing import Awaitable, Callable, Literal

from botcheck_scenarios import ConversationTurn

from . import callback_handler as _callback_handler


def build_loop_guard_payload(exc: BaseException) -> dict[str, object] | None:
    return _callback_handler.build_loop_guard_payload(exc)


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
    settings_obj,
    final_ack_total,
    event_logger,
) -> str:
    async def _persist_unreconciled_final_ack(
        *,
        run_id: str,
        preferred_finalizer: str,
        conversation: list[ConversationTurn],
        end_reason: str,
        primary_error: Exception,
        fallback_error: Exception,
    ) -> None:
        await _callback_handler.persist_unreconciled_final_ack(
            run_id=run_id,
            preferred_finalizer=preferred_finalizer,
            conversation=conversation,
            end_reason=end_reason,
            primary_error=primary_error,
            fallback_error=fallback_error,
            recovery_enabled=settings_obj.final_ack_recovery_enabled,
            recovery_log_path=settings_obj.final_ack_recovery_log_path,
        )

    return await _callback_handler.finalize_run_with_greedy_ack(
        run_id=run_id,
        conversation=conversation,
        end_reason=end_reason,
        primary=primary,
        failure_reason=failure_reason,
        failure_error_code=failure_error_code,
        failure_loop_guard=failure_loop_guard,
        complete_run_fn=complete_run_fn,
        fail_run_with_details_fn=fail_run_with_details_fn,
        persist_unreconciled_final_ack_fn=_persist_unreconciled_final_ack,
        final_ack_total=final_ack_total,
        event_logger=event_logger,
    )
