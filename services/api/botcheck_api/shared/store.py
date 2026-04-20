"""Compatibility facade for store access.

This module preserves existing imports while delegating behavior to the
repository/service split introduced for item 33.
"""

from . import store_service as _store_service
from .store_service import *  # noqa: F403
# reconcile_scenario_cache_status is intentionally absent from shared/store_service —
# it performs a write side-effect (not a pure query) and is only needed by the
# legacy store shim.  Do not add it to shared/store_service.__all__.
from ..scenarios.store_service import reconcile_scenario_cache_status

_STORE_ONLY_EXPORTS = [
    "reconcile_scenario_cache_status",
]

# Use dict.fromkeys to deduplicate in case _store_service.__all__ ever gains a
# symbol that is also in _STORE_ONLY_EXPORTS, preserving insertion order.
__all__ = list(dict.fromkeys([*_store_service.__all__, *_STORE_ONLY_EXPORTS]))
