from __future__ import annotations

from .ai_caller_policy import AICallerDecision


async def emit_ai_debug_events(
    *,
    event_emitter,
    bot_transcript: str,
    decision: AICallerDecision,
) -> None:
    if event_emitter is None:
        return
    await event_emitter.emit(
        "harness.classifier_input",
        {
            "transcript": str(bot_transcript or ""),
        },
    )
    await event_emitter.emit(
        "harness.classifier_output",
        {
            "selected_case": decision.action,
            "confidence": decision.confidence,
        },
    )
    await event_emitter.emit(
        "harness.caller_reasoning",
        {
            "summary": decision.reasoning_summary,
        },
    )
