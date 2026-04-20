"""Compatibility facade for auth security helpers.

Canonical implementations live in ``botcheck_api.auth.security``.
Do not monkeypatch private globals through this module; patch
``botcheck_api.auth.security`` directly.
"""

from __future__ import annotations

from .auth.security import (
    check_login_rate_limit,
    consume_totp_counter_once,
    reset_auth_security_state,
)

__all__ = [
    "check_login_rate_limit",
    "consume_totp_counter_once",
    "reset_auth_security_state",
]
