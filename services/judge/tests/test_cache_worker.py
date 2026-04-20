"""Tests for Phase 7 cache worker functions."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")

import httpx
import pytest
from botcheck_judge.metrics import TTS_CACHE_WARM_LATENCY_SECONDS
from botcheck_judge.tts_provider import reset_cache_warm_tts_breakers
from botcheck_judge.workers import cache_worker
from botocore.exceptions import ClientError

from botcheck_scenarios import (
    BotConfig,
    BotListenBlock,
    BranchCase,
    BranchConfig,
    CircuitOpenError,
    HangupBlock,
    HarnessPromptBlock,
    PromptContent,
    ScenarioDefinition,
    ScenarioType,
    TimeRouteBlock,
    TimeRouteWindow,
    TTSProviderDisabledError,
    Turn,
)


@pytest.fixture(autouse=True)
def reset_cache_tts_circuit() -> None:
    reset_cache_warm_tts_breakers()


def _scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache",
        name="Scenario Cache",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(id="t1", text="Hello there"),
            Turn(id="t2", text="Please confirm your account"),
            Turn(id="t3", speaker="bot", text="Welcome"),
        ],
    )


def _branching_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache-branching",
        name="Scenario Cache Branching",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(
                id="t1",
                text="Do you need billing or technical support?",
                wait_for_response=True,
                branching=BranchConfig(
                    default="t_fallback",
                    cases=[
                        BranchCase(condition="billing", next="t_billing"),
                        BranchCase(condition="technical", next="t_tech"),
                    ],
                ),
            ),
            Turn(id="t_billing", text="Let me route billing.", next="t_end"),
            Turn(id="t_tech", text="Let me route technical.", next="t_end"),
            Turn(id="t_fallback", text="Please repeat your request.", next="t_end"),
            Turn(id="t_end", speaker="bot", text="Connected."),
        ],
    )


class _FakePaginator:
    def __init__(
        self,
        pages_by_prefix: dict[str, list[dict[str, Any]]],
        errors_by_prefix: dict[str, Exception] | None = None,
    ) -> None:
        self._pages_by_prefix = pages_by_prefix
        self._errors_by_prefix = errors_by_prefix or {}

    async def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803
        error = self._errors_by_prefix.get(Prefix)
        if error is not None:
            raise error
        for page in self._pages_by_prefix.get(Prefix, []):
            yield page


class _FakeS3Client:
    def __init__(self) -> None:
        self.existing_keys: set[str] = set()
        self.put_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.deleted_manifest: str | None = None
        self.deleted_object_keys: list[str] = []
        self.pages_by_prefix: dict[str, list[dict[str, Any]]] = {}
        self.list_errors_by_prefix: dict[str, Exception] = {}

    async def head_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key not in self.existing_keys:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return {"Key": Key}

    async def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        key = str(kwargs.get("Key"))
        self.existing_keys.add(key)
        return {"ETag": "etag"}

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return _FakePaginator(self.pages_by_prefix, self.list_errors_by_prefix)

    async def delete_objects(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {"Deleted": kwargs.get("Delete", {}).get("Objects", [])}

    async def delete_object(self, *, Bucket: str, Key: str):  # noqa: N803
        self.deleted_object_keys.append(Key)
        if Key.endswith("/manifest.json"):
            self.deleted_manifest = Key
        return {"DeleteMarker": True}


class _FakeS3ClientCM:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> _FakeS3Client:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeS3Session:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    def client(self, *_args, **_kwargs):
        return _FakeS3ClientCM(self._client)


class _PassThroughBreaker:
    async def call(self, operation, *, on_transition=None, on_reject=None):
        del on_transition, on_reject
        return await operation()


def _warm_payload() -> dict[str, Any]:
    scenario = _scenario()
    return {
        "scenario_id": scenario.id,
        "tenant_id": "tenant-a",
        "scenario_version_hash": "vh-1",
        "scenario_payload": scenario.model_dump(mode="json"),
    }


def _time_route_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache-time-route",
        name="Scenario Cache Time Route",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            BotListenBlock(id="t0_pickup", next="t_route"),
            TimeRouteBlock(
                id="t_route",
                timezone="UTC",
                windows=[
                    TimeRouteWindow(
                        label="business_hours",
                        start="09:00",
                        end="17:00",
                        next="t_day",
                    ),
                    TimeRouteWindow(
                        label="after_hours",
                        start="17:00",
                        end="09:00",
                        next="t_night",
                    ),
                ],
                default="t_day",
            ),
            HarnessPromptBlock(
                id="t_day",
                content=PromptContent(text="Day path"),
                listen=True,
                next="t_end",
            ),
            HarnessPromptBlock(
                id="t_night",
                content=PromptContent(text="Night path"),
                listen=True,
                next="t_end",
            ),
            HangupBlock(id="t_end"),
        ],
    )


def _time_route_warm_payload() -> dict[str, Any]:
    scenario = _time_route_scenario()
    return {
        "scenario_id": scenario.id,
        "tenant_id": "tenant-a",
        "scenario_version_hash": "vh-time-route",
        "scenario_payload": scenario.model_dump(mode="json"),
    }


def _hist_count(histogram, **labels):
    labeled = histogram.labels(**labels) if labels else histogram
    for metric in labeled.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    raise AssertionError("Histogram count sample not found")


def test_derive_cache_status() -> None:
    assert cache_worker._derive_cache_status(total=0, cached=0, skipped=0, failed=0) == "warm"
    assert cache_worker._derive_cache_status(total=2, cached=2, skipped=0, failed=0) == "warm"
    assert cache_worker._derive_cache_status(total=2, cached=1, skipped=0, failed=1) == "partial"
    assert cache_worker._derive_cache_status(total=2, cached=0, skipped=0, failed=2) == "cold"


@pytest.mark.asyncio
async def test_warm_tts_cache_writes_turn_audio_and_manifest(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)
    warm_latency_before = _hist_count(TTS_CACHE_WARM_LATENCY_SECONDS, outcome="warm")

    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())

    assert result["cache_status"] == "warm"
    assert result["cached"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["status_applied"] is True

    # Two turn WAV writes + one manifest write
    assert len(fake_s3.put_calls) == 3
    keys = [str(call["Key"]) for call in fake_s3.put_calls]
    assert any(k.endswith("/tts-cache/t1/" + k.split("/")[-1]) for k in keys if "/t1/" in k)
    assert any(k.endswith("/tts-cache/t2/" + k.split("/")[-1]) for k in keys if "/t2/" in k)
    assert "tenant-a/tts-cache/scenario-cache/manifest.json" in keys
    manifest_put = next(call for call in fake_s3.put_calls if str(call["Key"]).endswith("/manifest.json"))
    manifest = manifest_put["Body"].decode()
    assert "\"turn_states\"" in manifest
    assert _hist_count(TTS_CACHE_WARM_LATENCY_SECONDS, outcome="warm") == warm_latency_before + 1
    assert synth_mock.await_count == 2
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_tts_cache_fetches_provider_runtime_context_and_applies_overrides(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    fetch_mock = AsyncMock(
        return_value={
            "feature_flags": {"feature_tts_provider_openai_enabled": True},
            "tts": {
                "vendor": "openai",
                "secret_fields": {"api_key": "stored-openai-key"},
            },
        }
    )
    monkeypatch.setattr(cache_worker, "_fetch_provider_runtime_context", fetch_mock)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav_with_retry", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())

    assert result["cache_status"] == "warm"
    fetch_mock.assert_awaited_once()
    first_call = synth_mock.await_args_list[0]
    runtime_settings = first_call.kwargs["settings_obj"]
    assert runtime_settings.openai_api_key == "stored-openai-key"
    assert runtime_settings.feature_tts_provider_openai_enabled is True


@pytest.mark.asyncio
async def test_warm_tts_cache_recaches_only_modified_turn(monkeypatch):
    scenario_old = _scenario()
    scenario_new = scenario_old.model_copy(deep=True)
    scenario_new.turns[1].content.text = "Please confirm your account number"

    old_t1_key = scenario_old.turn_cache_key(scenario_old.turns[0], "tenant-a")
    old_t2_key = scenario_old.turn_cache_key(scenario_old.turns[1], "tenant-a")
    new_t2_key = scenario_new.turn_cache_key(scenario_new.turns[1], "tenant-a")

    fake_s3 = _FakeS3Client()
    fake_s3.existing_keys.update({old_t1_key, old_t2_key})
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    payload = {
        "scenario_id": scenario_new.id,
        "tenant_id": "tenant-a",
        "scenario_version_hash": "vh-2",
        "scenario_payload": scenario_new.model_dump(mode="json"),
    }
    result = await cache_worker.warm_tts_cache({}, payload=payload)

    assert result["cache_status"] == "warm"
    assert result["cached"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert synth_mock.await_count == 1
    assert synth_mock.await_args_list[0].kwargs["text"] == "Please confirm your account number"

    put_keys = [str(call["Key"]) for call in fake_s3.put_calls]
    assert new_t2_key in put_keys
    assert old_t1_key not in put_keys
    assert "tenant-a/tts-cache/scenario-cache/manifest.json" in put_keys
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_tts_cache_retries_transient_timeout(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(cache_worker.settings, "tts_cache_turn_max_attempts", 2)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_turn_retry_backoff_s", 0.0)

    synth_mock = AsyncMock(
        side_effect=[httpx.ReadTimeout("boom"), b"wav-bytes", b"wav-bytes"]
    )
    sync_mock = AsyncMock(return_value=True)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)
    monkeypatch.setattr(cache_worker.asyncio, "sleep", sleep_mock)

    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())

    assert result["cache_status"] == "warm"
    assert result["cached"] == 2
    assert result["failed"] == 0
    assert synth_mock.await_count == 3
    sleep_mock.assert_awaited_once()
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_tts_cache_isolated_by_tenant_prefix(monkeypatch):
    scenario = _scenario()
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    payload_a = {
        "scenario_id": scenario.id,
        "tenant_id": "tenant-a",
        "scenario_version_hash": "vh-a",
        "scenario_payload": scenario.model_dump(mode="json"),
    }
    payload_b = {
        "scenario_id": scenario.id,
        "tenant_id": "tenant-b",
        "scenario_version_hash": "vh-b",
        "scenario_payload": scenario.model_dump(mode="json"),
    }

    result_a = await cache_worker.warm_tts_cache({}, payload=payload_a)
    result_b = await cache_worker.warm_tts_cache({}, payload=payload_b)

    assert result_a["cached"] == 2
    assert result_b["cached"] == 2
    assert synth_mock.await_count == 4

    put_keys = [str(call["Key"]) for call in fake_s3.put_calls]
    tenant_a_keys = [k for k in put_keys if k.startswith("tenant-a/tts-cache/")]
    tenant_b_keys = [k for k in put_keys if k.startswith("tenant-b/tts-cache/")]
    assert tenant_a_keys
    assert tenant_b_keys


@pytest.mark.asyncio
async def test_warm_tts_cache_masks_provider_secrets_when_runtime_context_fetch_fails(monkeypatch):
    """When runtime context is unavailable, cache warming must not fall back to env keys."""
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(
        cache_worker,
        "_fetch_provider_runtime_context",
        AsyncMock(side_effect=Exception("API unavailable")),
    )
    synth_mock = AsyncMock(return_value=b"wav-bytes")
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav_with_retry", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", AsyncMock(return_value=True))

    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())
    assert result["cache_status"] == "warm"
    assert result["cached"] == 2
    runtime_settings = synth_mock.await_args_list[0].kwargs["settings_obj"]
    assert runtime_settings.openai_api_key == ""


@pytest.mark.asyncio
async def test_warm_tts_cache_branching_scenario_precaches_all_harness_arms(monkeypatch):
    scenario = _branching_scenario()
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    payload = {
        "scenario_id": scenario.id,
        "tenant_id": "tenant-a",
        "scenario_version_hash": "vh-branching",
        "scenario_payload": scenario.model_dump(mode="json"),
    }
    result = await cache_worker.warm_tts_cache({}, payload=payload)

    # Pre-warm includes all cacheable harness turns, including branch arms that
    # may be unexecuted in any single run path.
    assert result["cache_status"] == "warm"
    assert result["total_harness_turns"] == 4
    assert result["cached"] == 4
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert synth_mock.await_count == 4

    put_keys = {str(call["Key"]) for call in fake_s3.put_calls}
    assert any("/tts-cache/t1/" in key for key in put_keys)
    assert any("/tts-cache/t_billing/" in key for key in put_keys)
    assert any("/tts-cache/t_tech/" in key for key in put_keys)
    assert any("/tts-cache/t_fallback/" in key for key in put_keys)
    assert "tenant-a/tts-cache/scenario-cache-branching/manifest.json" in put_keys
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_tts_cache_accepts_time_route_payload_and_precaches_harness_turns(
    monkeypatch,
):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    result = await cache_worker.warm_tts_cache({}, payload=_time_route_warm_payload())

    assert result["cache_status"] == "warm"
    assert result["total_harness_turns"] == 2
    assert result["cached"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert synth_mock.await_count == 2
    assert [call.kwargs["text"] for call in synth_mock.await_args_list] == [
        "Day path",
        "Night path",
    ]

    put_keys = {str(call["Key"]) for call in fake_s3.put_calls}
    assert any("/tts-cache/t_day/" in key for key in put_keys)
    assert any("/tts-cache/t_night/" in key for key in put_keys)
    assert "tenant-a/tts-cache/scenario-cache-time-route/manifest.json" in put_keys
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_tts_cache_stale_sync_marks_status_not_applied(monkeypatch):
    fake_s3 = _FakeS3Client()
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    synth_mock = AsyncMock(return_value=b"wav-bytes")
    sync_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(cache_worker, "_synthesize_to_wav", synth_mock)
    monkeypatch.setattr(cache_worker, "_sync_cache_status", sync_mock)

    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())

    assert result["cache_status"] == "warm"
    assert result["cached"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["status_applied"] is False
    sync_mock.assert_awaited_once()
    assert sync_mock.await_args.kwargs["scenario_version_hash"] == "vh-1"


@pytest.mark.asyncio
async def test_warm_tts_cache_returns_disabled_when_feature_flag_off(monkeypatch):
    monkeypatch.setattr(cache_worker.settings, "tts_cache_enabled", False)
    result = await cache_worker.warm_tts_cache({}, payload=_warm_payload())
    assert result == {"disabled": True}


@pytest.mark.asyncio
async def test_warm_tts_cache_rejects_scenario_id_mismatch():
    payload = _warm_payload()
    payload["scenario_id"] = "different-id"
    with pytest.raises(ValueError, match="scenario_id mismatch"):
        await cache_worker.warm_tts_cache({}, payload=payload)


@pytest.mark.asyncio
async def test_synthesize_to_wav_fails_fast_when_circuit_open(monkeypatch):
    class _OpenBreaker:
        async def call(self, _operation, *, on_transition=None, on_reject=None):
            del on_transition
            if on_reject is not None:
                on_reject(None)
            raise CircuitOpenError("judge.cache_tts.openai")

    monkeypatch.setattr(cache_worker.settings, "openai_api_key", "test-openai")
    monkeypatch.setattr(
        cache_worker,
        "get_cache_warm_tts_circuit_breaker",
        lambda _provider: _OpenBreaker(),
    )

    with pytest.raises(RuntimeError, match="circuit is open"):
        await cache_worker._synthesize_to_wav(text="hello", tts_voice="openai:nova")


@pytest.mark.asyncio
async def test_synthesize_to_wav_uses_resolved_provider_without_openai_key(monkeypatch):
    class _FakeProvider:
        provider_id = "elevenlabs"
        model_label = "eleven_flash_v2_5"

        async def synthesize_wav(self, *, text: str, timeout_s: float, response_format: str = "wav") -> bytes:
            assert text == "hello"
            assert timeout_s == cache_worker.settings.tts_cache_request_timeout_s
            assert response_format == "wav"
            return b"RIFF_TEST"

    monkeypatch.setattr(cache_worker.settings, "openai_api_key", None)
    monkeypatch.setattr(
        cache_worker,
        "resolve_cache_warm_tts_provider",
        lambda _tts_voice, **_kwargs: _FakeProvider(),
    )
    monkeypatch.setattr(
        cache_worker,
        "get_cache_warm_tts_circuit_breaker",
        lambda _provider: _PassThroughBreaker(),
    )

    wav = await cache_worker._synthesize_to_wav(
        text="hello",
        tts_voice="elevenlabs:voice-123",
    )

    assert wav == b"RIFF_TEST"


@pytest.mark.asyncio
async def test_synthesize_to_wav_rejects_disabled_elevenlabs_without_fallback(monkeypatch):
    monkeypatch.setattr(cache_worker.settings, "feature_tts_provider_elevenlabs_enabled", False)
    monkeypatch.setattr(cache_worker.settings, "feature_tts_provider_openai_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "openai_api_key", "test-openai")

    with pytest.raises(TTSProviderDisabledError, match="elevenlabs"):
        await cache_worker._synthesize_to_wav(
            text="hello",
            tts_voice="elevenlabs:voice-123",
        )


@pytest.mark.asyncio
async def test_purge_tts_cache_deletes_turn_prefix_objects(monkeypatch):
    fake_s3 = _FakeS3Client()
    fake_s3.pages_by_prefix = {
        "tenant-a/tts-cache/t1/": [
            {"Contents": [{"Key": "tenant-a/tts-cache/t1/a.wav"}]},
        ],
        "tenant-a/tts-cache/t2/": [
            {"Contents": [{"Key": "tenant-a/tts-cache/t2/b.wav"}]},
            {"Contents": [{"Key": "tenant-a/tts-cache/t2/c.wav"}]},
        ],
    }
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    result = await cache_worker.purge_tts_cache(
        {},
        payload={
            "scenario_id": "scenario-cache",
            "tenant_id": "tenant-a",
            "turn_ids": ["t1", "t2"],
        },
    )

    assert result["deleted"] == 3
    assert result["errors"] == 0
    assert fake_s3.deleted_manifest == "tenant-a/tts-cache/scenario-cache/manifest.json"
    assert len(fake_s3.delete_calls) == 3


@pytest.mark.asyncio
async def test_purge_tts_cache_continues_on_turn_prefix_error(monkeypatch):
    fake_s3 = _FakeS3Client()
    fake_s3.pages_by_prefix = {
        "tenant-a/tts-cache/t2/": [
            {"Contents": [{"Key": "tenant-a/tts-cache/t2/b.wav"}]},
        ],
    }
    fake_s3.list_errors_by_prefix = {
        "tenant-a/tts-cache/t1/": ClientError(
            {"Error": {"Code": "500", "Message": "boom"}},
            "ListObjectsV2",
        )
    }
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )

    result = await cache_worker.purge_tts_cache(
        {},
        payload={
            "scenario_id": "scenario-cache",
            "tenant_id": "tenant-a",
            "turn_ids": ["t1", "t2"],
        },
    )

    assert result["deleted"] == 1
    assert result["errors"] == 1
    assert fake_s3.deleted_manifest == "tenant-a/tts-cache/scenario-cache/manifest.json"
    assert len(fake_s3.delete_calls) == 1


@pytest.mark.asyncio
async def test_gc_tts_cache_returns_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(cache_worker.settings, "tts_cache_enabled", False)
    result = await cache_worker.gc_tts_cache({})
    assert result["disabled"] is True
    assert result["reason"] == "tts_cache_disabled"


@pytest.mark.asyncio
async def test_gc_tts_cache_returns_disabled_when_gc_toggle_off(monkeypatch):
    monkeypatch.setattr(cache_worker.settings, "tts_cache_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_gc_enabled", False)
    result = await cache_worker.gc_tts_cache({})
    assert result["disabled"] is True
    assert result["reason"] == "gc_disabled"


@pytest.mark.asyncio
async def test_gc_tts_cache_deletes_expired_non_manifest_objects(monkeypatch):
    now = datetime.now(UTC)
    old_obj = "tenant-a/tts-cache/t1/old.wav"
    new_obj = "tenant-a/tts-cache/t1/new.wav"
    manifest = "tenant-a/tts-cache/scenario-cache/manifest.json"

    fake_s3 = _FakeS3Client()
    fake_s3.pages_by_prefix = {
        "": [
            {
                "Contents": [
                    {"Key": old_obj, "Size": 100, "LastModified": now - timedelta(days=45)},
                    {"Key": new_obj, "Size": 100, "LastModified": now - timedelta(days=1)},
                    {"Key": manifest, "Size": 200, "LastModified": now - timedelta(days=45)},
                ]
            }
        ]
    }
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(cache_worker.settings, "tts_cache_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_gc_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_max_age_days", 30)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_tenant_max_gb", 0.0)

    result = await cache_worker.gc_tts_cache({})
    assert result["deleted"] == 1
    assert result["errors"] == 0
    assert result["deleted_by_reason"]["age"] == 1
    assert old_obj in fake_s3.deleted_object_keys
    assert manifest not in fake_s3.deleted_object_keys


@pytest.mark.asyncio
async def test_gc_tts_cache_enforces_tenant_size_ceiling_oldest_first(monkeypatch):
    now = datetime.now(UTC)
    oldest = "tenant-a/tts-cache/t1/oldest.wav"
    newer = "tenant-a/tts-cache/t1/newer.wav"
    manifest = "tenant-a/tts-cache/scenario-cache/manifest.json"

    fake_s3 = _FakeS3Client()
    fake_s3.pages_by_prefix = {
        "": [
            {
                "Contents": [
                    {"Key": oldest, "Size": 100, "LastModified": now - timedelta(days=2)},
                    {"Key": newer, "Size": 100, "LastModified": now - timedelta(days=1)},
                    {"Key": manifest, "Size": 50, "LastModified": now - timedelta(days=1)},
                ]
            }
        ]
    }
    monkeypatch.setattr(
        cache_worker.aioboto3,
        "Session",
        lambda **_kwargs: _FakeS3Session(fake_s3),
    )
    monkeypatch.setattr(cache_worker.settings, "tts_cache_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_gc_enabled", True)
    monkeypatch.setattr(cache_worker.settings, "tts_cache_max_age_days", 365)
    monkeypatch.setattr(
        cache_worker.settings,
        "tts_cache_tenant_max_gb",
        150.0 / (1024 * 1024 * 1024),  # limit to 150 bytes
    )

    result = await cache_worker.gc_tts_cache({})
    assert result["deleted"] == 1
    assert result["errors"] == 0
    assert result["deleted_by_reason"]["ceiling"] == 1
    assert fake_s3.deleted_object_keys[0] == oldest
    assert manifest not in fake_s3.deleted_object_keys
