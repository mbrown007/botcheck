"""Run telephony and LiveKit helper functions."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import HTTPException
from livekit import api as lk_api

from .. import metrics as api_metrics
from ..config import settings
from ..sip import SIPCredentials


async def livekit_room_exists(room_name: str) -> bool:
    candidate = room_name.strip()
    if not candidate:
        return False
    lkapi = lk_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        resp = await lkapi.room.list_rooms(lk_api.ListRoomsRequest(names=[candidate]))
        rooms = list(getattr(resp, "rooms", []) or [])
        return any(str(getattr(room, "name", "")) == candidate for room in rooms)
    finally:
        await lkapi.aclose()


async def delete_livekit_room(room_name: str) -> None:
    candidate = room_name.strip()
    if not candidate:
        return
    lkapi = lk_api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        await lkapi.room.delete_room(lk_api.DeleteRoomRequest(room=candidate))
    finally:
        await lkapi.aclose()


def extract_sip_host(endpoint: str) -> str:
    candidate = endpoint.strip()
    if candidate.startswith(("sip:", "sips:")):
        parsed = urlparse(candidate.replace("sips:", "sips://", 1).replace("sip:", "sip://", 1))
        authority = parsed.netloc or parsed.path
        host_port = authority.split("@", 1)[-1]
        host = host_port.split(";", 1)[0]
        host = host.split(":", 1)[0]
    else:
        host = candidate
        if "@" in host:
            host = host.split("@", 1)[1]
        host = host.split(";", 1)[0]
        host = host.split(":", 1)[0]
    return host.lower()


def extract_sip_dial_target(endpoint: str) -> str:
    candidate = endpoint.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="Invalid SIP endpoint")
    if candidate.startswith(("sip:", "sips:")):
        parsed = urlparse(candidate.replace("sips:", "sips://", 1).replace("sip:", "sip://", 1))
        authority = parsed.netloc or parsed.path
        userinfo = authority.split("@", 1)[0] if "@" in authority else ""
        user = userinfo.split(";", 1)[0].split(":", 1)[0]
        if user:
            return user
        raise HTTPException(status_code=400, detail=f"Invalid SIP endpoint: {endpoint}")
    if "@" in candidate:
        user = candidate.split("@", 1)[0].split(";", 1)[0].split(":", 1)[0]
        if user:
            return user
        raise HTTPException(status_code=400, detail=f"Invalid SIP endpoint: {endpoint}")
    return candidate


def is_explicit_sip_endpoint(value: str) -> bool:
    candidate = value.strip().lower()
    return candidate.startswith(("sip:", "sips:")) or "@" in candidate


def validate_sip_destination(endpoint: str) -> None:
    allowed = [d.strip().lower() for d in settings.sip_destination_allowlist if d.strip()]
    if not allowed:
        api_metrics.SIP_DISPATCH_ERRORS_TOTAL.labels(error_class="allowlist_unconfigured").inc()
        raise HTTPException(
            status_code=500,
            detail="SIP destination allowlist is not configured",
        )
    host = extract_sip_host(endpoint)
    if not host:
        api_metrics.SIP_DISPATCH_ERRORS_TOTAL.labels(error_class="allowlist_rejected").inc()
        raise HTTPException(status_code=400, detail=f"Invalid SIP endpoint: {endpoint}")
    for domain in allowed:
        normalized = domain.lstrip(".")
        if host == normalized or host.endswith(f".{normalized}"):
            return
    api_metrics.SIP_DISPATCH_ERRORS_TOTAL.labels(error_class="allowlist_rejected").inc()
    raise HTTPException(
        status_code=400,
        detail=f"SIP destination not in allowlist: {endpoint}",
    )


async def dispatch_sip_call(
    lkapi: lk_api.LiveKitAPI,
    run_id: str,
    creds: SIPCredentials,
    bot_endpoint: str,
    dial_target: str | None,
    room_name: str,
    caller_id: str | None = None,
    trunk_id_override: str | None = None,
) -> str:
    target = extract_sip_dial_target(dial_target or bot_endpoint)
    trunk_id = trunk_id_override or creds.trunk_id
    req = lk_api.CreateSIPParticipantRequest(
        room_name=room_name,
        sip_trunk_id=trunk_id,
        sip_call_to=target,
        participant_identity=f"bot-{run_id}",
        participant_name="Bot Under Test",
        participant_metadata=json.dumps({"run_id": run_id}),
    )
    if caller_id:
        req.sip_number = caller_id
    await lkapi.sip.create_sip_participant(req)
    return trunk_id
