"""Compatibility shim for runs router imports."""

from . import runs as _runs

router = _runs.router

__all__ = ["router"]
