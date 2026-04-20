"""Compatibility facade for TOTP helpers.

Canonical implementations live in ``botcheck_api.auth.totp``.
Do not monkeypatch private globals through this module; patch
``botcheck_api.auth.totp`` directly.
"""

from __future__ import annotations

from .auth.totp import (
    generate_totp_code,
    generate_totp_secret,
    resolve_totp_counter,
    verify_totp_code,
)

__all__ = [
    "generate_totp_code",
    "generate_totp_secret",
    "resolve_totp_counter",
    "verify_totp_code",
]
