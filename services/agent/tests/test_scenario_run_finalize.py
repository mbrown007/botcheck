from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src import scenario_run_finalize


class _FakeMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float | None]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **kwargs):
        self._labels = {k: str(v) for k, v in kwargs.items()}
        return self

    def inc(self, value: float | None = None) -> None:
        self.calls.append((dict(self._labels), value))


class _FakeRecorder:
    def __init__(self, *, wav_path: Path | None = None) -> None:
        self.stats = {"frames": 10}
        self.duration_ms = 1234
        self._wav_path = wav_path

    async def write_wav(self, run_id: str) -> Path | None:
        return self._wav_path


@pytest.mark.asyncio
async def test_finalize_run_media_sip_completed_without_recording(monkeypatch) -> None:
    sip_outcomes = _FakeMetric()
    telephony_minutes = _FakeMetric()
    monkeypatch.setattr(scenario_run_finalize, "SIP_CALL_OUTCOMES_TOTAL", sip_outcomes)
    monkeypatch.setattr(scenario_run_finalize, "TELEPHONY_MINUTES_TOTAL", telephony_minutes)

    bot_listener = SimpleNamespace(stop=AsyncMock())
    remove_participant = AsyncMock()
    upload_recording = AsyncMock()
    logger = SimpleNamespace(info=Mock(), warning=Mock(), debug=Mock())

    await scenario_run_finalize.finalize_run_media(
        run_id="run_123",
        room=SimpleNamespace(name="room-1"),
        bot_participant=SimpleNamespace(identity="bot-1"),
        is_sip=True,
        call_started_monotonic=0.0,
        bot_listener=bot_listener,
        recorder=_FakeRecorder(wav_path=None),
        settings_obj=SimpleNamespace(
            recording_upload_enabled=False,
            livekit_url="ws://localhost:7880",
            livekit_api_key="key",
            livekit_api_secret="secret",
        ),
        livekit_api_cls=object(),
        room_participant_identity_cls=object(),
        remove_participant_from_room_fn=remove_participant,
        upload_run_recording_fn=upload_recording,
        logger_obj=logger,
    )

    bot_listener.stop.assert_awaited_once()
    remove_participant.assert_awaited_once()
    upload_recording.assert_not_awaited()
    assert any(call[0].get("outcome") == "completed" for call in sip_outcomes.calls)
    assert any(call[0].get("provider") == "livekit-sip" for call in telephony_minutes.calls)


@pytest.mark.asyncio
async def test_finalize_run_media_cleans_temp_wav_on_upload_error(tmp_path: Path) -> None:
    wav_path = tmp_path / "run.wav"
    wav_path.write_bytes(b"wav")

    bot_listener = SimpleNamespace(stop=AsyncMock())
    remove_participant = AsyncMock()
    upload_recording = AsyncMock(side_effect=RuntimeError("upload failed"))
    logger = SimpleNamespace(info=Mock(), warning=Mock(), debug=Mock())

    await scenario_run_finalize.finalize_run_media(
        run_id="run_456",
        room=SimpleNamespace(name="room-2"),
        bot_participant=SimpleNamespace(identity="bot-2"),
        is_sip=False,
        call_started_monotonic=0.0,
        bot_listener=bot_listener,
        recorder=_FakeRecorder(wav_path=wav_path),
        settings_obj=SimpleNamespace(
            recording_upload_enabled=True,
            livekit_url="ws://localhost:7880",
            livekit_api_key="key",
            livekit_api_secret="secret",
        ),
        livekit_api_cls=object(),
        room_participant_identity_cls=object(),
        remove_participant_from_room_fn=remove_participant,
        upload_run_recording_fn=upload_recording,
        logger_obj=logger,
    )

    assert not wav_path.exists()
    upload_recording.assert_awaited_once()
