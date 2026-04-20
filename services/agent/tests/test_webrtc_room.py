from __future__ import annotations

import logging

import pytest

from src.webrtc_room import connect_webrtc_room

# NOTE: In production, webrtc_server_url and webrtc_participant_token are never
# stored in LiveKit room metadata. They arrive exclusively via the harness
# transport-context API response, which is merged last into run_metadata at the
# entrypoint coordinator ({**room_metadata, **transport_context}). These unit
# tests pass both fields directly into the run_metadata dict to exercise
# connect_webrtc_room in isolation — this is valid because the function only
# cares that the merged dict contains the required fields, not where they came from.


class _FakeConnectedRoom:
    def __init__(
        self,
        *,
        name: str = "preview-room",
        fail_connect: bool = False,
        fail_disconnect: bool = False,
    ) -> None:
        self.name = name
        self._fail_connect = fail_connect
        self._fail_disconnect = fail_disconnect
        self.connect_calls: list[tuple[str, str]] = []
        self.disconnect_calls = 0

    async def connect(self, url: str, token: str) -> None:
        self.connect_calls.append((url, token))
        if self._fail_connect:
            raise RuntimeError("connect failed")

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        if self._fail_disconnect:
            raise RuntimeError("disconnect also failed")


class _RtcModule:
    def __init__(self, room: _FakeConnectedRoom) -> None:
        self._room = room

    def Room(self) -> _FakeConnectedRoom:
        return self._room


@pytest.mark.asyncio
async def test_connect_webrtc_room_connects_remote_livekit_room() -> None:
    room = _FakeConnectedRoom(name="preview-room")

    connected = await connect_webrtc_room(
        run_metadata={
            "transport": "webrtc",
            "webrtc_provider": "livekit",
            "webrtc_session_mode": "bot_builder_preview",
            "webrtc_remote_room_name": "preview-room",
            "webrtc_server_url": "wss://livekit.example.test",
            "webrtc_participant_token": "participant-token",
            "webrtc_session_id": "sess_123",
        },
        rtc_module=_RtcModule(room),
        logger_obj=logging.getLogger("test.webrtc_room"),
    )

    assert connected is room
    assert room.connect_calls == [
        ("wss://livekit.example.test", "participant-token"),
    ]


@pytest.mark.asyncio
async def test_connect_webrtc_room_rejects_missing_bootstrap() -> None:
    with pytest.raises(RuntimeError, match="Missing WebRTC server URL"):
        await connect_webrtc_room(
            run_metadata={
                "transport": "webrtc",
                "webrtc_provider": "livekit",
                "webrtc_session_mode": "bot_builder_preview",
                "webrtc_participant_token": "participant-token",
            },
            rtc_module=_RtcModule(_FakeConnectedRoom()),
            logger_obj=logging.getLogger("test.webrtc_room"),
        )


@pytest.mark.asyncio
async def test_connect_webrtc_room_rejects_room_name_mismatch() -> None:
    room = _FakeConnectedRoom(name="other-room")

    with pytest.raises(RuntimeError, match="Remote WebRTC room name mismatch"):
        await connect_webrtc_room(
            run_metadata={
                "transport": "webrtc",
                "webrtc_provider": "livekit",
                "webrtc_session_mode": "bot_builder_preview",
                "webrtc_remote_room_name": "preview-room",
                "webrtc_server_url": "wss://livekit.example.test",
                "webrtc_participant_token": "participant-token",
            },
            rtc_module=_RtcModule(room),
            logger_obj=logging.getLogger("test.webrtc_room"),
        )

    assert room.disconnect_calls == 1


@pytest.mark.asyncio
async def test_connect_webrtc_room_disconnects_after_connect_failure() -> None:
    room = _FakeConnectedRoom(fail_connect=True)

    with pytest.raises(RuntimeError, match="Failed to connect remote WebRTC room"):
        await connect_webrtc_room(
            run_metadata={
                "transport": "webrtc",
                "webrtc_provider": "livekit",
                "webrtc_session_mode": "bot_builder_preview",
                "webrtc_remote_room_name": "preview-room",
                "webrtc_server_url": "wss://livekit.example.test",
                "webrtc_participant_token": "participant-token",
            },
            rtc_module=_RtcModule(room),
            logger_obj=logging.getLogger("test.webrtc_room"),
        )

    assert room.connect_calls == [
        ("wss://livekit.example.test", "participant-token"),
    ]
    assert room.disconnect_calls == 1


@pytest.mark.asyncio
async def test_connect_webrtc_room_raises_original_error_when_disconnect_also_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    room = _FakeConnectedRoom(fail_connect=True, fail_disconnect=True)

    with caplog.at_level(logging.WARNING, logger="test.webrtc_room"):
        with pytest.raises(RuntimeError, match="Failed to connect remote WebRTC room"):
            await connect_webrtc_room(
                run_metadata={
                    "transport": "webrtc",
                    "webrtc_provider": "livekit",
                    "webrtc_session_mode": "bot_builder_preview",
                    "webrtc_remote_room_name": "preview-room",
                    "webrtc_server_url": "wss://livekit.example.test",
                    "webrtc_participant_token": "participant-token",
                    "webrtc_session_id": "sess_cleanup_fail",
                },
                rtc_module=_RtcModule(room),
                logger_obj=logging.getLogger("test.webrtc_room"),
            )

    assert room.disconnect_calls == 1
    assert "webrtc_room_disconnect_after_connect_failure_failed" in caplog.text
