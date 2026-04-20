"""Tests for Phase 7 harness read-through TTS cache."""

import asyncio
import io
import os
import wave
from typing import Any

import pytest
from botocore.exceptions import ClientError
from botcheck_scenarios import BotConfig, ScenarioDefinition, ScenarioType, Turn

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

from src import agent  # noqa: E402
from src.config import settings  # noqa: E402
from src.scenario_kind import AI_RUNTIME_TAG  # noqa: E402


class _Counter:
    def __init__(self) -> None:
        self.value = 0
        self.by_scenario_kind: dict[str, int] = {}

    def inc(self, amount: float = 1.0) -> None:
        self.value += int(amount)

    def labels(self, **kwargs):
        scenario_kind = str(kwargs.get("scenario_kind", "unknown"))
        parent = self

        class _Child:
            def inc(self, amount: float = 1.0) -> None:
                delta = int(amount)
                parent.value += delta
                parent.by_scenario_kind[scenario_kind] = (
                    parent.by_scenario_kind.get(scenario_kind, 0) + delta
                )

        return _Child()


class _LabelCounter(_Counter):
    def __init__(self) -> None:
        super().__init__()
        self.by_reason: dict[str, int] = {}

    def labels(self, **kwargs):
        reason = str(kwargs.get("reason", "unknown"))
        parent = self

        class _Child:
            def inc(self, amount: float = 1.0) -> None:
                delta = int(amount)
                parent.value += delta
                parent.by_reason[reason] = parent.by_reason.get(reason, 0) + delta

        return _Child()


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(
        self,
        *,
        payload: bytes | None = None,
        error: Exception | None = None,
        missing_body: bool = False,
    ) -> None:
        self._payload = payload or b""
        self._error = error
        self._missing_body = missing_body
        self.last_bucket: str | None = None
        self.last_key: str | None = None
        self.get_calls = 0

    async def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        self.get_calls += 1
        self.last_bucket = Bucket
        self.last_key = Key
        if self._error is not None:
            raise self._error
        return {"Body": None if self._missing_body else _FakeBody(self._payload)}


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


def _scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        id="scenario-cache",
        name="Scenario Cache",
        type=ScenarioType.GOLDEN_PATH,
        bot=BotConfig(endpoint="sip:bot@test.example.com"),
        turns=[
            Turn(id="t1", text="Hello there"),
            Turn(id="t2", text="Please confirm your account"),
        ],
    )


def _wav_bytes_from_pcm(
    pcm_bytes: bytes,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return bio.getvalue()


@pytest.mark.asyncio
async def test_read_cached_turn_wav_hit(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]
    fake_s3 = _FakeS3Client(payload=b"wav-bytes")

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))

    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")
    monkeypatch.setattr(settings, "s3_bucket_prefix", "botcheck-artifacts")

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav == b"wav-bytes"
    assert hit.value == 1
    assert hit.by_scenario_kind == {"graph": 1}
    assert miss.value == 0
    assert fallback.value == 0
    assert fake_s3.last_bucket == "botcheck-artifacts"
    assert fake_s3.last_key == scenario.turn_cache_key(
        turn, "tenant-a", pcm_format_version=settings.tts_cache_pcm_format_version
    )


@pytest.mark.asyncio
async def test_read_cached_turn_wav_miss(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]
    fake_s3 = _FakeS3Client(
        error=ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    )

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))

    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav is None
    assert hit.value == 0
    assert miss.value == 1
    assert miss.by_scenario_kind == {"graph": 1}
    assert fallback.value == 0


@pytest.mark.asyncio
async def test_read_cached_turn_wav_hit_records_ai_scenario_kind_label(monkeypatch):
    scenario = _scenario().model_copy(update={"tags": [AI_RUNTIME_TAG]}, deep=True)
    turn = scenario.turns[0]
    fake_s3 = _FakeS3Client(payload=b"wav-bytes")

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))

    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )

    assert wav == b"wav-bytes"
    assert hit.value == 1
    assert hit.by_scenario_kind == {"ai": 1}
    assert miss.value == 0
    assert fallback.value == 0


@pytest.mark.asyncio
async def test_read_cached_turn_wav_fallback_on_s3_error(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]
    fake_s3 = _FakeS3Client(
        error=ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
    )

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))

    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav is None
    assert hit.value == 0
    assert miss.value == 0
    assert fallback.value == 1
    assert fallback.by_reason.get("s3_error") == 1


@pytest.mark.asyncio
async def test_read_cached_turn_wav_fallback_on_missing_body(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]
    fake_s3 = _FakeS3Client(missing_body=True)

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))

    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav is None
    assert hit.value == 0
    assert miss.value == 0
    assert fallback.value == 1
    assert fallback.by_reason.get("missing_body") == 1


