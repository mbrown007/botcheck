"""Compatibility shim for runs lifecycle router imports."""

from . import runs_lifecycle as _runs_lifecycle

router = _runs_lifecycle.router

__all__ = ["router"]
