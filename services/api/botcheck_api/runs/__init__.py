"""Runs feature package shims.

Legacy alias packages under ``botcheck_api.routers`` and
``botcheck_api.services`` were retired on 2026-03-06.
"""

from __future__ import annotations

# Only submodules that do NOT import ``botcheck_api.store`` (directly or
# transitively) can be imported eagerly here without triggering a circular-
# import chain.  When this package is first imported inside shared/store.py's
# initialisation (via ``from ..runs.store_service import …``), the
# ``botcheck_api.store`` module object is still the empty placeholder.
# Any submodule that reaches ``from .. import store`` at that point would
# capture a stale reference and fail at runtime.
#
# Safe to import eagerly (verified: none of these touch ``store`` at import time):
#   provider_state, service_telephony, store_service
#
# NOT safe (all eventually reach ``from .. import store``):
#   router, router_*, runs, runs_*, schedules, schedules_router, service
#   Those remain accessible via direct submodule import, e.g.:
#   ``from botcheck_api.runs.router import router``
from . import provider_state
from . import service_telephony
from . import store_service

__all__ = [
    "provider_state",
    "service_telephony",
    "store_service",
]
