"""Compatibility shim for grai router imports."""

from . import grai as _grai

router = _grai.router

__all__ = ["router"]
