"""Transcript redaction helpers for persisted run turns."""

from __future__ import annotations

import re
from typing import Final

# Structured PII-like patterns that are high-confidence for voice transcripts.
_PII_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b4\d{3}(?:[ -]?\d{4}){3}\b"), "[CARD]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
]

_WORD_TO_DIGIT: Final[dict[str, str]] = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_SPOKEN_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:zero|oh|o|one|two|three|four|five|six|seven|eight|nine)"
    r"(?:[\s-]+(?:zero|oh|o|one|two|three|four|five|six|seven|eight|nine)){2,}\b",
    flags=re.IGNORECASE,
)


def normalize_spoken_numbers(text: str) -> str:
    """Convert spoken number runs (\"four one five\") into digit strings."""

    def _replace(match: re.Match[str]) -> str:
        parts = re.split(r"[\s-]+", match.group(0).strip().lower())
        digits = "".join(_WORD_TO_DIGIT.get(part, "") for part in parts)
        return digits if digits else match.group(0)

    return _SPOKEN_NUMBER_RE.sub(_replace, text)


def redact_text_pipeline(text: str) -> str:
    if not text:
        return text
    redacted = normalize_spoken_numbers(text)
    for pattern, replacement in _PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_turn_payload(turn: dict) -> dict:
    """Return a copy of the turn payload with redacted text fields."""
    if not isinstance(turn, dict):
        return turn
    out = dict(turn)
    text = out.get("text")
    if isinstance(text, str):
        out["text"] = redact_text_pipeline(text)
    return out
