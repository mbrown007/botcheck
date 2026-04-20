"""Compatibility shim for shared config imports."""

from .. import config as _config


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_config, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_config)))

