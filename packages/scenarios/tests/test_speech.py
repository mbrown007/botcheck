import io
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import wave

import pytest

from botcheck_scenarios import (
    AzureSTTProvider,
    DEFAULT_STT_PROVIDER,
    DEFAULT_TTS_PROVIDER,
    DeepgramSTTProvider,
    ElevenLabsTTSProvider,
    ProviderKeyedRegistry,
    build_stt_provider,
    build_speech_capabilities,
    parse_stt_config,
    parse_tts_voice,
    stt_provider_enabled,
    tts_provider_enabled,
)
from botcheck_scenarios.speech import _pcm_to_audio_frames


def test_catalog_always_contains_all_providers() -> None:
    """Both providers appear in the list regardless of flag state; UI hides on enabled=False."""
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=False,
        feature_tts_provider_elevenlabs_enabled=False,
    )
    assert [p.id for p in capabilities.tts] == ["openai", "elevenlabs"]


def test_openai_enabled_by_flag() -> None:
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=True,
        feature_tts_provider_elevenlabs_enabled=False,
    )
    openai = next(p for p in capabilities.tts if p.id == "openai")
    elevenlabs = next(p for p in capabilities.tts if p.id == "elevenlabs")
    assert openai.enabled is True
    assert elevenlabs.enabled is False


def test_elevenlabs_enabled_by_flag() -> None:
    """ElevenLabs must become enabled when its flag is on — not silently blocked by supports_*."""
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=False,
        feature_tts_provider_elevenlabs_enabled=True,
    )
    elevenlabs = next(p for p in capabilities.tts if p.id == "elevenlabs")
    assert elevenlabs.enabled is True


def test_both_flags_off_disables_both_providers() -> None:
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=False,
        feature_tts_provider_elevenlabs_enabled=False,
    )
    assert all(not p.enabled for p in capabilities.tts)


def test_stt_list_contains_deepgram_and_azure() -> None:
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=True,
        feature_tts_provider_elevenlabs_enabled=True,
    )
    assert [provider.id for provider in capabilities.stt] == ["deepgram", "azure"]
    deepgram = capabilities.stt[0]
    azure = capabilities.stt[1]
    assert deepgram.enabled is True
    assert deepgram.voice_mode == "freeform_id"
    assert deepgram.supports_preview is False
    assert deepgram.supports_cache_warm is False
    assert deepgram.supports_live_synthesis is False
    assert deepgram.supports_live_stream is True
    assert azure.enabled is False
    assert azure.voice_mode == "freeform_id"
    assert azure.supports_preview is False
    assert azure.supports_cache_warm is False
    assert azure.supports_live_synthesis is False
    assert azure.supports_live_stream is True


def test_deepgram_stt_enabled_by_flag() -> None:
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=True,
        feature_tts_provider_elevenlabs_enabled=True,
        feature_stt_provider_deepgram_enabled=False,
    )
    assert capabilities.stt[0].enabled is False


def test_azure_stt_enabled_by_flag() -> None:
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=True,
        feature_tts_provider_elevenlabs_enabled=True,
        feature_stt_provider_azure_enabled=True,
    )
    azure = next(provider for provider in capabilities.stt if provider.id == "azure")
    assert azure.enabled is True


def test_static_capability_fields_are_stable() -> None:
    """Capability metadata (voice_mode, supports_*) is independent of feature flags."""
    capabilities = build_speech_capabilities(
        feature_tts_provider_openai_enabled=False,
        feature_tts_provider_elevenlabs_enabled=False,
    )
    openai = next(p for p in capabilities.tts if p.id == "openai")
    elevenlabs = next(p for p in capabilities.tts if p.id == "elevenlabs")

    assert openai.voice_mode == "static_select"
    assert openai.supports_preview is True
    assert openai.supports_cache_warm is True
    assert openai.supports_live_synthesis is True
    assert openai.supports_live_stream is True

    assert elevenlabs.voice_mode == "freeform_id"
    assert elevenlabs.supports_preview is True
    assert elevenlabs.supports_cache_warm is True
    assert elevenlabs.supports_live_synthesis is True
    assert elevenlabs.supports_live_stream is True


def test_parse_tts_voice_defaults_provider_for_legacy_values() -> None:
    parsed = parse_tts_voice("alloy")
    assert parsed.provider == DEFAULT_TTS_PROVIDER
    assert parsed.voice == "alloy"
    assert parsed.canonical == "openai:alloy"


