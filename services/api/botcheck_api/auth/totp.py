"""Minimal RFC 6238-compatible TOTP helper functions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from secrets import token_bytes


def generate_totp_secret(bytes_len: int = 20) -> str:
    """Generate a Base32 TOTP secret.

    20 random bytes = 160 bits entropy.
    """
    raw = token_bytes(bytes_len)
    return base64.b32encode(raw).decode().rstrip("=")


def _normalise_secret(secret: str) -> bytes:
    cleaned = secret.strip().replace(" ", "").upper()
    padded = cleaned + "=" * ((8 - (len(cleaned) % 8)) % 8)
    return base64.b32decode(padded, casefold=True)


def _totp_at(secret: str, counter: int, digits: int = 6) -> str:
    key = _normalise_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = code_int % (10**digits)
    return f"{code:0{digits}d}"


def verify_totp_code(
    secret: str,
    code: str,
    *,
    step_s: int = 30,
    window: int = 1,
    at_time: int | None = None,
) -> bool:
    return (
        resolve_totp_counter(
            secret,
            code,
            step_s=step_s,
            window=window,
            at_time=at_time,
        )
        is not None
    )


def resolve_totp_counter(
    secret: str,
    code: str,
    *,
    step_s: int = 30,
    window: int = 1,
    at_time: int | None = None,
) -> int | None:
    normalised = "".join(ch for ch in code if ch.isdigit())
    if len(normalised) != 6:
        return None

    now = int(at_time if at_time is not None else time.time())
    counter = now // step_s
    for offset in range(-window, window + 1):
        candidate_counter = counter + offset
        candidate = _totp_at(secret, candidate_counter)
        if hmac.compare_digest(candidate, normalised):
            return candidate_counter
    return None


def generate_totp_code(
    secret: str,
    *,
    step_s: int = 30,
    at_time: int | None = None,
) -> str:
    now = int(at_time if at_time is not None else time.time())
    counter = now // step_s
    return _totp_at(secret, counter)

