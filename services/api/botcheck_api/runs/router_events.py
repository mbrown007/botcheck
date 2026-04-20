"""Compatibility shim for runs events router imports."""

from . import runs_events as _runs_events

router = _runs_events.router

__all__ = ["router"]
