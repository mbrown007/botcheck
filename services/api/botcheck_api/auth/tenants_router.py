"""Compatibility shim for tenants router imports."""

from . import tenants as _tenants

router = _tenants.router

__all__ = ["router"]
