from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from .. import metrics as api_metrics
from ..text_normalization import strip_lower_or_none

ProviderSource = Literal["api", "agent", "judge"]
KnownProviderCircuitState = Literal["open", "half_open", "closed"]
ProviderCircuitState = Literal["open", "half_open", "closed", "unknown"]

logger = logging.getLogger("botcheck.api.provider_state")


@dataclass(frozen=True)
class ProviderCircuitIdentity:
    source: ProviderSource
    provider: str
    service: str
    component: str


@dataclass(frozen=True)
class ProviderCircuitSnapshot:
    source: ProviderSource
    provider: str
    service: str
    component: str
    state: ProviderCircuitState
    updated_at: datetime | None


KNOWN_PROVIDER_CIRCUITS: tuple[ProviderCircuitIdentity, ...] = (
    ProviderCircuitIdentity(
        source="agent",
        provider="botcheck",
        service="harness",
        component="worker",
    ),
    ProviderCircuitIdentity(
        source="api",
        provider="openai",
        service="tts",
        component="api_preview",
    ),
    ProviderCircuitIdentity(
        source="api",
        provider="elevenlabs",
        service="tts",
        component="api_preview",
    ),
    ProviderCircuitIdentity(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
    ),
    ProviderCircuitIdentity(
        source="agent",
        provider="elevenlabs",
        service="tts",
        component="agent_live_tts",
    ),
    ProviderCircuitIdentity(
        source="agent",
        provider="deepgram",
        service="stt",
        component="agent_live_stt",
    ),
    ProviderCircuitIdentity(
        source="agent",
        provider="azure",
        service="stt",
        component="agent_live_stt",
    ),
    ProviderCircuitIdentity(
        source="judge",
        provider="openai",
        service="tts",
        component="judge_cache_warm",
    ),
    ProviderCircuitIdentity(
        source="judge",
        provider="elevenlabs",
        service="tts",
        component="judge_cache_warm",
    ),
)

_ALL_STATES: tuple[ProviderCircuitState, ...] = ("open", "half_open", "closed", "unknown")


class _ProviderCircuitPayload(BaseModel):
    source: ProviderSource
    provider: str
    service: str
    component: str
    state: KnownProviderCircuitState
    updated_at: datetime


def provider_circuit_key(
    *,
    source: ProviderSource,
    provider: str,
    service: str,
    component: str,
) -> str:
    source_key = strip_lower_or_none(source) or ""
    provider_key = strip_lower_or_none(provider) or ""
    service_key = strip_lower_or_none(service) or ""
    component_key = strip_lower_or_none(component) or ""
    return (
        f"botcheck:provider-circuit:{source_key}:{provider_key}:{service_key}:{component_key}"
    )


def _parse_datetime_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _decode_payload(raw: object) -> _ProviderCircuitPayload | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            logger.debug("provider_circuit_snapshot_decode_bytes_failed", exc_info=True)
            return None
    if isinstance(raw, str):
        try:
            return _ProviderCircuitPayload.model_validate_json(raw)
        except ValidationError:
            logger.debug("provider_circuit_snapshot_invalid_schema")
            return None
        except Exception:
            logger.warning("provider_circuit_snapshot_unexpected_parse_error", exc_info=True)
            return None
    if isinstance(raw, dict):
        try:
            return _ProviderCircuitPayload.model_validate(raw)
        except ValidationError:
            logger.debug("provider_circuit_snapshot_invalid_schema")
            return None
    return None


async def store_provider_circuit_snapshot(
    redis_pool: object | None,
    *,
    source: ProviderSource,
    provider: str,
    service: str,
    component: str,
    state: KnownProviderCircuitState,
    observed_at: datetime | None,
    ttl_s: int,
) -> bool:
    set_fn = getattr(redis_pool, "set", None) if redis_pool is not None else None
    if set_fn is None:
        return False

    timestamp = observed_at.astimezone(UTC) if observed_at is not None else datetime.now(UTC)
    key = provider_circuit_key(
        source=source,
        provider=provider,
        service=service,
        component=component,
    )
    payload = _ProviderCircuitPayload(
        source=source,  # ProviderSource Literal — already lowercase by type contract
        provider=strip_lower_or_none(provider) or "",
        service=strip_lower_or_none(service) or "",
        component=strip_lower_or_none(component) or "",
        state=state,
        updated_at=timestamp,
    ).model_dump_json()
    try:
        await set_fn(key, payload, ex=max(1, int(ttl_s)))
    except Exception:
        logger.warning(
            "provider_circuit_snapshot_store_failed source=%s provider=%s service=%s component=%s",
            source,
            provider,
            service,
            component,
            exc_info=True,
        )
        return False
    return True


async def read_provider_circuit_snapshots(
    redis_pool: object | None,
    *,
    stale_after_s: float,
    now: datetime | None = None,
) -> list[ProviderCircuitSnapshot]:
    observed_now = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    get_fn = getattr(redis_pool, "get", None) if redis_pool is not None else None
    snapshots: list[ProviderCircuitSnapshot] = []

    for circuit in KNOWN_PROVIDER_CIRCUITS:
        state: ProviderCircuitState = "unknown"
        updated_at: datetime | None = None
        if get_fn is not None:
            key = provider_circuit_key(
                source=circuit.source,
                provider=circuit.provider,
                service=circuit.service,
                component=circuit.component,
            )
            try:
                payload = _decode_payload(await get_fn(key))
            except Exception:
                logger.warning("provider_circuit_snapshot_read_failed key=%s", key, exc_info=True)
                payload = None
            if payload is not None:
                # payload is a fully-validated _ProviderCircuitPayload; state is
                # guaranteed to be KnownProviderCircuitState and updated_at is a
                # timezone-aware datetime — no secondary validation needed.
                updated_at = payload.updated_at.astimezone(UTC)
                age_s = max(0.0, (observed_now - updated_at).total_seconds())
                if age_s <= stale_after_s:
                    state = payload.state

        snapshots.append(
            ProviderCircuitSnapshot(
                source=circuit.source,
                provider=circuit.provider,
                service=circuit.service,
                component=circuit.component,
                state=state,
                updated_at=updated_at,
            )
        )
    return snapshots


def provider_degraded(snapshots: list[ProviderCircuitSnapshot]) -> bool:
    return any(snapshot.state == "open" for snapshot in snapshots)


def harness_worker_snapshot(snapshots: list[ProviderCircuitSnapshot]) -> ProviderCircuitSnapshot:
    for snapshot in snapshots:
        if (
            snapshot.source == "agent"
            and snapshot.provider == "botcheck"
            and snapshot.service == "harness"
            and snapshot.component == "worker"
        ):
            return snapshot
    return ProviderCircuitSnapshot(
        source="agent",
        provider="botcheck",
        service="harness",
        component="worker",
        state="unknown",
        updated_at=None,
    )


def harness_degraded(snapshots: list[ProviderCircuitSnapshot]) -> bool:
    return harness_worker_snapshot(snapshots).state != "closed"


def observe_provider_circuit_state_gauge(snapshots: list[ProviderCircuitSnapshot]) -> None:
    """Project snapshot read-model into one-hot Prometheus gauge samples."""
    for snapshot in snapshots:
        for state in _ALL_STATES:
            api_metrics.PROVIDER_CIRCUIT_STATE.labels(
                source=snapshot.source,
                provider=snapshot.provider,
                service=snapshot.service,
                component=snapshot.component,
                state=state,
            ).set(1.0 if snapshot.state == state else 0.0)
