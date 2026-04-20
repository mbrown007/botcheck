from __future__ import annotations

from src import media_engine


class _FakeAudioSource:
    def __init__(self, *, sample_rate: int, num_channels: int) -> None:
        self.sample_rate = sample_rate
        self.num_channels = num_channels


class _FakeLocalAudioTrack:
    @staticmethod
    def create_audio_track(name: str, source: _FakeAudioSource):
        return {"name": name, "source": source}


class _FakeTrackPublishOptions:
    def __init__(self, *, source: str) -> None:
        self.source = source


class _FakeTrackSource:
    SOURCE_MICROPHONE = "mic"


class _FakeRtcModule:
    AudioSource = _FakeAudioSource
    LocalAudioTrack = _FakeLocalAudioTrack
    TrackPublishOptions = _FakeTrackPublishOptions
    TrackSource = _FakeTrackSource


class _FakeLocalParticipant:
    def __init__(self) -> None:
        self.published_track = None
        self.published_options = None

    async def publish_track(self, track, options) -> None:
        self.published_track = track
        self.published_options = options


class _FakeRoom:
    def __init__(self) -> None:
        self.local_participant = _FakeLocalParticipant()


async def test_publish_harness_audio_track_publishes_microphone_track() -> None:
    room = _FakeRoom()

    source = await media_engine.publish_harness_audio_track(
        room=room,
        rtc_module=_FakeRtcModule,
    )

    assert isinstance(source, _FakeAudioSource)
    assert source.sample_rate == 24000
    assert source.num_channels == 1
    assert room.local_participant.published_track["name"] == "harness"
    assert room.local_participant.published_track["source"] is source
    assert room.local_participant.published_options.source == _FakeTrackSource.SOURCE_MICROPHONE


class _FakeRoomService:
    def __init__(self) -> None:
        self.removed = None

    async def remove_participant(self, identity) -> None:
        self.removed = identity


class _FakeLiveKitAPI:
    last_init = None
    last_room_service = None

    def __init__(self, *, url: str, api_key: str, api_secret: str) -> None:
        _FakeLiveKitAPI.last_init = {
            "url": url,
            "api_key": api_key,
            "api_secret": api_secret,
        }
        self.room = _FakeRoomService()
        _FakeLiveKitAPI.last_room_service = self.room

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeRoomParticipantIdentity:
    def __init__(self, *, room: str, identity: str) -> None:
        self.room = room
        self.identity = identity


async def test_remove_participant_from_room_uses_livekit_api() -> None:
    await media_engine.remove_participant_from_room(
        room_name="room_1",
        participant_identity="bot_1",
        livekit_api_cls=_FakeLiveKitAPI,
        room_participant_identity_cls=_FakeRoomParticipantIdentity,
        livekit_url="ws://livekit",
        livekit_api_key="lk_key",
        livekit_api_secret="lk_secret",
    )

    assert _FakeLiveKitAPI.last_init == {
        "url": "ws://livekit",
        "api_key": "lk_key",
        "api_secret": "lk_secret",
    }
    assert isinstance(_FakeLiveKitAPI.last_room_service.removed, _FakeRoomParticipantIdentity)
    assert _FakeLiveKitAPI.last_room_service.removed.room == "room_1"
    assert _FakeLiveKitAPI.last_room_service.removed.identity == "bot_1"
