"""Compatibility shim for shared audit imports."""

from .. import audit as _audit


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_audit, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_audit)))