def test_parse_tts_voice_normalizes_provider_and_voice() -> None:
    parsed = parse_tts_voice(" OpenAI : nova ")
    assert parsed.provider == "openai"
    assert parsed.voice == "nova"


def test_parse_tts_voice_rejects_missing_voice_segment() -> None:
    with pytest.raises(ValueError, match="voice"):
        parse_tts_voice("openai:   ")


def test_parse_stt_config_defaults_provider_and_normalizes_model() -> None:
    parsed = parse_stt_config("  ", " nova-2-phonecall ")
    assert parsed.provider == DEFAULT_STT_PROVIDER
    assert parsed.model == "nova-2-phonecall"


def test_parse_stt_config_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="stt_model"):
        parse_stt_config("deepgram", "   ")


def test_tts_provider_enabled_maps_flags_by_provider() -> None:
    assert (
        tts_provider_enabled(
            "openai",
            feature_tts_provider_openai_enabled=True,
            feature_tts_provider_elevenlabs_enabled=False,
        )
        is True
    )
    assert (
        tts_provider_enabled(
            "elevenlabs",
            feature_tts_provider_openai_enabled=True,
            feature_tts_provider_elevenlabs_enabled=False,
    )
        is False
    )


def test_stt_provider_enabled_maps_flags_by_provider() -> None:
    assert (
        stt_provider_enabled(
            "deepgram",
            feature_stt_provider_deepgram_enabled=True,
            feature_stt_provider_azure_enabled=False,
        )
        is True
    )
    assert (
        stt_provider_enabled(
            "azure",
            feature_stt_provider_deepgram_enabled=True,
            feature_stt_provider_azure_enabled=True,
        )
        is True
    )
    assert (
        stt_provider_enabled(
            "unknown",
            feature_stt_provider_deepgram_enabled=True,
            feature_stt_provider_azure_enabled=True,
        )
        is False
    )


def test_build_stt_provider_returns_deepgram_provider() -> None:
    provider = build_stt_provider(
        "Deepgram",
        model="nova-2-general",
        language="en-GB",
        deepgram_api_key="test-deepgram",
    )

    assert isinstance(provider, DeepgramSTTProvider)
    assert provider.provider_id == "deepgram"
    assert provider.model_label == "nova-2-general"
    assert provider.language == "en-GB"


def test_build_stt_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        build_stt_provider("whisper", model="whisper-large")


def test_build_stt_provider_returns_azure_provider() -> None:
    provider = build_stt_provider(
        "Azure",
        model="azure-default",
        language="en-GB",
        azure_speech_key="test-azure-key",
        azure_speech_region="uksouth",
        azure_speech_endpoint="https://azure.example.test",
    )

    assert isinstance(provider, AzureSTTProvider)
    assert provider.provider_id == "azure"
    assert provider.model_label == "azure-default"
    assert provider.language == "en-GB"


def test_azure_provider_create_stt_passes_expected_kwargs() -> None:
    captured: dict[str, object] = {}

    class _AzureModule:
        @staticmethod
        def STT(**kwargs):
            captured.update(kwargs)
            return kwargs

    provider = AzureSTTProvider(
        model="azure-default",
        language="en-GB",
        speech_key="test-azure-key",
        speech_region="uksouth",
        speech_endpoint="https://azure.example.test",
    )

    stt = provider.create_stt(
        plugin_module=_AzureModule,
        endpointing_ms=500,
    )

    assert stt["language"] == "en-GB"
    assert stt["speech_key"] == "test-azure-key"
    assert stt["speech_region"] == "uksouth"
    assert stt["speech_endpoint"] == "https://azure.example.test"
    assert stt["segmentation_silence_timeout_ms"] == 500


def test_provider_keyed_registry_is_lazy_and_reuses_instances() -> None:
    created: list[str] = []

    class _FakeResettable:
        def __init__(self, provider: str) -> None:
            self.provider = provider
            self.reset_calls = 0

        def reset(self) -> None:
            self.reset_calls += 1

    registry = ProviderKeyedRegistry(lambda provider: created.append(provider) or _FakeResettable(provider))

    first = registry.get("openai")
    second = registry.get(" OpenAI ")
    registry.reset("openai")

    assert created == ["openai"]
    assert first is second
    assert first.reset_calls == 1


