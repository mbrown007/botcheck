from __future__ import annotations

import re

DECISION_DEFAULT_SLOT = "default"
DECISION_PATH_SLOT_PREFIX = "path_"
DECISION_OUTPUT_HANDLE_PREFIX = "decision-output:"

_PATH_SLOT_RE = re.compile(rf"^{re.escape(DECISION_PATH_SLOT_PREFIX)}(\d+)$")


def decision_path_slot(index: int) -> str:
    safe_index = max(1, int(index))
    return f"{DECISION_PATH_SLOT_PREFIX}{safe_index}"


def decision_output_slots(output_count: int) -> list[str]:
    safe_count = max(1, int(output_count))
    slots = [DECISION_DEFAULT_SLOT]
    slots.extend(decision_path_slot(index) for index in range(1, safe_count))
    return slots


def decision_handle_id(slot: str) -> str:
    return f"{DECISION_OUTPUT_HANDLE_PREFIX}{slot}"


def parse_decision_handle_slot(handle_id: str | None) -> str | None:
    if not handle_id or not handle_id.startswith(DECISION_OUTPUT_HANDLE_PREFIX):
        return None
    slot = handle_id[len(DECISION_OUTPUT_HANDLE_PREFIX) :].strip().lower()
    return slot or None


def is_default_decision_slot(slot: str | None) -> bool:
    return (slot or "").strip().lower() == DECISION_DEFAULT_SLOT


def is_path_decision_slot(slot: str | None) -> bool:
    return _PATH_SLOT_RE.match((slot or "").strip().lower()) is not None


def decision_path_slot_index(slot: str | None) -> int | None:
    match = _PATH_SLOT_RE.match((slot or "").strip().lower())
    if not match:
        return None
    try:
        parsed = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
