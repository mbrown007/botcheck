"""Compatibility shim for scenarios router imports."""

from . import scenarios as _scenarios

router = _scenarios.router

__all__ = ["router"]
