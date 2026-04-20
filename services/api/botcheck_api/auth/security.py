"""Security helpers for login hardening.

In-memory fallback remains available for local development and degraded mode.
When enabled, Redis-backed keys provide multi-instance consistency for
rate-limit windows and TOTP replay protection.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from threading import Lock
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from ..config import settings

_LOCK = Lock()
_RATE_WINDOWS: dict[str, deque[float]] = {}
_TOTP_REPLAY: dict[str, float] = {}
_REDIS_CLIENT: Redis | None = None
_REDIS_FAILURE_UNTIL_S = 0.0

logger = logging.getLogger("botcheck.api.auth_security")


def _cleanup_expired(now: float) -> None:
    stale_replay = [key for key, expires_at in _TOTP_REPLAY.items() if expires_at <= now]
    for key in stale_replay:
        _TOTP_REPLAY.pop(key, None)


def _redis_enabled() -> bool:
    return bool(settings.auth_security_redis_enabled and settings.redis_url.strip())


def _redis_cache_key(kind: str, key: str) -> str:
    return f"{settings.auth_security_redis_prefix}:{kind}:{key}"


def _redis_mark_unavailable(now_s: float, exc: Exception) -> None:
    global _REDIS_CLIENT, _REDIS_FAILURE_UNTIL_S
    _REDIS_CLIENT = None
    _REDIS_FAILURE_UNTIL_S = now_s + settings.auth_security_redis_failure_backoff_s
    logger.warning(
        "Auth security Redis unavailable; falling back to in-memory state: %s",
        exc,
    )


def _redis_client(now_s: float) -> Redis | None:
    global _REDIS_CLIENT
    if not _redis_enabled():
        return None
    if now_s < _REDIS_FAILURE_UNTIL_S:
        return None
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.auth_security_redis_timeout_s,
            socket_timeout=settings.auth_security_redis_timeout_s,
            retry_on_timeout=False,
        )
    return _REDIS_CLIENT


def _check_login_rate_limit_redis(
    *,
    client: Redis,
    key: str,
    max_attempts: int,
    window_s: int,
    now_s: float,
) -> tuple[bool, int]:
    redis_key = _redis_cache_key("rl", key)
    now_ms = int(now_s * 1000)
    window_ms = int(window_s * 1000)
    floor_ms = now_ms - window_ms

    # Trim stale attempts then evaluate current cardinality.
    pipe = client.pipeline(transaction=True)
    pipe.zremrangebyscore(redis_key, 0, floor_ms)
    pipe.zcard(redis_key)
    pipe.zrange(redis_key, 0, 0, withscores=True)
    _, count, oldest = pipe.execute()

    if int(count) >= max_attempts:
        oldest_ms = now_ms
        if oldest:
            oldest_ms = int(float(oldest[0][1]))
        retry_after = max(1, int(((oldest_ms + window_ms) - now_ms + 999) / 1000))
        client.expire(redis_key, window_s + 1)
        return False, retry_after

    member = f"{now_ms}:{uuid4().hex}"
    pipe = client.pipeline(transaction=True)
    pipe.zadd(redis_key, {member: now_ms})
    pipe.expire(redis_key, window_s + 1)
    pipe.execute()
    return True, 0


def _consume_totp_counter_once_redis(
    *,
    client: Redis,
    key: str,
    ttl_s: int,
) -> bool:
    redis_key = _redis_cache_key("totp", key)
    return bool(client.set(redis_key, "1", nx=True, ex=ttl_s))


def check_login_rate_limit(
    *,
    key: str,
    max_attempts: int,
    window_s: int,
    now: float | None = None,
) -> tuple[bool, int]:
    """Record a login attempt and enforce a simple sliding-window limit.

    Returns ``(allowed, retry_after_seconds)``.
    """
    if max_attempts <= 0 or window_s <= 0:
        return True, 0

    ts = float(now if now is not None else time.time())
    client = _redis_client(ts)
    if client is not None:
        try:
            return _check_login_rate_limit_redis(
                client=client,
                key=key,
                max_attempts=max_attempts,
                window_s=window_s,
                now_s=ts,
            )
        except (RedisError, OSError) as exc:
            _redis_mark_unavailable(ts, exc)

    cutoff = ts - float(window_s)
    with _LOCK:
        _cleanup_expired(ts)
        attempts = _RATE_WINDOWS.setdefault(key, deque())
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

        if len(attempts) >= max_attempts:
            oldest = attempts[0]
            retry_after = max(1, int((oldest + float(window_s)) - ts))
            return False, retry_after

        attempts.append(ts)
        return True, 0


def consume_totp_counter_once(
    *,
    key: str,
    ttl_s: int,
    now: float | None = None,
) -> bool:
    """Consume a TOTP counter key once during its replay-protection window."""
    if ttl_s <= 0:
        return True

    ts = float(now if now is not None else time.time())
    client = _redis_client(ts)
    if client is not None:
        try:
            return _consume_totp_counter_once_redis(
                client=client,
                key=key,
                ttl_s=ttl_s,
            )
        except (RedisError, OSError) as exc:
            _redis_mark_unavailable(ts, exc)

    expires_at = ts + float(ttl_s)
    with _LOCK:
        _cleanup_expired(ts)
        existing = _TOTP_REPLAY.get(key)
        if existing is not None and existing > ts:
            return False
        _TOTP_REPLAY[key] = expires_at
        return True


def reset_auth_security_state() -> None:
    """Clear in-memory limiter/replay state (used by tests)."""
    global _REDIS_CLIENT, _REDIS_FAILURE_UNTIL_S
    with _LOCK:
        _RATE_WINDOWS.clear()
        _TOTP_REPLAY.clear()
        if _REDIS_CLIENT is not None:
            try:
                _REDIS_CLIENT.close()
            except Exception:
                pass
        _REDIS_CLIENT = None
        _REDIS_FAILURE_UNTIL_S = 0.0

