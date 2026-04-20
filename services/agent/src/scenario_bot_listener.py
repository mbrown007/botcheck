from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from botcheck_scenarios import ConversationTurn

from .metrics import PROVIDER_API_CALLS_TOTAL, STT_LISTEN_LATENCY_SECONDS, STT_SECONDS_TOTAL

if TYPE_CHECKING:
    from .audio import PreviewTranscriptCallback

TIMING_SKEW_TOLERANCE_MS = 250


def _provider_label(bot_listener) -> str:
    return str(getattr(bot_listener, "provider_id", "deepgram") or "deepgram").strip().lower() or "deepgram"


def _model_label(bot_listener) -> str:
    return str(getattr(bot_listener, "model_label", "base") or "base").strip() or "base"


async def listen_bot_turn(
    *,
    bot_listener,
    timeout_s: float,
    merge_window_s: float,
    stt_endpointing_ms: int,
    listen_for_s: float | None = None,
    turn_id: str,
    turn_number: int,
    now_ms_fn: Callable[[], int],
    logger_obj,
    scenario_kind: str = "graph",
    # preview_callback is only set for AI voice scenarios; graph-loop callers
    # (scenario_harness_turn, scenario_bot_turn) intentionally omit it.
    preview_callback: "PreviewTranscriptCallback | None" = None,
) -> ConversationTurn:
    window_start_ms = now_ms_fn()
    provider = _provider_label(bot_listener)
    model = _model_label(bot_listener)
    try:
        bot_text = await bot_listener.listen(
            timeout_s=timeout_s,
            merge_window_s=merge_window_s,
            stt_endpointing_ms=stt_endpointing_ms,
            listen_for_s=listen_for_s,
            preview_callback=preview_callback,
        )
    except Exception:
        window_end_ms = now_ms_fn()
        stt_duration_s = (window_end_ms - window_start_ms) / 1000.0
        listen_latency_s = max(0.0, float(window_end_ms - window_start_ms) / 1000.0)
        STT_SECONDS_TOTAL.labels(
            provider=provider,
            model=model,
            scenario_kind=scenario_kind,
        ).inc(stt_duration_s)
        STT_LISTEN_LATENCY_SECONDS.labels(
            provider=provider,
            model=model,
            result="error",
            scenario_kind=scenario_kind,
        ).observe(listen_latency_s)
        PROVIDER_API_CALLS_TOTAL.labels(
            provider=provider,
            service="stt",
            model=model,
            outcome="error",
        ).inc()
        raise
    window_end_ms = now_ms_fn()
    logger_obj.info("Turn %d [bot]: %s", turn_number, bot_text[:80])

    start_ms = window_start_ms
    end_ms = window_end_ms
    timing_getter = getattr(bot_listener, "last_utterance_timing_ms", None)
    if callable(timing_getter):
        timing = timing_getter()
        if timing is not None and bot_text != "(timeout)":
            timing_start_ms = int(timing[0])
            timing_end_ms = int(timing[1])
            if timing_end_ms >= timing_start_ms:
                skew_before_window_ms = window_start_ms - timing_end_ms
                if skew_before_window_ms <= TIMING_SKEW_TOLERANCE_MS:
                    start_ms = max(0, timing_start_ms)
                    end_ms = max(start_ms, timing_end_ms)
                else:
                    start_ms = max(window_start_ms, timing_start_ms)
                    end_ms = max(start_ms, timing_end_ms)

    stt_duration_s = (window_end_ms - window_start_ms) / 1000.0
    listen_latency_s = max(0.0, float(window_end_ms - window_start_ms) / 1000.0)
    listen_result = "timeout" if bot_text == "(timeout)" else "speech"
    STT_SECONDS_TOTAL.labels(
        provider=provider,
        model=model,
        scenario_kind=scenario_kind,
    ).inc(stt_duration_s)
    STT_LISTEN_LATENCY_SECONDS.labels(
        provider=provider,
        model=model,
        result=listen_result,
        scenario_kind=scenario_kind,
    ).observe(listen_latency_s)
    PROVIDER_API_CALLS_TOTAL.labels(
        provider=provider,
        service="stt",
        model=model,
        outcome="success",
    ).inc()

    return ConversationTurn(
        turn_id=turn_id,
        turn_number=turn_number,
        speaker="bot",
        text=bot_text,
        audio_start_ms=start_ms,
        audio_end_ms=end_ms,
    )
