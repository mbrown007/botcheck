from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from botcheck_scenarios import BranchMode, ConversationTurn, HarnessPromptBlock, PromptContent


def scenario_prompt_text(turn_def) -> str:
    """Return the prompt text for a harness_prompt block; empty string for all other kinds."""
    if turn_def.kind != "harness_prompt":
        return ""
    return turn_def.content.text or ""


def ai_prompt_block(*, turn_id: str, prompt_text: str) -> HarnessPromptBlock:
    """Build a minimal HarnessPromptBlock for AI-generated prompt turns."""
    return HarnessPromptBlock(
        id=turn_id,
        content=PromptContent(text=prompt_text),
        listen=True,
    )


def classifier_history(
    conversation: list[ConversationTurn],
    *,
    limit: int = 6,
) -> list[dict]:
    # Keep classifier context bounded for predictable latency.
    return [turn.model_dump(mode="json") for turn in conversation[-limit:]]


def effective_turn_timeout(turn_def, scenario) -> float:
    # Explicit per-turn timeout takes precedence.
    if turn_def.config.timeout_s is not None:
        return float(turn_def.config.timeout_s)
    if turn_def.expect and turn_def.expect.transferred_to:
        return float(scenario.config.transfer_timeout_s)
    return float(scenario.config.turn_timeout_s)


def effective_stt_settings(turn_def, scenario) -> tuple[int, float]:
    endpointing_ms = (
        turn_def.config.stt_endpointing_ms
        if turn_def.config.stt_endpointing_ms is not None
        else scenario.config.stt_endpointing_ms
    )
    merge_window_s = (
        turn_def.config.transcript_merge_window_s
        if turn_def.config.transcript_merge_window_s is not None
        else scenario.config.transcript_merge_window_s
    )
    return int(endpointing_ms), float(merge_window_s)


async def classify_branch_condition(
    *,
    turn_def,
    bot_text: str,
    conversation: list[ConversationTurn],
    scenario,
    classify_branch_fn: Callable[..., Awaitable[str]],
    classifier_client: Any,
    classifier_model: str,
    classifier_timeout_s: float,
) -> tuple[str, str | None]:
    if turn_def.branching is None:
        return "default", None
    if turn_def.branching.mode == BranchMode.KEYWORD:
        lowered = str(bot_text or "").lower()
        for case in turn_def.branching.cases:
            if str(case.match or "").lower() in lowered:
                return case.condition, bot_text
        return "default", bot_text
    if turn_def.branching.mode == BranchMode.REGEX:
        safe_text = str(bot_text or "")
        for case in turn_def.branching.cases:
            pattern = str(case.regex or "").strip()
            if not pattern:
                continue
            if re.search(pattern, safe_text, flags=re.IGNORECASE):
                return case.condition, bot_text
        return "default", bot_text
    condition = await classify_branch_fn(
        bot_response=bot_text,
        conditions=[case.condition for case in turn_def.branching.cases],
        conversation_history=classifier_history(conversation),
        scenario_intent=scenario.description or scenario.name,
        client=classifier_client,
        model=classifier_model,
        timeout_s=classifier_timeout_s,
    )
    return condition, bot_text
