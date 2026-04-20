"""Scenarios feature package shims.

Legacy alias packages under ``botcheck_api.routers`` and
``botcheck_api.services`` were retired on 2026-03-06.
"""

from __future__ import annotations

# Only submodules that do NOT import ``botcheck_api.store`` (directly or
# transitively) can be imported eagerly here without triggering a circular-
# import chain.  When this package is first imported during store.py's own
# initialisation, any submodule that reaches ``from .. import store`` at that
# point would capture a stale reference and fail at runtime.
#
# Safe to import eagerly (verified: neither touches ``store`` at import time):
#   service, store_service
#
# NOT safe (both eventually reach ``from .. import store``):
#   router  — re-exports scenarios.router; depends on scenarios at import time
#   scenarios — imports ``from .. import store`` directly
#   Those remain accessible via direct submodule import, e.g.:
#   ``from botcheck_api.scenarios.router import router``
from . import service
from . import store_service

__all__ = [
    "service",
    "store_service",
]
