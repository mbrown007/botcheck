"""Shared speech provider capability models and catalog helpers."""

from __future__ import annotations

import io
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from contextlib import AbstractAsyncContextManager
from typing import Any, AsyncIterator, Callable, Generic, Literal, Protocol, TypeVar
import wave

import httpx
from pydantic import BaseModel, Field

SpeechVoiceMode = Literal["static_select", "freeform_id"]
DEFAULT_TTS_PROVIDER = "openai"
DEFAULT_STT_PROVIDER = "deepgram"
TRegistryValue = TypeVar("TRegistryValue")


@dataclass(frozen=True)
class ParsedTTSVoice:
    provider: str
    voice: str

    @property
    def canonical(self) -> str:
        return f"{self.provider}:{self.voice}"


@dataclass(frozen=True)
class ParsedSTTConfig:
    provider: str
    model: str


class TTSProviderResolutionError(ValueError):
    """Base class for TTS provider resolution failures."""


class TTSProviderDisabledError(TTSProviderResolutionError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"TTS provider is disabled: {provider}")
        self.provider = provider


class TTSProviderUnsupportedError(TTSProviderResolutionError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"TTS provider is unsupported: {provider}")
        self.provider = provider


class STTProviderResolutionError(ValueError):
    """Base class for STT provider resolution failures."""


class STTProviderDisabledError(STTProviderResolutionError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"STT provider is disabled: {provider}")
        self.provider = provider


class STTProviderUnsupportedError(STTProviderResolutionError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"STT provider is unsupported: {provider}")
        self.provider = provider


class LiveTTSAdapter(Protocol):
    provider_id: str
    model_label: str

    def synthesize(self, text: str, *, conn_options: Any):
        """Return the provider-specific live synthesis stream/context manager."""


class TTSProvider(Protocol):
    provider_id: str
    voice_id: str
    model_label: str

    async def synthesize_wav(
        self,
        *,
        text: str,
        timeout_s: float,
        response_format: str = "wav",
    ) -> bytes: ...

    def create_live_tts(
        self,
        *,
        openai_module: Any | None = None,
        rtc_module: Any | None = None,
    ) -> LiveTTSAdapter: ...


class STTProvider(Protocol):
    provider_id: str
    model_label: str

    def create_stt(
        self,
        *,
        plugin_module: Any | None = None,
        endpointing_ms: int | None = None,
    ) -> Any: ...


class SpeechProviderCapability(BaseModel):
    id: str
    label: str
    enabled: bool
    voice_mode: SpeechVoiceMode
    supports_preview: bool
    supports_cache_warm: bool
    supports_live_synthesis: bool
    supports_live_stream: bool


class SpeechCapabilities(BaseModel):
    tts: list[SpeechProviderCapability] = Field(default_factory=list)
    stt: list[SpeechProviderCapability] = Field(default_factory=list)


class ProviderKeyedRegistry(Generic[TRegistryValue]):
    def __init__(self, factory: Callable[[str], TRegistryValue]) -> None:
        self._factory = factory
        self._values: dict[str, TRegistryValue] = {}

    def get(self, provider: str) -> TRegistryValue:
        key = provider.strip().lower()
        if not key:
            raise ValueError("provider is required")
        value = self._values.get(key)
        if value is None:
            value = self._factory(key)
            self._values[key] = value
        return value

    def reset(self, provider: str | None = None) -> None:
        if provider is None:
            values = list(self._values.values())
            self._values.clear()
        else:
            key = provider.strip().lower()
            if not key:
                raise ValueError("provider is required")
            value = self._values.pop(key, None)
            values = [] if value is None else [value]

        for value in values:
            reset = getattr(value, "reset", None)
            if callable(reset):
                reset()


class _OpenAILiveTTSAdapter:
    def __init__(self, *, voice_id: str, model_label: str, openai_module: Any) -> None:
        self.provider_id = "openai"
        self.model_label = model_label
        self._tts = openai_module.TTS(voice=voice_id)

    def synthesize(self, text: str, *, conn_options: Any):
        return self._tts.synthesize(text, conn_options=conn_options)



