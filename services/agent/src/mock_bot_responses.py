"""
Deterministic response selection for the Phase 5 mock bot.

The runtime mock bot uses keyword-based routing so branching scenarios can
exercise multiple paths in CI without depending on an external SIP endpoint.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

logger = logging.getLogger("botcheck.mock_bot.responses")

DEFAULT_RESPONSE_MAP: dict[str, str] = {
    "billing": "You've reached billing support. How can I help?",
    "technical": "You've reached technical support. What issue are you experiencing?",
    "dispute": "I can route this to billing disputes. Please describe the charge.",
}

DEFAULT_RESPONSE = "I'm sorry, I can only answer AcmeCorp support questions."


def _normalize_keyword(value: str) -> str:
    return " ".join(value.lower().split())


def parse_response_map_json(raw_json: str | None) -> dict[str, str]:
    """
    Parse optional JSON override for mock responses.

    Expected shape: {"keyword": "response", ...}
    Invalid entries are ignored; an empty/invalid map returns {}.
    """
    if raw_json is None or not raw_json.strip():
        return {}

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        logger.warning("Invalid MOCK_BOT_RESPONSE_MAP_JSON; falling back to defaults")
        return {}

    if not isinstance(parsed, dict):
        logger.warning(
            "MOCK_BOT_RESPONSE_MAP_JSON must be a JSON object; falling back to defaults"
        )
        return {}

    normalized: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        keyword = _normalize_keyword(key)
        response = value.strip()
        if not keyword or not response:
            continue
        normalized[keyword] = response
    return normalized


def resolve_response_map(raw_json: str | None) -> dict[str, str]:
    """
    Return effective response map.

    Env override is additive over defaults so CI can add branch-specific phrases
    without redefining the baseline routing behavior.
    """
    merged = dict(DEFAULT_RESPONSE_MAP)
    merged.update(parse_response_map_json(raw_json))
    return merged


def mock_response(
    harness_text: str,
    *,
    response_map: Mapping[str, str] | None = None,
    default_response: str = DEFAULT_RESPONSE,
) -> str:
    text = " ".join((harness_text or "").lower().split())
    if not text:
        return default_response

    mapping = response_map or DEFAULT_RESPONSE_MAP
    for keyword, reply in mapping.items():
        normalized_keyword = _normalize_keyword(keyword)
        if normalized_keyword and normalized_keyword in text:
            return reply
    return default_response
