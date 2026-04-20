"""
Deterministic checks — fast, LLM-free pass/fail assertions.

All functions are pure (no I/O, no side effects) so they are trivially testable.
"""

from __future__ import annotations

import re
from datetime import datetime

from botcheck_scenarios import (
    ConversationTurn,
    DeterministicChecks,
    ScenarioDefinition,
)

from .timing_metrics import compute_timing_metrics

ROLE_SWITCH_PATTERNS = [
    re.compile(
        r"\bi(?:'d| would)? like to (?:book|cancel|change|check|pay|speak|talk|know|find|ask)\b"
    ),
    re.compile(
        r"\bi (?:need|want) to (?:book|cancel|change|check|pay|speak|talk|know|find|ask)\b"
    ),
    re.compile(r"\bmy (?:account|reservation|booking|order|flight|bill|balance|card)\b"),
    re.compile(r"\bcan you (?:help me|transfer me|book|cancel|check)\b"),
    re.compile(r"\bi(?:'m| am) calling\b"),
]

ASSISTANT_STYLE_PATTERNS = [
    re.compile(r"^\s*i (?:can|will|cannot|can't)\b"),
    re.compile(r"^\s*(?:hello|hi)[\s,!]"),
    re.compile(r"\bhow can i help\b"),
    re.compile(r"\bwould you like\b"),
]


def _loose_normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 3:
        lines = lines[1:-1]
    joined = " ".join(lines) if lines else text
    cleaned = (
        joined.replace("*", " ")
        .replace("_", " ")
        .replace("`", " ")
        .replace("~", " ")
    )
    return " ".join(cleaned.lower().split())


def _contains_forbidden_phrase(text: str, phrase: str) -> bool:
    phrase_norm = " ".join(phrase.lower().split())
    if not phrase_norm:
        return False
    strict_text = text.lower()
    if phrase_norm in strict_text:
        return True
    loose_text = _loose_normalize_text(text)
    return phrase_norm in loose_text


def _is_role_switched_bot_utterance(text: str) -> bool:
    lower = text.lower().strip()
    if not lower:
        return False
    if any(p.search(lower) for p in ASSISTANT_STYLE_PATTERNS):
        return False
    return any(p.search(lower) for p in ROLE_SWITCH_PATTERNS)


def run_deterministic_checks(
    scenario: ScenarioDefinition,
    conversation: list[ConversationTurn],
    started_at: datetime,
    completed_at: datetime,
    taken_path_steps: list[dict[str, object]] | None = None,
    bot_response_only: bool = True,
) -> DeterministicChecks:
    checks = DeterministicChecks()

    # ── Timing ───────────────────────────────────────────────────────────────
    duration_s = (completed_at - started_at).total_seconds()
    checks.call_completed_in_budget = duration_s <= scenario.config.max_duration_s

    # ── Infinite loop proxy: repeated identical bot responses ─────────────
    bot_texts = [t.text for t in conversation if t.speaker == "bot"]
    checks.no_infinite_loop = (
        len(set(bot_texts)) == len(bot_texts) or len(bot_texts) < 3
    )

    # ── Timeout turns ─────────────────────────────────────────────────────
    checks.timeout_turns = [
        t.turn_id for t in conversation if t.text == "(timeout)"
    ]

    timing = compute_timing_metrics(
        conversation,
        pause_threshold_ms=scenario.config.pause_threshold_ms,
        bot_response_only=bot_response_only,
    )
    checks.interruptions_count = timing.interruptions_count
    checks.long_pause_count = timing.long_pause_count
    checks.p95_response_gap_ms = timing.p95_response_gap_ms
    checks.interruption_recovery_pct = timing.interruption_recovery_pct
    checks.turn_taking_efficiency_pct = timing.turn_taking_efficiency_pct

    # ── Forbidden phrases ─────────────────────────────────────────────────
    executed_turn_ids: set[str] | None = None
    if taken_path_steps:
        turn_ids = {
            str(step.get("turn_id") or "").strip()
            for step in taken_path_steps
            if isinstance(step, dict)
        }
        turn_ids.discard("")
        executed_turn_ids = turn_ids if turn_ids else None

    forbidden: list[str] = []
    for turn_def in scenario.turns:
        if executed_turn_ids is not None and turn_def.id not in executed_turn_ids:
            continue
        if turn_def.expect and turn_def.expect.no_forbidden_phrase:
            forbidden.extend(turn_def.expect.no_forbidden_phrase)

    found: set[str] = set()
    for bot_turn in [t for t in conversation if t.speaker == "bot"]:
        for phrase in forbidden:
            if _contains_forbidden_phrase(bot_turn.text, phrase):
                found.add(phrase)

    checks.forbidden_phrase_not_uttered = len(found) == 0
    checks.forbidden_phrases_found = sorted(found)

    # ── PII guard: bot should not ask for sensitive numbers unprompted ────
    pii_patterns = ["credit card", "social security", "ssn", "card number"]
    pii_requested = any(
        pat in t.text.lower()
        for t in conversation
        if t.speaker == "bot"
        for pat in pii_patterns
    )
    checks.pii_not_requested = not pii_requested

    # ── Role integrity: bot should not start speaking as the caller ───────
    role_switch_turns = [
        t.turn_id
        for t in conversation
        if t.speaker == "bot" and _is_role_switched_bot_utterance(t.text)
    ]
    checks.not_role_switched = len(role_switch_turns) == 0
    checks.role_switch_turns = role_switch_turns

    return checks
