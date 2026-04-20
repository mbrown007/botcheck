from __future__ import annotations

import math
from dataclasses import dataclass

from botcheck_scenarios import ConversationTurn


@dataclass(frozen=True)
class TimingMetrics:
    interruptions_count: int
    long_pause_count: int
    p95_response_gap_ms: int
    interruption_recovery_pct: float
    turn_taking_efficiency_pct: float


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = max(0, math.ceil(len(sorted_vals) * 0.95) - 1)
    return sorted_vals[idx]


def compute_timing_metrics(
    conversation: list[ConversationTurn],
    *,
    pause_threshold_ms: int = 2000,
    bot_response_only: bool = False,
) -> TimingMetrics:
    """Compute timing metrics for a conversation.

    The primary voice-AI reliability metric is **Time to First Word (TTFW)**:
    the gap from when the harness (caller) stops speaking to when the bot
    starts its response (harness→bot transition).

    When ``bot_response_only`` is True (the default), only TTFW transitions
    (harness→bot) are counted for p95, efficiency, pause, and interruption
    metrics.  bot→harness gaps — which include STT endpointing wait time,
    TTS synthesis, inter-turn pauses, and (for AI scenarios) LLM generation
    — are harness processing overhead and carry no signal about bot reliability.
    """
    interruptions = 0
    long_pauses = 0
    ttfw_gaps: list[int] = []  # harness→bot gaps (Time to First Word)
    transition_count = 0
    successful_transitions = 0
    efficient_transitions = 0

    prev: ConversationTurn | None = None
    for turn in conversation:
        if prev is None:
            prev = turn
            continue
        if turn.speaker != prev.speaker:
            gap_ms = int(turn.audio_start_ms) - int(prev.audio_end_ms)
            is_ttfw = prev.speaker == "harness" and turn.speaker == "bot"
            # In bot_response_only mode only TTFW (harness→bot) transitions are
            # measured — harness processing time is not a bot reliability signal.
            count_this = not bot_response_only or is_ttfw
            if count_this:
                ttfw_gaps.append(gap_ms)
                transition_count += 1
                # Exact turn-boundary handoffs (gap == 0) are not interruptions.
                # Only true overlap (negative gap) should count as barge-in.
                if gap_ms < 0:
                    interruptions += 1
                else:
                    successful_transitions += 1
                if 0 <= gap_ms <= pause_threshold_ms:
                    efficient_transitions += 1
                if gap_ms > pause_threshold_ms:
                    long_pauses += 1
        prev = turn

    if transition_count == 0:
        interruption_recovery_pct = 100.0
        turn_taking_efficiency_pct = 100.0
    else:
        interruption_recovery_pct = (successful_transitions / transition_count) * 100.0
        turn_taking_efficiency_pct = (efficient_transitions / transition_count) * 100.0

    return TimingMetrics(
        interruptions_count=interruptions,
        long_pause_count=long_pauses,
        p95_response_gap_ms=_p95(ttfw_gaps),  # p95 TTFW (Time to First Word)
        interruption_recovery_pct=round(interruption_recovery_pct, 2),
        turn_taking_efficiency_pct=round(turn_taking_efficiency_pct, 2),
    )