def test_pcm_to_audio_frames_drops_sub_byte_input() -> None:
    class _RTC:
        class AudioFrame:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

    frames = _pcm_to_audio_frames(
        b"\x00",
        rtc_module=_RTC(),
        sample_rate_hz=24000,
    )

    assert frames == []


@pytest.mark.asyncio
async def test_elevenlabs_synthesize_wav_wraps_pcm_response(monkeypatch) -> None:
    captured: dict[str, object] = {}
    pcm_bytes = b"\x01\x02\x03\x04" * 8

    class _FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers, params, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            captured["json"] = json
            return _FakeResponse(pcm_bytes)

    monkeypatch.setattr("botcheck_scenarios.speech.httpx.AsyncClient", _FakeClient)

    provider = ElevenLabsTTSProvider(
        voice_id="voice-123",
        model_label="eleven_flash_v2_5",
        api_key="test-elevenlabs",
        output_format="pcm_24000",
    )
    wav_bytes = await provider.synthesize_wav(text="Hello", timeout_s=4.0)

    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice-123"
    assert captured["headers"] == {
        "xi-api-key": "test-elevenlabs",
        "Content-Type": "application/json",
    }
    assert captured["params"] == {"output_format": "pcm_24000"}
    assert captured["json"] == {"text": "Hello", "model_id": "eleven_flash_v2_5"}

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.readframes(wav_file.getnframes()) == pcm_bytes


@pytest.mark.asyncio
async def test_elevenlabs_stream_pcm_uses_stream_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        is_error = False

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"\x01\x02"
            yield b"\x03\x04"

    class _FakeStreamContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _FakeClient:
        def __init__(self, *, timeout) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, *, headers, params, json):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            captured["json"] = json
            return _FakeStreamContext()

    monkeypatch.setattr("botcheck_scenarios.speech.httpx.AsyncClient", _FakeClient)

    provider = ElevenLabsTTSProvider(
        voice_id="voice-123",
        model_label="eleven_flash_v2_5",
        api_key="test-elevenlabs",
        output_format="pcm_24000",
    )

    async with provider.stream_pcm(text="Hello", timeout_s=4.0) as byte_stream:
        chunks = [chunk async for chunk in byte_stream]

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice-123/stream"
    assert captured["headers"] == {
        "xi-api-key": "test-elevenlabs",
        "Content-Type": "application/json",
    }
    assert captured["params"] == {"output_format": "pcm_24000"}
    assert captured["json"] == {"text": "Hello", "model_id": "eleven_flash_v2_5"}
    assert chunks == [b"\x01\x02", b"\x03\x04"]
    # Timeout must have read=None to avoid cutting off mid-stream responses
    import httpx as _httpx
    assert isinstance(captured["timeout"], _httpx.Timeout)
    assert captured["timeout"].read is None


def test_deepgram_provider_create_stt_passes_expected_kwargs() -> None:
    captured: dict[str, object] = {}

    class _DeepgramModule:
        @staticmethod
        def STT(**kwargs):
            captured.update(kwargs)
            return kwargs

    provider = DeepgramSTTProvider(
        model="nova-2-phonecall",
        language="en-US",
        api_key="test-deepgram-key",
    )

    stt = provider.create_stt(
        plugin_module=_DeepgramModule,
        endpointing_ms=400,
    )

    assert stt["model"] == "nova-2-phonecall"
    assert stt["language"] == "en-US"
    assert stt["endpointing_ms"] == 400
    assert stt["api_key"] == "test-deepgram-key"


