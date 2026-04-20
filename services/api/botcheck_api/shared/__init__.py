"""Shared kernel package shims.

Slice 1 scaffold: expose a shared-folder import path without moving implementation.

Legacy alias packages under ``botcheck_api.routers`` and
``botcheck_api.services`` were retired on 2026-03-06.
"""

from . import (
    audit,
    audit_router,
    config,
    database,
    exceptions,
    health_router,
    metrics,
    models,
    store,
    store_service,
    telemetry,
)
from .. import text_normalization

__all__ = [
    "audit",
    "audit_router",
    "config",
    "database",
    "exceptions",
    "health_router",
    "metrics",
    "models",
    "store",
    "store_service",
    "telemetry",
    "text_normalization",
]
