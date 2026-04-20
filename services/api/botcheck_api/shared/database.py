"""Compatibility shim for shared database imports."""

from .. import database as _database


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_database, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_database)))