@pytest.mark.asyncio
async def test_elevenlabs_live_adapter_streams_pcm_into_audio_frames_progressively(
    monkeypatch,
) -> None:
    class _Frame:
        def __init__(self, **kwargs) -> None:
            self.data = kwargs["data"]
            self.sample_rate = kwargs["sample_rate"]
            self.num_channels = kwargs["num_channels"]
            self.samples_per_channel = kwargs["samples_per_channel"]

    class _RTC:
        AudioFrame = _Frame

    provider = ElevenLabsTTSProvider(
        voice_id="voice-123",
        model_label="eleven_flash_v2_5",
        api_key="test-elevenlabs",
        output_format="pcm_24000",
    )
    consumed_chunks: list[bytes] = []

    @asynccontextmanager
    async def _stream_pcm(*, text: str, timeout_s: float):
        del text, timeout_s

        async def _iter_chunks():
            for chunk in (b"\x00\x00" * 480, b"\x00\x00" * 480):
                consumed_chunks.append(chunk)
                yield chunk

        yield _iter_chunks()

    monkeypatch.setattr(provider, "stream_pcm", _stream_pcm)

    adapter = provider.create_live_tts(rtc_module=_RTC())
    async with adapter.synthesize("Hello", conn_options=SimpleNamespace(timeout=3.0)) as chunked:
        first_event = await chunked.__anext__()
        assert len(consumed_chunks) == 1
        remaining_events = [event async for event in chunked]

    assert adapter.provider_id == "elevenlabs"
    assert adapter.model_label == "eleven_flash_v2_5"
    assert first_event.frame.sample_rate == 24000
    assert first_event.frame.num_channels == 1
    assert first_event.frame.samples_per_channel == 480
    assert len(remaining_events) == 1


@pytest.mark.asyncio
async def test_elevenlabs_live_adapter_emits_single_frame_for_subframe_pcm(monkeypatch) -> None:
    class _Frame:
        def __init__(self, **kwargs) -> None:
            self.data = kwargs["data"]
            self.sample_rate = kwargs["sample_rate"]
            self.num_channels = kwargs["num_channels"]
            self.samples_per_channel = kwargs["samples_per_channel"]

    class _RTC:
        AudioFrame = _Frame

    provider = ElevenLabsTTSProvider(
        voice_id="voice-123",
        model_label="eleven_flash_v2_5",
        api_key="test-elevenlabs",
        output_format="pcm_24000",
    )
    @asynccontextmanager
    async def _stream_pcm(*, text: str, timeout_s: float):
        del text, timeout_s

        async def _iter_chunks():
            yield b"\x00\x00" * 120

        yield _iter_chunks()

    monkeypatch.setattr(provider, "stream_pcm", _stream_pcm)

    adapter = provider.create_live_tts(rtc_module=_RTC())
    async with adapter.synthesize("Hi", conn_options=SimpleNamespace(timeout=3.0)) as chunked:
        events = [event async for event in chunked]

    assert len(events) == 1
    assert events[0].frame.samples_per_channel == 120


@pytest.mark.asyncio
async def test_elevenlabs_live_adapter_reassembles_frames_from_misaligned_chunks(
    monkeypatch,
) -> None:
    """Chunks that do not align to frame boundaries must be reassembled correctly.

    One frame = 480 samples * 2 bytes = 960 bytes at 24 kHz / 20 ms.
    Deliver 3 chunks of 481 bytes each (481 * 3 = 1443 bytes total).
    Expected: 1 full frame (960 bytes) yielded after chunk 2 lands and fills the
    buffer, a second partial frame (483 bytes → 241 samples) flushed at stream end.
    """

    class _Frame:
        def __init__(self, **kwargs) -> None:
            self.samples_per_channel = kwargs["samples_per_channel"]

    class _RTC:
        AudioFrame = _Frame

    provider = ElevenLabsTTSProvider(
        voice_id="voice-123",
        model_label="eleven_flash_v2_5",
        api_key="test-elevenlabs",
        output_format="pcm_24000",
    )
    chunk = b"\x00\x01" * 481  # 962 bytes, not a multiple of 960

    @asynccontextmanager
    async def _stream_pcm(*, text: str, timeout_s: float):
        del text, timeout_s

        async def _iter_chunks():
            yield chunk
            yield chunk
            yield chunk  # total 2886 bytes → 3 full frames (2880 bytes) + 6 bytes remainder

        yield _iter_chunks()

    monkeypatch.setattr(provider, "stream_pcm", _stream_pcm)

    adapter = provider.create_live_tts(rtc_module=_RTC())
    async with adapter.synthesize("Test", conn_options=SimpleNamespace(timeout=3.0)) as chunked:
        events = [event async for event in chunked]

    # 2886 bytes / 960 bytes-per-frame = 3 full frames + 6 remainder bytes (3 samples)
    assert len(events) == 4
    assert events[0].frame.samples_per_channel == 480
    assert events[1].frame.samples_per_channel == 480
    assert events[2].frame.samples_per_channel == 480
    assert events[3].frame.samples_per_channel == 3  # partial flush at stream end
