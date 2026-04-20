"""Tests for harness call recording helpers."""

import os
import wave
from unittest.mock import AsyncMock

os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

from livekit import rtc  # noqa: E402
from src import agent  # noqa: E402
from src.audio import RecordingAudioSource  # noqa: E402
from src.config import settings  # noqa: E402


class _Frame:
    def __init__(self, data: bytes) -> None:
        self.data = data


class _FakeResampler:
    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk

    def push(self, _frame):
        return [_Frame(self._chunk)]


def _make_audio_frame(*, sample_rate: int = 24000, duration_ms: int = 20) -> rtc.AudioFrame:
    """Create a silent rtc.AudioFrame suitable for resampler tests."""
    samples = int(sample_rate * duration_ms / 1000)
    return rtc.AudioFrame(
        data=bytes(samples * 2),
        sample_rate=sample_rate,
        num_channels=1,
        samples_per_channel=samples,
    )


class TestBotAudioRecorder:
    async def test_write_wav_persists_audio(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "recording_tmp_dir", str(tmp_path))
        recorder = agent._BotAudioRecorder(enabled=True, sample_rate=16000, channels=1)
        recorder.capture_frame(_Frame(b"\x00\x00" * 16000))

        path = await recorder.write_wav("run_test")
        assert path is not None
        assert path.exists()
        assert recorder.duration_ms >= 1000

        with wave.open(str(path), "rb") as wav_file:
            assert wav_file.getframerate() == 16000
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2

    async def test_disabled_recorder_skips_write(self):
        recorder = agent._BotAudioRecorder(enabled=False)
        recorder.capture_frame(_Frame(b"\x00\x00" * 200))
        path = await recorder.write_wav("run_disabled")
        assert path is None

    async def test_write_wav_stereo_when_both_legs_captured(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "recording_tmp_dir", str(tmp_path))
        recorder = agent._BotAudioRecorder(enabled=True, sample_rate=16000, channels=1)

        # Capture bot leg (already at 16 kHz)
        recorder.capture_frame(_Frame(b"\x01\x00" * 8000))  # 0.5 s

        # Capture harness leg via real rtc.AudioFrame (24 kHz → 16 kHz)
        for _ in range(25):  # 25 × 20 ms = 500 ms
            recorder.capture_harness_frame(_make_audio_frame(sample_rate=24000, duration_ms=20))

        path = await recorder.write_wav("run_stereo")
        assert path is not None
        with wave.open(str(path), "rb") as wav_file:
            assert wav_file.getnchannels() == 2
            assert wav_file.getframerate() == 16000

    async def test_write_wav_mono_fallback_when_only_bot(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "recording_tmp_dir", str(tmp_path))
        recorder = agent._BotAudioRecorder(enabled=True, sample_rate=16000, channels=1)
        recorder.capture_frame(_Frame(b"\x00\x00" * 1600))

        path = await recorder.write_wav("run_mono")
        assert path is not None
        with wave.open(str(path), "rb") as wav_file:
            assert wav_file.getnchannels() == 1

    async def test_harness_frame_ignored_when_disabled(self):
        recorder = agent._BotAudioRecorder(enabled=False)
        recorder.capture_harness_frame(_make_audio_frame())
        assert len(recorder._harness_pcm) == 0

    async def test_harness_pcm_is_padded_to_elapsed_offset(self):
        recorder = agent._BotAudioRecorder(enabled=True, sample_rate=16000, channels=1)
        recorder._harness_resampler = _FakeResampler(b"\x02\x00" * 160)

        recorder.capture_harness_frame(_make_audio_frame(), elapsed_ms=500)

        expected_gap_bytes = 16000 * 2 // 2  # 500 ms mono at 16 kHz, 16-bit
        assert len(recorder._harness_pcm) == expected_gap_bytes + (160 * 2)
        assert recorder._harness_pcm[:expected_gap_bytes] == b"\x00" * expected_gap_bytes


class TestRecordingAudioSource:
    async def test_forwards_frame_to_underlying_source_and_recorder(self):
        mock_source = AsyncMock()
        recorder = agent._BotAudioRecorder(enabled=True, sample_rate=16000, channels=1)

        proxy = RecordingAudioSource(mock_source, recorder)
        # Push enough frames (500 ms total) to guarantee resampler output.
        frames = [_make_audio_frame(sample_rate=24000, duration_ms=20) for _ in range(25)]
        for frame in frames:
            await proxy.capture_frame(frame)

        assert mock_source.capture_frame.await_count == 25
        assert len(recorder._harness_pcm) > 0
