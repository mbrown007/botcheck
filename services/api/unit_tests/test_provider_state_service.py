from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from botcheck_api import metrics as api_metrics
from botcheck_api.runs import provider_state as svc


class _FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        del ex
        self.storage[key] = value
        return True

    async def get(self, key: str):
        return self.storage.get(key)


def test_provider_circuit_key_normalizes_fields() -> None:
    key = svc.provider_circuit_key(
        source="agent",
        provider=" OpenAI ",
        service=" TTS ",
        component=" Agent_Live_TTS ",
    )
    assert key == "botcheck:provider-circuit:agent:openai:tts:agent_live_tts"


@pytest.mark.asyncio
async def test_store_and_read_provider_circuit_snapshot_round_trip() -> None:
    redis = _FakeRedis()
    observed_at = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)
    stored = await svc.store_provider_circuit_snapshot(
        redis,
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="open",
        observed_at=observed_at,
        ttl_s=120,
    )
    assert stored is True

    snapshots = await svc.read_provider_circuit_snapshots(
        redis,
        stale_after_s=300.0,
        now=observed_at + timedelta(seconds=30),
    )
    by_component = {
        (row.source, row.provider, row.component): row for row in snapshots
    }
    assert by_component[("agent", "openai", "agent_live_tts")].state == "open"
    assert by_component[("agent", "openai", "agent_live_tts")].updated_at == observed_at
    assert svc.provider_degraded(snapshots) is True


@pytest.mark.asyncio
async def test_read_provider_snapshots_defaults_to_unknown_without_pool() -> None:
    snapshots = await svc.read_provider_circuit_snapshots(
        None,
        stale_after_s=120.0,
    )
    assert len(snapshots) == 9
    assert {row.state for row in snapshots} == {"unknown"}
    assert svc.provider_degraded(snapshots) is False
    assert svc.harness_degraded(snapshots) is True


@pytest.mark.asyncio
async def test_read_provider_snapshots_defaults_include_agent_live_stt() -> None:
    snapshots = await svc.read_provider_circuit_snapshots(
        None,
        stale_after_s=120.0,
    )
    by_component = {
        (row.source, row.provider, row.service, row.component): row
        for row in snapshots
    }
    assert by_component[("agent", "deepgram", "stt", "agent_live_stt")].state == "unknown"
    assert by_component[("agent", "azure", "stt", "agent_live_stt")].state == "unknown"


@pytest.mark.asyncio
async def test_read_provider_snapshot_marks_stale_unknown() -> None:
    redis = _FakeRedis()
    key = svc.provider_circuit_key(
        source="judge",
        provider="openai",
        service="tts",
        component="judge_cache_warm",
    )
    stale_at = datetime(2026, 3, 4, 10, 0, tzinfo=UTC)
    redis.storage[key] = json.dumps(
        {
            "source": "judge",
            "provider": "openai",
            "service": "tts",
            "component": "judge_cache_warm",
            "state": "open",
            "updated_at": stale_at.isoformat(),
        }
    )
    snapshots = await svc.read_provider_circuit_snapshots(
        redis,
        stale_after_s=30.0,
        now=stale_at + timedelta(seconds=120),
    )
    by_component = {
        (row.source, row.provider, row.component): row for row in snapshots
    }
    assert by_component[("judge", "openai", "judge_cache_warm")].state == "unknown"
    assert by_component[("judge", "openai", "judge_cache_warm")].updated_at == stale_at


@pytest.mark.asyncio
async def test_read_provider_snapshot_ignores_malformed_payload() -> None:
    redis = _FakeRedis()
    key = svc.provider_circuit_key(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
    )
    redis.storage[key] = '{"provider":"openai","service":"tts","component":"agent_live_tts"}'

    snapshots = await svc.read_provider_circuit_snapshots(
        redis,
        stale_after_s=300.0,
        now=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    by_component = {
        (row.source, row.provider, row.component): row for row in snapshots
    }
    assert by_component[("agent", "openai", "agent_live_tts")].state == "unknown"
    assert by_component[("agent", "openai", "agent_live_tts")].updated_at is None


def test_observe_provider_circuit_state_gauge_sets_one_hot_state() -> None:
    snapshots = [
        svc.ProviderCircuitSnapshot(
            source="agent",
            provider="openai",
            service="tts",
            component="agent_live_tts",
            state="open",
            updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
        )
    ]
    svc.observe_provider_circuit_state_gauge(snapshots)

    open_value = api_metrics.PROVIDER_CIRCUIT_STATE.labels(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="open",
    )._value.get()
    unknown_value = api_metrics.PROVIDER_CIRCUIT_STATE.labels(
        source="agent",
        provider="openai",
        service="tts",
        component="agent_live_tts",
        state="unknown",
    )._value.get()
    assert open_value == 1.0
    assert unknown_value == 0.0


def test_harness_worker_snapshot_returns_default_unknown_when_missing() -> None:
    snapshot = svc.harness_worker_snapshot([])
    assert snapshot.source == "agent"
    assert snapshot.provider == "botcheck"
    assert snapshot.service == "harness"
    assert snapshot.component == "worker"
    assert snapshot.state == "unknown"
