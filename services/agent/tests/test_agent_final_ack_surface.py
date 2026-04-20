from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import ConversationTurn

from src import agent_final_ack_surface


def _conversation() -> list[ConversationTurn]:
    return [
        ConversationTurn(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="hello",
            audio_start_ms=0,
            audio_end_ms=100,
        )
    ]


def test_build_loop_guard_payload_passthrough(monkeypatch) -> None:
    sentinel = {"guard": "x"}
    mock_build = lambda exc: sentinel  # noqa: E731
    monkeypatch.setattr(agent_final_ack_surface._callback_handler, "build_loop_guard_payload", mock_build)
    assert agent_final_ack_surface.build_loop_guard_payload(RuntimeError("x")) == sentinel


@pytest.mark.asyncio
async def test_finalize_surface_binds_persist_with_runtime_settings(monkeypatch) -> None:
    persisted = {}
    persist_mock = AsyncMock()
    monkeypatch.setattr(agent_final_ack_surface._callback_handler, "persist_unreconciled_final_ack", persist_mock)

    async def _fake_finalize(**kwargs):
        nonlocal persisted
        persisted = kwargs
        await kwargs["persist_unreconciled_final_ack_fn"](
            run_id="run_1",
            preferred_finalizer="complete",
            conversation=_conversation(),
            end_reason="service_not_available",
            primary_error=RuntimeError("p"),
            fallback_error=RuntimeError("f"),
        )
        return "complete"

    monkeypatch.setattr(agent_final_ack_surface._callback_handler, "finalize_run_with_greedy_ack", _fake_finalize)

    settings_obj = type(
        "S",
        (),
        {
            "final_ack_recovery_enabled": True,
            "final_ack_recovery_log_path": "/tmp/recovery.jsonl",
        },
    )()

    result = await agent_final_ack_surface.finalize_run_with_greedy_ack(
        run_id="run_1",
        conversation=_conversation(),
        end_reason="max_turns_reached",
        complete_run_fn=AsyncMock(),
        fail_run_with_details_fn=AsyncMock(),
        settings_obj=settings_obj,
        final_ack_total=object(),
        event_logger=object(),
    )

    assert result == "complete"
    assert persisted["run_id"] == "run_1"
    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["recovery_enabled"] is True
    assert kwargs["recovery_log_path"] == "/tmp/recovery.jsonl"
