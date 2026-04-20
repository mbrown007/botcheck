"""Compatibility shim for shared exceptions imports."""

from .. import exceptions as _exceptions


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_exceptions, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_exceptions)))

