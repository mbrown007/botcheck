"""Unit tests for auth security Redis-backed primitives."""

from __future__ import annotations

from botcheck_api.auth import security as auth_security


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple, dict]] = []

    def zremrangebyscore(self, *args, **kwargs):
        self._ops.append(("zremrangebyscore", args, kwargs))
        return self

    def zcard(self, *args, **kwargs):
        self._ops.append(("zcard", args, kwargs))
        return self

    def zrange(self, *args, **kwargs):
        self._ops.append(("zrange", args, kwargs))
        return self

    def zadd(self, *args, **kwargs):
        self._ops.append(("zadd", args, kwargs))
        return self

    def expire(self, *args, **kwargs):
        self._ops.append(("expire", args, kwargs))
        return self

    def execute(self):
        out = []
        for method, args, kwargs in self._ops:
            out.append(getattr(self._redis, method)(*args, **kwargs))
        self._ops.clear()
        return out


class _FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        assert transaction is True
        return _FakePipeline(self)

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        zset = self._zsets.setdefault(key, {})
        to_delete = [member for member, score in zset.items() if min_score <= score <= max_score]
        for member in to_delete:
            zset.pop(member, None)
        return len(to_delete)

    def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    def zrange(self, key: str, start: int, stop: int, *, withscores: bool = False):
        pairs = sorted(self._zsets.get(key, {}).items(), key=lambda item: item[1])
        if stop >= 0:
            pairs = pairs[start : stop + 1]
        else:
            pairs = pairs[start:]
        if withscores:
            return [(member, float(score)) for member, score in pairs]
        return [member for member, _score in pairs]

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        zset = self._zsets.setdefault(key, {})
        for member, score in mapping.items():
            zset[member] = float(score)
        return len(mapping)

    def expire(self, key: str, seconds: int) -> bool:
        del seconds
        return key in self._zsets or key in self._kv

    def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None):
        del ex
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def close(self) -> None:
        return None


class _BrokenRedis:
    def set(self, *args, **kwargs):
        raise OSError("redis unavailable")

    def pipeline(self, *args, **kwargs):
        raise OSError("redis unavailable")

    def close(self) -> None:
        return None


def test_check_login_rate_limit_uses_redis_when_enabled(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(auth_security.settings, "auth_security_redis_enabled", True)
    monkeypatch.setattr(auth_security, "_redis_client", lambda _now: fake)
    auth_security.reset_auth_security_state()

    assert auth_security.check_login_rate_limit(
        key="tenant:user:ip",
        max_attempts=2,
        window_s=60,
        now=1.0,
    ) == (True, 0)
    assert auth_security.check_login_rate_limit(
        key="tenant:user:ip",
        max_attempts=2,
        window_s=60,
        now=2.0,
    ) == (True, 0)
    allowed, retry_after = auth_security.check_login_rate_limit(
        key="tenant:user:ip",
        max_attempts=2,
        window_s=60,
        now=3.0,
    )
    assert allowed is False
    assert retry_after > 0


def test_consume_totp_counter_once_uses_redis_when_enabled(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(auth_security.settings, "auth_security_redis_enabled", True)
    monkeypatch.setattr(auth_security, "_redis_client", lambda _now: fake)
    auth_security.reset_auth_security_state()

    assert auth_security.consume_totp_counter_once(
        key="tenant:user:counter",
        ttl_s=120,
        now=1.0,
    )
    assert not auth_security.consume_totp_counter_once(
        key="tenant:user:counter",
        ttl_s=120,
        now=2.0,
    )


def test_redis_error_falls_back_to_in_memory(monkeypatch):
    monkeypatch.setattr(auth_security.settings, "auth_security_redis_enabled", True)
    monkeypatch.setattr(auth_security, "_redis_client", lambda _now: _BrokenRedis())
    auth_security.reset_auth_security_state()

    # Falls back to process-local window tracking when Redis is unavailable.
    assert auth_security.check_login_rate_limit(
        key="tenant:user:ip",
        max_attempts=1,
        window_s=60,
        now=1.0,
    ) == (True, 0)
    allowed, retry_after = auth_security.check_login_rate_limit(
        key="tenant:user:ip",
        max_attempts=1,
        window_s=60,
        now=2.0,
    )
    assert allowed is False
    assert retry_after > 0

    assert auth_security.consume_totp_counter_once(
        key="tenant:user:counter",
        ttl_s=120,
        now=3.0,
    )
    assert not auth_security.consume_totp_counter_once(
        key="tenant:user:counter",
        ttl_s=120,
        now=4.0,
    )
