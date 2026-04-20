"""Compatibility shim for packs router imports."""

from . import packs as _packs

router = _packs.router

__all__ = ["router"]
