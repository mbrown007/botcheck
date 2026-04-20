from __future__ import annotations


def strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def strip_lower_or_none(value: str | None) -> str | None:
    candidate = strip_or_none(value)
    if candidate is None:
        return None
    return candidate.lower()


def strip_nonempty(value: str, *, error_message: str = "value must not be blank") -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError(error_message)
    return candidate
