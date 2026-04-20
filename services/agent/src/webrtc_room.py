from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class WebRTCRunBootstrap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transport: str | None = None
    bot_protocol: str | None = None
    webrtc_provider: str | None = None
    webrtc_session_mode: str | None = None
    webrtc_session_id: str | None = None
    webrtc_remote_room_name: str | None = None
    webrtc_participant_name: str | None = None
    webrtc_server_url: str | None = None
    webrtc_participant_token: str | None = None
    webrtc_join_timeout_s: int = Field(default=20, ge=1, le=120)

    @field_validator(
        "transport",
        "bot_protocol",
        "webrtc_provider",
        "webrtc_session_mode",
        "webrtc_session_id",
        "webrtc_remote_room_name",
        "webrtc_participant_name",
        "webrtc_server_url",
        "webrtc_participant_token",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("webrtc_join_timeout_s", mode="before")
    @classmethod
    def _normalize_join_timeout(cls, value: object) -> int:
        if value is None or str(value).strip() == "":
            return 20
        return int(value)

    def transport_protocol(self) -> str:
        return (self.transport or self.bot_protocol or "").lower()


async def connect_webrtc_room(
    *,
    run_metadata: dict[str, object],
    rtc_module: Any,
    logger_obj,
):
    try:
        bootstrap = WebRTCRunBootstrap.model_validate(run_metadata)
    except ValidationError as exc:
        raise RuntimeError("Invalid WebRTC run bootstrap metadata") from exc

    if bootstrap.transport_protocol() != "webrtc":
        raise RuntimeError("WebRTC room bootstrap requested for non-WebRTC transport")
    if bootstrap.webrtc_provider != "livekit":
        raise RuntimeError(
            f"Unsupported WebRTC provider: {bootstrap.webrtc_provider or '<missing>'}"
        )
    if bootstrap.webrtc_session_mode != "bot_builder_preview":
        raise RuntimeError(
            "Unsupported WebRTC session mode: "
            f"{bootstrap.webrtc_session_mode or '<missing>'}"
        )
    if not bootstrap.webrtc_server_url:
        raise RuntimeError("Missing WebRTC server URL in transport context")
    if not bootstrap.webrtc_participant_token:
        raise RuntimeError("Missing WebRTC participant token in transport context")

    room = rtc_module.Room()
    try:
        await asyncio.wait_for(
            room.connect(
                bootstrap.webrtc_server_url,
                bootstrap.webrtc_participant_token,
            ),
            timeout=float(bootstrap.webrtc_join_timeout_s),
        )
    except Exception as exc:
        try:
            await room.disconnect()
        except Exception:
            logger_obj.warning(
                "webrtc_room_disconnect_after_connect_failure_failed session_id=%s",
                bootstrap.webrtc_session_id or "",
                exc_info=True,
            )
        raise RuntimeError("Failed to connect remote WebRTC room") from exc

    expected_room_name = bootstrap.webrtc_remote_room_name
    actual_room_name = str(getattr(room, "name", "") or "").strip()
    if expected_room_name and actual_room_name and actual_room_name != expected_room_name:
        try:
            await room.disconnect()
        except Exception:
            logger_obj.warning(
                "webrtc_room_disconnect_after_mismatch_failed expected=%s actual=%s",
                expected_room_name,
                actual_room_name,
                exc_info=True,
            )
        raise RuntimeError(
            "Remote WebRTC room name mismatch: "
            f"expected {expected_room_name!r}, got {actual_room_name!r}"
        )

    logger_obj.info(
        "webrtc_room_connected provider=%s session_mode=%s session_id=%s remote_room=%s participant=%s",
        bootstrap.webrtc_provider,
        bootstrap.webrtc_session_mode,
        bootstrap.webrtc_session_id,
        expected_room_name or actual_room_name or "",
        bootstrap.webrtc_participant_name or "",
    )
    return room
