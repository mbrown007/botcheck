"""Auth feature package.

Preserves existing import semantics via ``from .core import *`` while lazily
exposing auth submodules used by compatibility shims.

Legacy alias packages under ``botcheck_api.routers`` and
``botcheck_api.services`` were retired on 2026-03-06.
"""

from importlib import import_module

from . import core
from .core import *  # noqa: F401,F403

_CORE_PUBLIC = [name for name in dir(core) if not name.startswith("_")]
_MODULE_EXPORTS = (
    "core",
    "security",
    "totp",
    "router_login",
    "router_sessions",
    "router_totp",
    "tenants",
    "tenants_router",
)

__all__ = [*_CORE_PUBLIC, *_MODULE_EXPORTS]


def __getattr__(name: str):  # pragma: no cover - trivial module proxy
    if name in _MODULE_EXPORTS:
        return import_module(f"{__name__}.{name}")
    return getattr(core, name)


def __dir__() -> list[str]:  # pragma: no cover - trivial module proxy
    return sorted(set(globals()) | set(dir(core)) | set(_MODULE_EXPORTS))
