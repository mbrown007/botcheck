from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable, Literal

from botcheck_scenarios import ConversationTurn

from .graph import HarnessLoopError, HarnessMaxTurnsError


def build_loop_guard_payload(exc: BaseException) -> dict[str, object] | None:
    if isinstance(exc, HarnessMaxTurnsError):
        payload: dict[str, object] = {
            "guard": "max_turns_reached",
            "effective_cap": exc.effective_cap,
        }
        if exc.turn_id:
            payload["turn_id"] = exc.turn_id
        if isinstance(exc.visit, int) and exc.visit > 0:
            payload["visit"] = exc.visit
        return payload

    if isinstance(exc, HarnessLoopError):
        return {
            "guard": "per_turn_loop_limit",
            "turn_id": exc.turn_id,
            "visit": exc.visit,
            "max_visits": exc.max_visits,
            "effective_cap": exc.effective_cap,
        }

    return None


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
    if not recovery_enabled:
        return
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "preferred_finalizer": preferred_finalizer,
        "end_reason": end_reason,
        "conversation_turns": len(conversation),
        "primary_error": f"{type(primary_error).__name__}: {primary_error}",
        "fallback_error": f"{type(fallback_error).__name__}: {fallback_error}",
        "replay_hints": {
            "complete_path": f"/runs/{run_id}/complete",
            "fail_path": f"/runs/{run_id}/fail",
        },
    }
    line = json.dumps(payload, separators=(",", ":"))
    path = Path(recovery_log_path)

    # Rare failure-path write: keep synchronous to avoid executor deadlocks in
    # constrained runtimes.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


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
    """
    Ensure final callback acknowledgement by attempting both finalizers.

    Primary callback is attempted first (`complete` for normal path, `fail` for
    exception path). If it fails, fallback finalizer is attempted. If both fail,
    a recovery record is persisted for replay and a RuntimeError is raised.
    """
    if primary == "complete":
        try:
            await complete_run_fn(
                run_id,
                conversation,
                end_reason=end_reason,
                end_source="harness",
            )
            final_ack_total.labels(outcome="complete_success").inc()
            return "complete"
        except Exception as complete_exc:
            event_logger.warning(
                "final_callback_complete_failed_fallback_to_fail",
                run_id=run_id,
                exc_info=True,
            )
            try:
                await fail_run_with_details_fn(
                    run_id=run_id,
                    reason=failure_reason,
                    end_reason=end_reason or "service_not_available",
                    error_code=failure_error_code,
                    loop_guard=failure_loop_guard,
                )
                final_ack_total.labels(outcome="fallback_fail_success").inc()
                return "fail"
            except Exception as fail_exc:
                final_ack_total.labels(outcome="unreconciled").inc()
                await persist_unreconciled_final_ack_fn(
                    run_id=run_id,
                    preferred_finalizer="complete",
                    conversation=conversation,
                    end_reason=end_reason,
                    primary_error=complete_exc,
                    fallback_error=fail_exc,
                )
                raise RuntimeError(
                    "Final callback unreconciled: both complete and fail callbacks failed"
                ) from fail_exc

    try:
        await fail_run_with_details_fn(
            run_id=run_id,
            reason=failure_reason,
            end_reason=end_reason or "service_not_available",
            error_code=failure_error_code,
            loop_guard=failure_loop_guard,
        )
        final_ack_total.labels(outcome="fail_success").inc()
        return "fail"
    except Exception as fail_exc:
        event_logger.warning(
            "final_callback_fail_failed_fallback_to_complete",
            run_id=run_id,
            exc_info=True,
        )
        try:
            await complete_run_fn(
                run_id,
                conversation,
                end_reason=end_reason or "service_not_available",
                end_source="harness",
            )
            final_ack_total.labels(outcome="fallback_complete_success").inc()
            return "complete"
        except Exception as complete_exc:
            final_ack_total.labels(outcome="unreconciled").inc()
            await persist_unreconciled_final_ack_fn(
                run_id=run_id,
                preferred_finalizer="fail",
                conversation=conversation,
                end_reason=end_reason,
                primary_error=fail_exc,
                fallback_error=complete_exc,
            )
            raise RuntimeError(
                "Final callback unreconciled: both fail and complete callbacks failed"
            ) from complete_exc