@pytest.mark.asyncio
async def test_read_cached_turn_wav_disabled(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)
    monkeypatch.setattr(settings, "tts_cache_enabled", False)

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav is None
    assert hit.value == 0
    assert miss.value == 0
    assert fallback.value == 0


@pytest.mark.asyncio
async def test_read_cached_turn_wav_enabled_but_missing_s3_credentials(monkeypatch):
    scenario = _scenario()
    turn = scenario.turns[0]

    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()
    monkeypatch.setattr(agent, "TTS_CACHE_HITS_TOTAL", hit)
    monkeypatch.setattr(agent, "TTS_CACHE_MISSES_TOTAL", miss)
    monkeypatch.setattr(agent, "TTS_CACHE_FALLBACK_TOTAL", fallback)

    called = {"session": False}

    def _unexpected_session(**_kwargs):
        called["session"] = True
        raise AssertionError("aioboto3.Session should not be used without credentials")

    monkeypatch.setattr(agent.aioboto3, "Session", _unexpected_session)
    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", None)
    monkeypatch.setattr(settings, "s3_secret_key", None)

    wav = await agent._read_cached_turn_wav(
        scenario=scenario,
        turn=turn,
        tenant_id="tenant-a",
    )
    assert wav is None
    assert called["session"] is False
    assert hit.value == 0
    assert miss.value == 0
    assert fallback.value == 0


class _FakeAudioSource:
    def __init__(self) -> None:
        self.frames: list[Any] = []

    async def capture_frame(self, frame: Any) -> None:
        self.frames.append(frame)


@pytest.mark.asyncio
async def test_publish_cached_wav_emits_audio_frames():
    pcm = b"\x00\x00" * 2400  # 0.1s at 24kHz mono 16-bit
    wav_bytes = _wav_bytes_from_pcm(pcm)
    source = _FakeAudioSource()

    await agent._publish_cached_wav(source, wav_bytes)
    assert len(source.frames) >= 1
    assert all(getattr(frame, "sample_rate", 0) == 24000 for frame in source.frames)


@pytest.mark.asyncio
async def test_turn_audio_cache_prefetcher_prefetches_without_recording_until_consumed(
    monkeypatch,
):
    scenario = _scenario()
    fake_s3 = _FakeS3Client(payload=b"prefetched-wav")
    hit = _Counter()
    miss = _Counter()
    fallback = _LabelCounter()

    monkeypatch.setattr(agent.aioboto3, "Session", lambda **_kwargs: _FakeS3Session(fake_s3))
    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")

    prefetcher = agent._cache_surface.TurnAudioCachePrefetcher(
        scenario=scenario,
        tenant_id="tenant-a",
        settings_obj=settings,
        hits_total=hit,
        misses_total=miss,
        fallback_total=fallback,
        max_concurrency=2,
    )
    prefetcher.start()

    await asyncio.sleep(0)
    assert fake_s3.get_calls == 2
    assert hit.value == 0
    assert miss.value == 0
    assert fallback.value == 0

    wav = await prefetcher.get(turn=scenario.turns[0])
    assert wav == b"prefetched-wav"
    assert hit.value == 1
    assert hit.by_scenario_kind == {"graph": 1}
    assert miss.value == 0
    assert fallback.value == 0
    assert fake_s3.get_calls == 2

    wav_again = await prefetcher.get(turn=scenario.turns[0])
    assert wav_again == b"prefetched-wav"
    assert hit.value == 2
    assert hit.by_scenario_kind == {"graph": 2}
    assert fake_s3.get_calls == 2


@pytest.mark.asyncio
async def test_build_prefetched_read_cached_turn_wav_starts_prefetcher(monkeypatch):
    scenario = _scenario()
    started = {"value": False}

    class _FakePrefetcher:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            started["value"] = True

        async def get(self, *, turn: Turn) -> bytes | None:
            return f"prefetched:{turn.id}".encode()

        def cancel(self) -> None:
            return None

    monkeypatch.setattr(settings, "tts_cache_prefetch_enabled", True)
    monkeypatch.setattr(settings, "tts_cache_enabled", True)
    monkeypatch.setattr(settings, "s3_access_key", "test")
    monkeypatch.setattr(settings, "s3_secret_key", "test")
    monkeypatch.setattr(
        agent._cache_surface,
        "TurnAudioCachePrefetcher",
        _FakePrefetcher,
    )

    read_fn, prefetcher = agent._build_prefetched_read_cached_turn_wav(
        scenario=scenario,
        tenant_id="tenant-a",
        run_metadata=None,
    )

    assert started["value"] is True
    assert prefetcher is not None
    wav = await read_fn(
        scenario=scenario,
        turn=scenario.turns[0],
        tenant_id="tenant-a",
    )
    assert wav == b"prefetched:t1"
