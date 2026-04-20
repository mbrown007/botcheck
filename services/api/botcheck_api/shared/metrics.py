"""Compatibility shim for shared metrics imports."""

from .. import metrics as _metrics


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_metrics, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_metrics)))

