from __future__ import annotations

import asyncio
import inspect
import logging
import random

logger = logging.getLogger("botcheck.api.capacity")

_SIP_SLOT_KEY = "botcheck:sip:dispatch_slots"
_SIP_SLOT_KEY_PATTERN = "sip_slots:*"
DEFAULT_SIP_CAPACITY_SCOPE = "tenant-default"

_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local max_slots = tonumber(ARGV[1])
local ttl_ms = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', key) or '0')
if current >= max_slots then
  return 0
end
current = redis.call('INCR', key)
redis.call('PEXPIRE', key, ttl_ms)
return current
"""

_RELEASE_SCRIPT = """
local key = KEYS[1]
local ttl_ms = tonumber(ARGV[1])
local current = tonumber(redis.call('GET', key) or '0')
if current <= 0 then
  redis.call('DEL', key)
  return 0
end
current = redis.call('DECR', key)
if current <= 0 then
  redis.call('DEL', key)
  return 0
end
redis.call('PEXPIRE', key, ttl_ms)
return current
"""

_local_slots_by_key: dict[str, int] = {}
_local_lock: asyncio.Lock | None = None


def _get_local_lock() -> asyncio.Lock:
    global _local_lock
    if _local_lock is None:
        _local_lock = asyncio.Lock()
    return _local_lock


def _coerce_int(value: object) -> int:
    if isinstance(value, bytes):
        return int(value.decode())
    return int(value)


def build_sip_slot_key(*, tenant_id: str, capacity_scope: str | None) -> str:
    tenant = str(tenant_id).strip() or "default"
    scope = str(capacity_scope or "").strip() or DEFAULT_SIP_CAPACITY_SCOPE
    return f"sip_slots:{tenant}:{scope}"


def _resolve_slot_key(*, slot_key: str | None) -> str:
    candidate = str(slot_key or "").strip()
    if candidate:
        return candidate
    return _SIP_SLOT_KEY


async def _redis_eval_int(
    redis_pool: object,
    script: str,
    key: str,
    *args: object,
) -> int:
    eval_fn = getattr(redis_pool, "eval", None)
    if eval_fn is None or not callable(eval_fn):
        raise RuntimeError("Redis pool does not expose eval()")

    result = eval_fn(script, 1, key, *args)
    if inspect.isawaitable(result):
        result = await result
    elif not isinstance(result, (int, float, str, bytes)):
        raise RuntimeError("Redis eval returned unsupported result type")
    return _coerce_int(result)


async def _sum_slot_values(redis_pool: object, keys: list) -> int:
    """Return the sum of integer slot counts stored at each key."""
    if not keys:
        return 0
    mget_fn = getattr(redis_pool, "mget", None)
    if mget_fn is not None and callable(mget_fn):
        result = mget_fn(*keys)
        if inspect.isawaitable(result):
            result = await result
        return sum(_coerce_int(v) for v in result if v is not None)
    get_fn = getattr(redis_pool, "get", None)
    if get_fn is None or not callable(get_fn):
        raise RuntimeError("Redis pool does not expose mget() or get()")
    total = 0
    for key in keys:
        val = get_fn(key)
        if inspect.isawaitable(val):
            val = await val
        if val is not None:
            total += _coerce_int(val)
    return total


async def count_active_sip_slots(*, redis_pool: object) -> int:
    scan_fn = getattr(redis_pool, "scan", None)
    if scan_fn is not None and callable(scan_fn):
        cursor = 0
        total = 0
        while True:
            result = scan_fn(cursor=cursor, match=_SIP_SLOT_KEY_PATTERN)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, tuple) or len(result) != 2:
                raise RuntimeError("Redis scan() returned unsupported result type")
            cursor, keys = result
            if not isinstance(keys, (list, tuple, set)):
                raise RuntimeError("Redis scan() returned unsupported keys result")
            total += await _sum_slot_values(redis_pool, list(keys))
            if _coerce_int(cursor) == 0:
                return total

    keys_fn = getattr(redis_pool, "keys", None)
    if keys_fn is None or not callable(keys_fn):
        raise RuntimeError("Redis pool does not expose scan() or keys()")

    result = keys_fn(_SIP_SLOT_KEY_PATTERN)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, (list, tuple, set)):
        raise RuntimeError("Redis keys() returned unsupported result type")
    return await _sum_slot_values(redis_pool, list(result))


async def try_acquire_sip_slot(
    *,
    redis_pool: object | None,
    max_slots: int,
    slot_ttl_s: int,
    slot_key: str | None = None,
) -> bool:
    if max_slots <= 0:
        return False

    key = _resolve_slot_key(slot_key=slot_key)
    ttl_ms = max(5, slot_ttl_s) * 1000
    if redis_pool is not None:
        try:
            current = await _redis_eval_int(
                redis_pool,
                _ACQUIRE_SCRIPT,
                key,
                int(max_slots),
                int(ttl_ms),
            )
            return current > 0
        except Exception:
            logger.warning("Redis SIP slot acquire failed; using local fallback", exc_info=True)

    async with _get_local_lock():
        current = int(_local_slots_by_key.get(key, 0))
        if current >= max_slots:
            return False
        _local_slots_by_key[key] = current + 1
        return True


async def release_sip_slot(
    *,
    redis_pool: object | None,
    slot_ttl_s: int,
    slot_key: str | None = None,
) -> None:
    key = _resolve_slot_key(slot_key=slot_key)
    ttl_ms = max(5, slot_ttl_s) * 1000
    if redis_pool is not None:
        try:
            await _redis_eval_int(
                redis_pool,
                _RELEASE_SCRIPT,
                key,
                int(ttl_ms),
            )
            return
        except Exception:
            logger.warning("Redis SIP slot release failed; using local fallback", exc_info=True)

    async with _get_local_lock():
        current = int(_local_slots_by_key.get(key, 0))
        if current <= 1:
            _local_slots_by_key.pop(key, None)
            return
        _local_slots_by_key[key] = current - 1


async def acquire_with_backoff(
    *,
    redis_pool: object | None,
    max_slots: int,
    slot_ttl_s: int,
    attempts: int,
    backoff_s: int,
    jitter_s: int,
    slot_key: str | None = None,
) -> bool:
    retries = max(1, attempts)
    for attempt in range(1, retries + 1):
        acquired = await try_acquire_sip_slot(
            redis_pool=redis_pool,
            max_slots=max_slots,
            slot_ttl_s=slot_ttl_s,
            slot_key=slot_key,
        )
        if acquired:
            return True
        if attempt >= retries:
            return False
        wait_s = max(1, backoff_s) + random.uniform(0, max(0, jitter_s))
        await asyncio.sleep(wait_s)
    return False
