from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from src import scenario_bot_listener


class _FakeMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float | None]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def inc(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))

    def observe(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))


@pytest.mark.asyncio
async def test_listen_bot_turn_builds_turn_and_records_stt_metrics(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "Billing support here"
    bot_listener.last_utterance_timing_ms = Mock(return_value=(1325, 1710))
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-phonecall"
    logger = Mock()
    now_values = iter((1000, 1750))

    turn = await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=1200,
        turn_id="t_bot",
        turn_number=3,
        now_ms_fn=lambda: next(now_values),
        logger_obj=logger,
    )

    assert turn.turn_id == "t_bot"
    assert turn.turn_number == 3
    assert turn.speaker == "bot"
    assert turn.text == "Billing support here"
    assert turn.audio_start_ms == 1325
    assert turn.audio_end_ms == 1710
    assert stt_metric.calls[0][1] == 0.75
    assert stt_metric.calls[0][0]["provider"] == "deepgram"
    assert stt_metric.calls[0][0]["model"] == "nova-2-phonecall"
    assert stt_metric.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][0]["result"] == "speech"
    assert stt_latency.calls[0][0]["model"] == "nova-2-phonecall"
    assert stt_latency.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][1] == 0.75
    assert provider_calls.calls[0][0]["provider"] == "deepgram"
    assert provider_calls.calls[0][0]["model"] == "nova-2-phonecall"
    assert provider_calls.calls[0][0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_listen_bot_turn_records_timeout_latency_result(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "(timeout)"
    bot_listener.last_utterance_timing_ms = Mock(return_value=None)
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-general"
    logger = Mock()
    now_values = iter((4000, 6250))

    turn = await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=1200,
        turn_id="t_bot_timeout",
        turn_number=4,
        now_ms_fn=lambda: next(now_values),
        logger_obj=logger,
    )

    assert turn.text == "(timeout)"
    assert turn.audio_start_ms == 4000
    assert turn.audio_end_ms == 6250
    assert stt_metric.calls[0][1] == 2.25
    assert stt_metric.calls[0][0]["model"] == "nova-2-general"
    assert stt_metric.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][0]["result"] == "timeout"
    assert stt_latency.calls[0][0]["model"] == "nova-2-general"
    assert stt_latency.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][1] == 2.25
    assert provider_calls.calls[0][0]["model"] == "nova-2-general"
    assert provider_calls.calls[0][0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_listen_bot_turn_forwards_listen_for_s_to_listener(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "(timeout)"
    bot_listener.last_utterance_timing_ms = Mock(return_value=None)
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-general"

    await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=1200,
        listen_for_s=4.25,
        turn_id="t_bot_timeout",
        turn_number=4,
        now_ms_fn=lambda: 0,
        logger_obj=Mock(),
    )

    assert bot_listener.listen.await_args.kwargs["listen_for_s"] == 4.25


@pytest.mark.asyncio
async def test_listen_bot_turn_clamps_timing_before_window_start(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "Hello there"
    bot_listener.last_utterance_timing_ms = Mock(return_value=(250, 700))
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-general"
    logger = Mock()
    now_values = iter((1000, 2000))

    turn = await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=1200,
        turn_id="t_bot_clamp",
        turn_number=5,
        now_ms_fn=lambda: next(now_values),
        logger_obj=logger,
    )

    assert turn.audio_start_ms == 1000
    assert turn.audio_end_ms == 1000
    assert stt_metric.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][0]["scenario_kind"] == "graph"


@pytest.mark.asyncio
async def test_listen_bot_turn_preserves_small_pre_window_skew(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "I can hear you clearly."
    bot_listener.last_utterance_timing_ms = Mock(return_value=(13412, 13460))
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-phonecall"
    logger = Mock()
    now_values = iter((13467, 14500))

    turn = await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=1200,
        turn_id="t_bot_skew",
        turn_number=6,
        now_ms_fn=lambda: next(now_values),
        logger_obj=logger,
    )

    assert turn.audio_start_ms == 13412
    assert turn.audio_end_ms == 13460
    assert stt_metric.calls[0][0]["scenario_kind"] == "graph"
    assert stt_latency.calls[0][0]["scenario_kind"] == "graph"


@pytest.mark.asyncio
async def test_listen_bot_turn_records_error_outcome_when_listener_raises(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.side_effect = RuntimeError("deepgram down")
    bot_listener.provider_id = "deepgram"
    bot_listener.model_label = "nova-2-phonecall"
    logger = Mock()
    now_values = iter((500, 950))

    with pytest.raises(RuntimeError, match="deepgram down"):
        await scenario_bot_listener.listen_bot_turn(
            bot_listener=bot_listener,
            timeout_s=12.0,
            merge_window_s=0.6,
            stt_endpointing_ms=1200,
            turn_id="t_bot_error",
            turn_number=6,
            now_ms_fn=lambda: next(now_values),
            logger_obj=logger,
        )

    assert stt_metric.calls[0][0]["provider"] == "deepgram"
    assert stt_metric.calls[0][0]["model"] == "nova-2-phonecall"
    assert stt_latency.calls[0][0]["provider"] == "deepgram"
    assert stt_latency.calls[0][0]["model"] == "nova-2-phonecall"
    assert stt_latency.calls[0][0]["result"] == "error"
    assert provider_calls.calls[0][0]["outcome"] == "error"


@pytest.mark.asyncio
async def test_listen_bot_turn_records_azure_labels_for_ai_scenarios(monkeypatch) -> None:
    stt_metric = _FakeMetric()
    stt_latency = _FakeMetric()
    provider_calls = _FakeMetric()
    monkeypatch.setattr(scenario_bot_listener, "STT_SECONDS_TOTAL", stt_metric)
    monkeypatch.setattr(scenario_bot_listener, "STT_LISTEN_LATENCY_SECONDS", stt_latency)
    monkeypatch.setattr(scenario_bot_listener, "PROVIDER_API_CALLS_TOTAL", provider_calls)

    bot_listener = AsyncMock()
    bot_listener.listen.return_value = "I'll connect you to an agent now."
    bot_listener.last_utterance_timing_ms = Mock(return_value=(2400, 2950))
    bot_listener.provider_id = "azure"
    bot_listener.model_label = "azure-default"
    logger = Mock()
    now_values = iter((2000, 3100))

    turn = await scenario_bot_listener.listen_bot_turn(
        bot_listener=bot_listener,
        timeout_s=12.0,
        merge_window_s=0.6,
        stt_endpointing_ms=700,
        turn_id="t_bot_azure",
        turn_number=7,
        now_ms_fn=lambda: next(now_values),
        logger_obj=logger,
        scenario_kind="ai",
    )

    assert turn.text == "I'll connect you to an agent now."
    assert stt_metric.calls[0][0]["provider"] == "azure"
    assert stt_metric.calls[0][0]["model"] == "azure-default"
    assert stt_metric.calls[0][0]["scenario_kind"] == "ai"
    assert stt_latency.calls[0][0]["provider"] == "azure"
    assert stt_latency.calls[0][0]["model"] == "azure-default"
    assert stt_latency.calls[0][0]["result"] == "speech"
    assert stt_latency.calls[0][0]["scenario_kind"] == "ai"
    assert provider_calls.calls[0][0]["provider"] == "azure"
    assert provider_calls.calls[0][0]["model"] == "azure-default"
    assert provider_calls.calls[0][0]["outcome"] == "success"
