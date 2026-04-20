from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from fastapi import HTTPException

import pytest
from botcheck_scenarios import CircuitOpenError, CircuitState

from botcheck_api.exceptions import ApiProblem, PROVIDER_QUOTA_EXCEEDED
from botcheck_api.scenarios import service as scenario_service
from botcheck_api.runs import provider_state as provider_state

_FAKE_TENANT = "test-tenant"
_FAKE_DB = AsyncMock()


class _OpenCircuitBreaker:
    async def call(self, _operation, *, on_transition=None, on_reject=None):
        del on_transition
        if on_reject is not None:
            on_reject(CircuitState.OPEN)
        raise CircuitOpenError("api.preview_tts.openai")


class _FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        del ex
        self.storage[key] = value
        return True

    async def get(self, key: str):
        return self.storage.get(key)


class _PassThroughBreaker:
    async def call(self, operation, *, on_transition=None, on_reject=None):
        del on_transition, on_reject
        return await operation()


class _FakeCounter:
    def __init__(self) -> None:
        self.incs: list[dict[str, str]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {key: str(value) for key, value in kwargs.items()}
        return self

    def inc(self, amount: float = 1.0) -> None:
        del amount
        self.incs.append(dict(self._labels))


@pytest.mark.asyncio
async def test_synthesize_preview_wav_returns_503_when_circuit_open(monkeypatch) -> None:
    class _FakeOpenAIProvider:
        provider_id = "openai"
        model_label = "gpt-4o-mini-tts"

    async def _fake_resolve(db, *, tenant_id, tts_voice):
        return _FakeOpenAIProvider()

    monkeypatch.setattr(scenario_service, "resolve_tenant_preview_tts_provider", _fake_resolve)
    monkeypatch.setattr(
        scenario_service,
        "get_preview_tts_circuit_breaker",
        lambda _provider: _OpenCircuitBreaker(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await scenario_service.synthesize_preview_wav(
            _FAKE_DB,
            tenant_id=_FAKE_TENANT,
            text="hello",
            tts_voice="openai:nova",
        )

    assert exc_info.value.status_code == 503
    assert "circuit open" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_synthesize_preview_wav_publishes_open_snapshot_on_reject(monkeypatch) -> None:
    class _FakeOpenAIProvider:
        provider_id = "openai"
        model_label = "gpt-4o-mini-tts"

    async def _fake_resolve(db, *, tenant_id, tts_voice):
        return _FakeOpenAIProvider()

    monkeypatch.setattr(scenario_service, "resolve_tenant_preview_tts_provider", _fake_resolve)
    monkeypatch.setattr(
        scenario_service,
        "get_preview_tts_circuit_breaker",
        lambda _provider: _OpenCircuitBreaker(),
    )
    fake_redis = _FakeRedis()

    with pytest.raises(HTTPException):
        await scenario_service.synthesize_preview_wav(
            _FAKE_DB,
            tenant_id=_FAKE_TENANT,
            text="hello",
            tts_voice="openai:nova",
            provider_state_pool=fake_redis,
        )

    # Snapshot publish is fire-and-forget; yield to event loop once.
    await asyncio.sleep(0)

    snapshots = await provider_state.read_provider_circuit_snapshots(
        fake_redis,
        stale_after_s=300.0,
    )
    by_component = {
        (row.source, row.provider, row.component): row for row in snapshots
    }
    assert by_component[("api", "openai", "api_preview")].state == "open"


@pytest.mark.asyncio
async def test_synthesize_preview_wav_does_not_require_openai_key_for_elevenlabs(
    monkeypatch,
) -> None:
    class _FakeProvider:
        provider_id = "elevenlabs"
        model_label = "eleven_flash_v2_5"

        async def synthesize_wav(self, *, text: str, timeout_s: float, response_format: str = "wav") -> bytes:
            assert text == "hello"
            assert timeout_s == scenario_service.settings.tts_preview_request_timeout_s
            assert response_format == "wav"
            return b"RIFF_TEST"

    async def _fake_resolve(db, *, tenant_id, tts_voice):
        return _FakeProvider()

    monkeypatch.setattr(scenario_service.settings, "openai_api_key", "")
    monkeypatch.setattr(
        scenario_service,
        "resolve_tenant_preview_tts_provider",
        _fake_resolve,
    )
    monkeypatch.setattr(
        scenario_service,
        "get_preview_tts_circuit_breaker",
        lambda _provider: _PassThroughBreaker(),
    )

    wav = await scenario_service.synthesize_preview_wav(
        _FAKE_DB,
        tenant_id=_FAKE_TENANT,
        text="hello",
        tts_voice="elevenlabs:voice-123",
    )

    assert wav == b"RIFF_TEST"


@pytest.mark.asyncio
async def test_synthesize_preview_wav_records_elevenlabs_circuit_open_with_same_metric_shape(
    monkeypatch,
) -> None:
    class _FakeProvider:
        provider_id = "elevenlabs"
        model_label = "eleven_flash_v2_5"

    api_calls_counter = _FakeCounter()
    fake_redis = _FakeRedis()
    async def _fake_resolve(db, *, tenant_id, tts_voice):
        return _FakeProvider()

    monkeypatch.setattr(
        scenario_service,
        "resolve_tenant_preview_tts_provider",
        _fake_resolve,
    )
    monkeypatch.setattr(
        scenario_service,
        "get_preview_tts_circuit_breaker",
        lambda _provider: _OpenCircuitBreaker(),
    )
    monkeypatch.setattr(
        scenario_service.api_metrics,
        "PROVIDER_API_CALLS_TOTAL",
        api_calls_counter,
    )

    with pytest.raises(HTTPException):
        await scenario_service.synthesize_preview_wav(
            _FAKE_DB,
            tenant_id=_FAKE_TENANT,
            text="hello",
            tts_voice="elevenlabs:voice-123",
            provider_state_pool=fake_redis,
        )

    await asyncio.sleep(0)

    assert any(
        labels == {
            "provider": "elevenlabs",
            "service": "tts",
            "model": "eleven_flash_v2_5",
            "outcome": "circuit_open",
        }
        for labels in api_calls_counter.incs
    )

    snapshots = await provider_state.read_provider_circuit_snapshots(
        fake_redis,
        stale_after_s=300.0,
    )
    by_component = {
        (row.source, row.provider, row.component): row for row in snapshots
    }
    assert by_component[("api", "elevenlabs", "api_preview")].state == "open"


@pytest.mark.asyncio
async def test_synthesize_preview_wav_rejects_when_provider_quota_blocked(monkeypatch) -> None:
    class _FakeProvider:
        provider_id = "openai"
        catalog_provider_id = "openai:gpt-4o-mini-tts"
        model_label = "gpt-4o-mini-tts"

    async def _fake_resolve(db, *, tenant_id, tts_voice):
        return _FakeProvider()

    quota_mock = AsyncMock(
        side_effect=ApiProblem(
            status=429,
            error_code=PROVIDER_QUOTA_EXCEEDED,
            detail="Provider quota exceeded for openai:gpt-4o-mini-tts (requests)",
        )
    )

    monkeypatch.setattr(scenario_service, "resolve_tenant_preview_tts_provider", _fake_resolve)
    monkeypatch.setattr(scenario_service, "assert_provider_quota_available", quota_mock)
    monkeypatch.setattr(
        scenario_service,
        "get_preview_tts_circuit_breaker",
        lambda _provider: pytest.fail("quota block should happen before circuit breaker call"),
    )

    with pytest.raises(ApiProblem) as exc_info:
        await scenario_service.synthesize_preview_wav(
            _FAKE_DB,
            tenant_id=_FAKE_TENANT,
            text="hello",
            tts_voice="openai:nova",
        )

    assert exc_info.value.error_code == PROVIDER_QUOTA_EXCEEDED
    quota_mock.assert_awaited_once()
