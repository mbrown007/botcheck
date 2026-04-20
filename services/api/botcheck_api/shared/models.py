"""Compatibility shim for shared models imports."""

from .. import models as _models


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_models, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_models)))