def _pcm_chunk_to_audio_frame(
    pcm_bytes: bytes,
    *,
    rtc_module: Any,
    sample_rate_hz: int,
    channels: int = 1,
    sample_width: int = 2,
) -> Any | None:
    bytes_per_sample = sample_width * channels
    samples_per_channel = len(pcm_bytes) // bytes_per_sample
    if samples_per_channel <= 0:
        return None
    return rtc_module.AudioFrame(
        data=pcm_bytes,
        sample_rate=sample_rate_hz,
        num_channels=channels,
        samples_per_channel=samples_per_channel,
    )


def _parse_pcm_output_format_sample_rate(output_format: str) -> int:
    normalized = str(output_format or "").strip().lower()
    if not normalized.startswith("pcm_"):
        raise ValueError("ElevenLabs output_format must use pcm_* in this slice")
    sample_rate = normalized.removeprefix("pcm_")
    if not sample_rate.isdigit():
        raise ValueError("ElevenLabs pcm output_format must include a numeric sample rate")
    value = int(sample_rate)
    if value <= 0:
        raise ValueError("ElevenLabs pcm output_format sample rate must be positive")
    return value


def _pcm_to_wav_bytes(
    pcm_bytes: bytes,
    *,
    sample_rate_hz: int,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(pcm_bytes)
    return bio.getvalue()


def _pcm_to_audio_frames(
    pcm_bytes: bytes,
    *,
    rtc_module: Any,
    sample_rate_hz: int,
    channels: int = 1,
    sample_width: int = 2,
    frame_ms: int = 20,
) -> list[Any]:
    bytes_per_sample = sample_width * channels
    frame_samples = max(1, int(sample_rate_hz * (frame_ms / 1000)))
    frame_size = frame_samples * bytes_per_sample
    frames: list[Any] = []

    for idx in range(0, len(pcm_bytes), frame_size):
        chunk = pcm_bytes[idx : idx + frame_size]
        frame = _pcm_chunk_to_audio_frame(
            chunk,
            rtc_module=rtc_module,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            sample_width=sample_width,
        )
        if frame is not None:
            frames.append(frame)

    return frames


class _StreamingPCMToAudioFrameStream:
    def __init__(
        self,
        *,
        open_byte_stream: Callable[[], Any],
        rtc_module: Any,
        sample_rate_hz: int,
        channels: int = 1,
        sample_width: int = 2,
        frame_ms: int = 20,
    ) -> None:
        self._open_byte_stream = open_byte_stream
        self._rtc_module = rtc_module
        self._sample_rate_hz = sample_rate_hz
        self._channels = channels
        self._sample_width = sample_width
        bytes_per_sample = sample_width * channels
        frame_samples = max(1, int(sample_rate_hz * (frame_ms / 1000)))
        self._frame_size = frame_samples * bytes_per_sample
        self._byte_stream_cm = None
        self._byte_iter = None
        self._pending = bytearray()
        self._stream_finished = False

    async def __aenter__(self) -> _StreamingPCMToAudioFrameStream:
        self._byte_stream_cm = self._open_byte_stream()
        byte_stream = await self._byte_stream_cm.__aenter__()
        self._byte_iter = byte_stream.__aiter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Clear internal state before propagating to the upstream CM so that any
        # re-entrant or follow-on __anext__ call sees a terminated iterator rather
        # than a partially-consumed one, and so that a secondary exception raised
        # during aclose() does not hide the original exc in the traceback.
        cm = self._byte_stream_cm
        self._byte_stream_cm = None
        self._byte_iter = None
        self._pending.clear()
        self._stream_finished = True
        if cm is not None:
            await cm.__aexit__(exc_type, exc, tb)
        return None

    def __aiter__(self) -> _StreamingPCMToAudioFrameStream:
        return self

    def _pop_frame(self, *, allow_partial: bool) -> Any | None:
        if len(self._pending) < self._frame_size and not allow_partial:
            return None
        if not self._pending:
            return None
        frame_bytes = bytes(self._pending[: self._frame_size])
        del self._pending[: self._frame_size]
        return _pcm_chunk_to_audio_frame(
            frame_bytes,
            rtc_module=self._rtc_module,
            sample_rate_hz=self._sample_rate_hz,
            channels=self._channels,
            sample_width=self._sample_width,
        )

    async def __anext__(self):
        while True:
            frame = self._pop_frame(allow_partial=self._stream_finished)
            if frame is not None:
                return SimpleNamespace(frame=frame)
            if self._stream_finished or self._byte_iter is None:
                raise StopAsyncIteration
            try:
                chunk = await self._byte_iter.__anext__()
            except StopAsyncIteration:
                self._stream_finished = True
                continue
            if chunk:
                self._pending.extend(chunk)


class _ElevenLabsLiveTTSAdapter:
    def __init__(self, *, provider: ElevenLabsTTSProvider, rtc_module: Any) -> None:
        self.provider_id = provider.provider_id
        self.model_label = provider.model_label
        self._provider = provider
        self._rtc_module = rtc_module

    def synthesize(self, text: str, *, conn_options: Any):
        timeout_s = float(getattr(conn_options, "timeout", 30.0) or 30.0)
        return _StreamingPCMToAudioFrameStream(
            open_byte_stream=lambda: self._provider.stream_pcm(
                text=text,
                timeout_s=timeout_s,
            ),
            rtc_module=self._rtc_module,
            sample_rate_hz=self._provider.sample_rate_hz,
        )


class OpenAITTSProvider:
    provider_id = "openai"

    def __init__(
        self,
        *,
        voice_id: str,
        model_label: str,
        api_key: str | None = None,
    ) -> None:
        self.voice_id = voice_id
        self.model_label = model_label
        self._api_key = (api_key or "").strip()

    async def synthesize_wav(
        self,
        *,
        text: str,
        timeout_s: float,
        response_format: str = "wav",
    ) -> bytes:
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI TTS")

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_label,
                    "voice": self.voice_id,
                    "input": text,
                    "response_format": response_format,
                },
            )
            resp.raise_for_status()
            return resp.content

    def create_live_tts(
        self,
        *,
        openai_module: Any | None = None,
        rtc_module: Any | None = None,
    ) -> LiveTTSAdapter:
        del rtc_module
        if openai_module is None:
            raise ValueError("openai_module is required for OpenAI live TTS")
        return _OpenAILiveTTSAdapter(
            voice_id=self.voice_id,
            model_label=self.model_label,
            openai_module=openai_module,
        )


