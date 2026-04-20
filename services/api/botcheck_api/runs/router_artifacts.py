"""Compatibility shim for runs artifacts router imports."""

from . import runs_artifacts as _runs_artifacts

router = _runs_artifacts.router

__all__ = ["router"]
