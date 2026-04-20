from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src import scenario_harness_turn

from botcheck_scenarios import ConversationTurn


def _harness_turn_def(*, wait_for_response: bool, branching=None):
    return SimpleNamespace(
        id="t_h",
        content=SimpleNamespace(text="hello", silence_s=None, audio_file=None, dtmf=None),
        listen=wait_for_response,
        branching=branching,
        adversarial=False,
        technique=None,
        config=SimpleNamespace(pre_speak_pause_s=0, post_speak_pause_s=0, retry_on_silence=0),
    )


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_no_wait_reports_once_and_advances(monkeypatch) -> None:
    report_turn = AsyncMock()
    graph = SimpleNamespace(advance=Mock())
    response_visits: dict[str, int] = defaultdict(int)
    conversation: list[ConversationTurn] = []

    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", AsyncMock())
    listen_bot_turn = AsyncMock()
    monkeypatch.setattr(scenario_harness_turn, "listen_bot_turn", listen_bot_turn)
    monkeypatch.setattr(scenario_harness_turn, "classify_branch_condition", AsyncMock())

    now_values = iter((100, 220))
    turn_number = await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=_harness_turn_def(wait_for_response=False),
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        response_visit_counts=response_visits,
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=graph,
        now_ms_fn=lambda: next(now_values),
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=object(),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert turn_number == 1
    assert len(conversation) == 1
    assert conversation[0].speaker == "harness"
    report_turn.assert_awaited_once()
    graph.advance.assert_called_once_with("default")
    listen_bot_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_wait_branching_reports_harness_and_bot(monkeypatch) -> None:
    report_turn = AsyncMock()
    graph = SimpleNamespace(advance=Mock())
    response_visits: dict[str, int] = defaultdict(int)
    conversation: list[ConversationTurn] = []

    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", AsyncMock())
    monkeypatch.setattr(
        scenario_harness_turn,
        "listen_bot_turn",
        AsyncMock(
            return_value=ConversationTurn(
                turn_id="t_h_bot",
                turn_number=2,
                speaker="bot",
                text="billing support",
                audio_start_ms=300,
                audio_end_ms=500,
            )
        ),
    )
    monkeypatch.setattr(
        scenario_harness_turn,
        "classify_branch_condition",
        AsyncMock(return_value=("billing", "billing support")),
    )

    now_values = iter((100, 220))
    turn_number = await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=_harness_turn_def(
            wait_for_response=True,
            branching=SimpleNamespace(cases=[SimpleNamespace(condition="billing")], default="t_d"),
        ),
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        response_visit_counts=response_visits,
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=graph,
        now_ms_fn=lambda: next(now_values),
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=object(),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert turn_number == 2
    assert len(conversation) == 2
    assert response_visits["t_h_bot"] == 1
    assert report_turn.await_count == 2
    graph.advance.assert_called_once_with("billing")
    assert scenario_harness_turn.listen_bot_turn.await_args.kwargs["listen_for_s"] is None


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_threads_listen_for_s_override(monkeypatch) -> None:
    report_turn = AsyncMock()
    response_visits: dict[str, int] = defaultdict(int)
    conversation: list[ConversationTurn] = []

    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", AsyncMock())
    listen_bot_turn = AsyncMock(
        return_value=ConversationTurn(
            turn_id="t_h_bot",
            turn_number=2,
            speaker="bot",
            text="billing support",
            audio_start_ms=300,
            audio_end_ms=500,
        )
    )
    monkeypatch.setattr(scenario_harness_turn, "listen_bot_turn", listen_bot_turn)
    monkeypatch.setattr(
        scenario_harness_turn,
        "classify_branch_condition",
        AsyncMock(return_value=("default", None)),
    )

    turn_def = _harness_turn_def(wait_for_response=True)
    turn_def.config.listen_for_s = 3.25
    now_values = iter((100, 220))
    await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=turn_def,
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        response_visit_counts=response_visits,
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=None,
        now_ms_fn=lambda: next(now_values),
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=object(),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert listen_bot_turn.await_args.kwargs["listen_for_s"] == 3.25


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_rejects_dtmf_until_implemented() -> None:
    turn_def = SimpleNamespace(
        id="t_h",
        content=SimpleNamespace(text=None, silence_s=None, audio_file=None, dtmf="1"),
        listen=False,
        branching=None,
        adversarial=False,
        technique=None,
        config=SimpleNamespace(pre_speak_pause_s=0, post_speak_pause_s=0, retry_on_silence=0),
    )

    with pytest.raises(RuntimeError, match="dtmf"):
        await scenario_harness_turn.execute_harness_prompt_block(
            turn_def=turn_def,
            turn_number=0,
            turn_visit=1,
            run_id="run_1",
            conversation=[],
            response_visit_counts=defaultdict(int),
            scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
            settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
            tenant_id="tenant-a",
            bot_listener=object(),
            audio_source=object(),
            tts=object(),
            read_cached_turn_wav_fn=AsyncMock(),
            publish_cached_wav_fn=AsyncMock(),
            timeout=10.0,
            effective_merge_window_s=0.7,
            effective_endpointing_ms=1200,
            classify_branch_fn=object(),
            classifier_client=object(),
            report_turn_fn=AsyncMock(),
            graph_traversal=None,
            now_ms_fn=lambda: 0,
            emit_heartbeat_state_fn=lambda **kwargs: None,
            logger_obj=object(),
            tts_live_circuit_breaker=None,
            tts_circuit_bridge=None,
        )


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_retries_on_silence_then_accepts_speech(
    monkeypatch,
) -> None:
    report_turn = AsyncMock()
    response_visits: dict[str, int] = defaultdict(int)
    conversation: list[ConversationTurn] = []
    play_audio = AsyncMock()

    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", play_audio)
    monkeypatch.setattr(
        scenario_harness_turn,
        "listen_bot_turn",
        AsyncMock(
            side_effect=[
                ConversationTurn(
                    turn_id="t_h_bot",
                    turn_number=2,
                    speaker="bot",
                    text="(timeout)",
                    audio_start_ms=300,
                    audio_end_ms=500,
                ),
                ConversationTurn(
                    turn_id="t_h_bot",
                    turn_number=2,
                    speaker="bot",
                    text="billing support",
                    audio_start_ms=600,
                    audio_end_ms=800,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        scenario_harness_turn,
        "classify_branch_condition",
        AsyncMock(return_value=("default", None)),
    )

    turn_def = _harness_turn_def(wait_for_response=True)
    turn_def.config.retry_on_silence = 1
    now_values = iter((100, 220, 400, 520))
    turn_number = await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=turn_def,
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        response_visit_counts=response_visits,
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=None,
        now_ms_fn=lambda: next(now_values),
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=SimpleNamespace(info=Mock()),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert turn_number == 2
    assert play_audio.await_count == 2
    assert scenario_harness_turn.listen_bot_turn.await_count == 2
    assert [turn.speaker for turn in conversation] == ["harness", "bot"]
    assert conversation[0].audio_start_ms == 100
    assert conversation[0].audio_end_ms == 520
    assert conversation[1].text == "billing support"
    assert report_turn.await_count == 2
    assert response_visits["t_h_bot"] == 1


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_reports_final_timeout_after_retry_budget(
    monkeypatch,
) -> None:
    report_turn = AsyncMock()
    response_visits: dict[str, int] = defaultdict(int)
    conversation: list[ConversationTurn] = []
    play_audio = AsyncMock()

    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", play_audio)
    monkeypatch.setattr(
        scenario_harness_turn,
        "listen_bot_turn",
        AsyncMock(
            side_effect=[
                ConversationTurn(
                    turn_id="t_h_bot",
                    turn_number=2,
                    speaker="bot",
                    text="(timeout)",
                    audio_start_ms=300,
                    audio_end_ms=500,
                ),
                ConversationTurn(
                    turn_id="t_h_bot",
                    turn_number=2,
                    speaker="bot",
                    text="(timeout)",
                    audio_start_ms=600,
                    audio_end_ms=800,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        scenario_harness_turn,
        "classify_branch_condition",
        AsyncMock(return_value=("default", None)),
    )

    turn_def = _harness_turn_def(wait_for_response=True)
    turn_def.config.retry_on_silence = 1
    now_values = iter((100, 220, 400, 520))
    turn_number = await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=turn_def,
        turn_number=0,
        turn_visit=1,
        run_id="run_1",
        conversation=conversation,
        response_visit_counts=response_visits,
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=None,
        now_ms_fn=lambda: next(now_values),
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=SimpleNamespace(info=Mock()),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert turn_number == 2
    assert play_audio.await_count == 2
    assert scenario_harness_turn.listen_bot_turn.await_count == 2
    assert [turn.speaker for turn in conversation] == ["harness", "bot"]
    assert conversation[1].text == "(timeout)"
    assert report_turn.await_count == 2
    assert response_visits["t_h_bot"] == 1


@pytest.mark.asyncio
async def test_execute_harness_prompt_block_listen_false_ignores_retry_budget(
    monkeypatch,
) -> None:
    """retry_on_silence is silently ignored when listen=False; only one play occurs."""
    play_audio = AsyncMock()
    monkeypatch.setattr(scenario_harness_turn, "play_harness_turn_audio", play_audio)

    turn_def = _harness_turn_def(wait_for_response=False)
    turn_def.config.retry_on_silence = 3

    report_turn = AsyncMock()
    await scenario_harness_turn.execute_harness_prompt_block(
        turn_def=turn_def,
        turn_number=0,
        turn_visit=1,
        run_id="run_no_listen",
        conversation=[],
        response_visit_counts=defaultdict(int),
        scenario=SimpleNamespace(config=SimpleNamespace(inter_turn_pause_s=0)),
        settings_obj=SimpleNamespace(branch_classifier_model="m", branch_classifier_timeout_s=1.0),
        tenant_id="tenant-a",
        bot_listener=object(),
        audio_source=object(),
        tts=object(),
        read_cached_turn_wav_fn=AsyncMock(),
        publish_cached_wav_fn=AsyncMock(),
        timeout=10.0,
        effective_merge_window_s=0.7,
        effective_endpointing_ms=1200,
        classify_branch_fn=object(),
        classifier_client=object(),
        report_turn_fn=report_turn,
        graph_traversal=None,
        now_ms_fn=lambda: 0,
        emit_heartbeat_state_fn=lambda **kwargs: None,
        logger_obj=SimpleNamespace(info=Mock()),
        tts_live_circuit_breaker=None,
        tts_circuit_bridge=None,
    )

    assert play_audio.await_count == 1
