"""Compatibility shim for schedules router imports."""

from . import schedules as _schedules

router = _schedules.router

__all__ = ["router"]
