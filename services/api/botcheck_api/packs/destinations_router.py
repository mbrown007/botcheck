"""Compatibility shim for destinations router imports."""

from . import destinations as _destinations

router = _destinations.router

__all__ = ["router"]
