"""Compatibility shim for pack-runs router imports."""

from . import pack_runs as _pack_runs

router = _pack_runs.router

__all__ = ["router"]
