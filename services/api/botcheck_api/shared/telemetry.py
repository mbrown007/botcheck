"""Compatibility shim for shared telemetry imports."""

from .. import telemetry as _telemetry


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    return getattr(_telemetry, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(_telemetry)))

