from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src import scenario_bot_turn

from botcheck_scenarios import ConversationTurn


@pytest.mark.asyncio
async def test_execute_bot_listen_block_reports_and_advances(monkeypatch) -> None:
    conversation: list[ConversationTurn] = []
    report_turn = AsyncMock()
    graph = SimpleNamespace(advance=Mock())

    listened_turn = ConversationTurn(
        turn_id="t_bot",
        turn_number=1,
        speaker="bot",
        text="I can help with billing",
        audio_start_ms=100,
        audio_end_ms=250,
    )
    monkeypatch.setattr(scenario_bot_turn, "listen_bot_turn", AsyncMock(return_value=listened_turn))
    monkeypatch.setattr(
        scenario_bot_turn,
        "classify_branch_condition",
        AsyncMock(return_value=("billing", "I can help with billing")),
    )

    turn_def = SimpleNamespace(
        id="t_bot",
        config=SimpleNamespace(pre_listen_wait_s=0, listen_for_s=4.5),
        branching=SimpleNamespace(cases=[SimpleNamespace(condition="billing")], default="t_default"),
    )
    settings_obj = SimpleNamespace(
        branch_classifier_model="model-x",
        branch_classifier_timeout_s=2.0,
    )

    turn_number, chosen = await scenario_bot_turn.execute_bot_listen_block(
        turn_def=turn_def,
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        scenario=SimpleNamespace(name="n", description="d"),
        settings_obj=settings_obj,
        bot_listener=object(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=graph,
        now_ms_fn=lambda: 0,
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=object(),
    )

    assert turn_number == 1
    assert chosen == "billing"
    assert conversation == [listened_turn]
    report_turn.assert_awaited_once()
    graph.advance.assert_called_once_with("billing")
    scenario_bot_turn.listen_bot_turn.assert_awaited_once()
    assert scenario_bot_turn.listen_bot_turn.await_args.kwargs["listen_for_s"] == 4.5
