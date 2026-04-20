"""Packs feature package shims.

Legacy alias packages under ``botcheck_api.routers`` and
``botcheck_api.services`` were retired on 2026-03-06.

Only ``service`` is eagerly imported (cycle-safe); the remaining six
submodules are loaded on demand via ``__getattr__`` to avoid circular
imports through ``botcheck_api.store``.
"""

from __future__ import annotations

from importlib import import_module

from . import service

# These submodules all reach ``botcheck_api.store`` at import time and cannot
# be imported eagerly here without triggering a circular-import chain.
# Note: "packs" refers to the submodule ``botcheck_api.packs.packs``, not the
# package itself — the name collision is intentional (inherited submodule name).
_LAZY_EXPORTS: frozenset[str] = frozenset({
    "router",
    "runs_router",
    "packs",
    "pack_runs",
    "destinations",
    "destinations_router",
})

__all__ = ["service", *sorted(_LAZY_EXPORTS)]


def __getattr__(name: str) -> object:
    if name in _LAZY_EXPORTS:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