class ElevenLabsTTSProvider:
    provider_id = "elevenlabs"

    def __init__(
        self,
        *,
        voice_id: str,
        model_label: str,
        api_key: str | None = None,
        output_format: str = "pcm_24000",
    ) -> None:
        self.voice_id = voice_id
        self.model_label = model_label
        self.output_format = str(output_format or "").strip() or "pcm_24000"
        self.sample_rate_hz = _parse_pcm_output_format_sample_rate(self.output_format)
        self._api_key = (api_key or "").strip()

    async def synthesize_pcm(
        self,
        *,
        text: str,
        timeout_s: float,
    ) -> bytes:
        if not self._api_key:
            raise ValueError("ELEVENLABS_API_KEY is required for ElevenLabs TTS")

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                headers={
                    "xi-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                params={"output_format": self.output_format},
                json={
                    "text": text,
                    "model_id": self.model_label,
                },
            )
            resp.raise_for_status()
            return resp.content

    @asynccontextmanager
    async def stream_pcm(
        self,
        *,
        text: str,
        timeout_s: float,
    ) -> AbstractAsyncContextManager[AsyncIterator[bytes]]:
        if not self._api_key:
            raise ValueError("ELEVENLABS_API_KEY is required for ElevenLabs TTS")

        # Use a connect/write timeout but no read deadline: the read timeout covers the
        # gap between individual chunks, and TTS streaming keeps the connection open for
        # the full synthesis duration which can exceed any fixed per-read timeout.
        timeout = httpx.Timeout(timeout_s, read=None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream",
                headers={
                    "xi-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                params={"output_format": self.output_format},
                json={
                    "text": text,
                    "model_id": self.model_label,
                },
            ) as resp:
                if resp.is_error:
                    await resp.aread()  # drain body so error detail appears in the exception
                resp.raise_for_status()
                yield resp.aiter_bytes()

    async def synthesize_wav(
        self,
        *,
        text: str,
        timeout_s: float,
        response_format: str = "wav",
    ) -> bytes:
        normalized_format = str(response_format or "").strip().lower() or "wav"
        if normalized_format != "wav":
            raise ValueError("ElevenLabs TTS provider only supports wav output in this slice")
        pcm = await self.synthesize_pcm(text=text, timeout_s=timeout_s)
        return _pcm_to_wav_bytes(
            pcm,
            sample_rate_hz=self.sample_rate_hz,
        )

    def create_live_tts(
        self,
        *,
        openai_module: Any | None = None,
        rtc_module: Any | None = None,
    ) -> LiveTTSAdapter:
        del openai_module
        if rtc_module is None:
            raise ValueError("rtc_module is required for ElevenLabs live TTS")
        return _ElevenLabsLiveTTSAdapter(provider=self, rtc_module=rtc_module)


class DeepgramSTTProvider:
    provider_id = "deepgram"

    def __init__(
        self,
        *,
        model: str,
        language: str = "en-US",
        api_key: str | None = None,
    ) -> None:
        self.model_label = str(model or "").strip()
        self.language = str(language or "").strip() or "en-US"
        self._api_key = (api_key or "").strip()

    def create_stt(
        self,
        *,
        plugin_module: Any | None = None,
        endpointing_ms: int | None = None,
    ) -> Any:
        if plugin_module is None:
            raise ValueError("plugin_module is required for Deepgram STT")
        kwargs: dict[str, Any] = {
            "language": self.language,
            "model": self.model_label,
        }
        if endpointing_ms is not None:
            kwargs["endpointing_ms"] = endpointing_ms
        if self._api_key:
            kwargs["api_key"] = self._api_key
        return plugin_module.STT(**kwargs)


class AzureSTTProvider:
    provider_id = "azure"

    def __init__(
        self,
        *,
        model: str,
        language: str = "en-US",
        speech_key: str | None = None,
        speech_region: str | None = None,
        speech_endpoint: str | None = None,
    ) -> None:
        # The LiveKit Azure STT plugin does not expose a model selector; keep the
        # scenario-configured value as the canonical telemetry/display label.
        self.model_label = str(model or "").strip()
        self.language = str(language or "").strip() or "en-US"
        self._speech_key = (speech_key or "").strip()
        self._speech_region = (speech_region or "").strip()
        self._speech_endpoint = (speech_endpoint or "").strip()

    def create_stt(
        self,
        *,
        plugin_module: Any | None = None,
        endpointing_ms: int | None = None,
    ) -> Any:
        if plugin_module is None:
            raise ValueError("plugin_module is required for Azure STT")
        kwargs: dict[str, Any] = {
            "language": self.language,
        }
        if self._speech_key:
            kwargs["speech_key"] = self._speech_key
        if self._speech_region:
            kwargs["speech_region"] = self._speech_region
        if self._speech_endpoint:
            kwargs["speech_endpoint"] = self._speech_endpoint
        if endpointing_ms is not None:
            kwargs["segmentation_silence_timeout_ms"] = endpointing_ms
        return plugin_module.STT(**kwargs)


def parse_tts_voice(voice: str) -> ParsedTTSVoice:
    raw = str(voice or "").strip()
    if not raw:
        raise ValueError("tts_voice must not be empty")
    if ":" not in raw:
        return ParsedTTSVoice(provider=DEFAULT_TTS_PROVIDER, voice=raw)
    provider, selected_voice = raw.split(":", 1)
    normalized_provider = provider.strip().lower() or DEFAULT_TTS_PROVIDER
    normalized_voice = selected_voice.strip()
    if not normalized_voice:
        raise ValueError("tts_voice must include a voice after the provider prefix")
    return ParsedTTSVoice(provider=normalized_provider, voice=normalized_voice)


def parse_stt_config(stt_provider: str, stt_model: str) -> ParsedSTTConfig:
    normalized_provider = str(stt_provider or "").strip().lower() or DEFAULT_STT_PROVIDER
    normalized_model = str(stt_model or "").strip()
    if not normalized_model:
        raise ValueError("stt_model must not be empty")
    return ParsedSTTConfig(provider=normalized_provider, model=normalized_model)


def tts_provider_enabled(
    provider: str,
    *,
    feature_tts_provider_openai_enabled: bool,
    feature_tts_provider_elevenlabs_enabled: bool,
) -> bool:
    normalized = provider.strip().lower()
    if normalized == "openai":
        return feature_tts_provider_openai_enabled
    if normalized == "elevenlabs":
        return feature_tts_provider_elevenlabs_enabled
    return False


def stt_provider_enabled(
    provider: str,
    *,
    feature_stt_provider_deepgram_enabled: bool,
    feature_stt_provider_azure_enabled: bool = False,
) -> bool:
    normalized = provider.strip().lower()
    if normalized == "deepgram":
        return feature_stt_provider_deepgram_enabled
    if normalized == "azure":
        return feature_stt_provider_azure_enabled
    return False


def build_stt_provider(
    provider: str,
    *,
    model: str,
    language: str = "en-US",
    deepgram_api_key: str | None = None,
    azure_speech_key: str | None = None,
    azure_speech_region: str | None = None,
    azure_speech_endpoint: str | None = None,
) -> STTProvider:
    parsed = parse_stt_config(provider, model)
    if parsed.provider == "deepgram":
        return DeepgramSTTProvider(
            model=parsed.model,
            language=language,
            api_key=deepgram_api_key,
        )
    if parsed.provider == "azure":
        return AzureSTTProvider(
            model=parsed.model,
            language=language,
            speech_key=azure_speech_key,
            speech_region=azure_speech_region,
            speech_endpoint=azure_speech_endpoint,
        )
    raise STTProviderUnsupportedError(parsed.provider)


def _tts_capability_catalog() -> tuple[SpeechProviderCapability, ...]:
    return (
        SpeechProviderCapability(
            id="openai",
            label="OpenAI",
            enabled=False,
            voice_mode="static_select",
            supports_preview=True,
            supports_cache_warm=True,
            supports_live_synthesis=True,
            supports_live_stream=True,
        ),
        SpeechProviderCapability(
            id="elevenlabs",
            label="ElevenLabs",
            enabled=False,
            voice_mode="freeform_id",
            supports_preview=True,
            supports_cache_warm=True,
            supports_live_synthesis=True,
            supports_live_stream=True,
        ),
    )


def _stt_capability_catalog() -> tuple[SpeechProviderCapability, ...]:
    return (
        SpeechProviderCapability(
            id="deepgram",
            label="Deepgram",
            enabled=True,
            voice_mode="freeform_id",
            supports_preview=False,
            supports_cache_warm=False,
            supports_live_synthesis=False,
            supports_live_stream=True,
        ),
        SpeechProviderCapability(
            id="azure",
            label="Azure Speech",
            enabled=False,
            voice_mode="freeform_id",
            supports_preview=False,
            supports_cache_warm=False,
            supports_live_synthesis=False,
            supports_live_stream=True,
        ),
    )


def build_speech_capabilities(
    *,
    feature_tts_provider_openai_enabled: bool,
    feature_tts_provider_elevenlabs_enabled: bool,
    feature_stt_provider_deepgram_enabled: bool = True,
    feature_stt_provider_azure_enabled: bool = False,
) -> SpeechCapabilities:
    feature_flags = {
        "openai": feature_tts_provider_openai_enabled,
        "elevenlabs": feature_tts_provider_elevenlabs_enabled,
    }

    tts_capabilities = [
        capability.model_copy(update={"enabled": feature_flags[capability.id]})
        for capability in _tts_capability_catalog()
    ]

    return SpeechCapabilities(
        tts=tts_capabilities,
        stt=[
            capability.model_copy(
                update={
                    "enabled": stt_provider_enabled(
                        capability.id,
                        feature_stt_provider_deepgram_enabled=feature_stt_provider_deepgram_enabled,
                        feature_stt_provider_azure_enabled=feature_stt_provider_azure_enabled,
                    )
                }
            )
            for capability in _stt_capability_catalog()
        ],
    )
