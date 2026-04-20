"""Helpers for external WebRTC destination bootstrapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator


class _BotBuilderPreviewSessionResponse(BaseModel):
    session_id: str = Field(min_length=1)
    room_name: str = Field(min_length=1)
    participant_name: str = Field(min_length=1)
    transport: str = Field(min_length=1)

    @field_validator("session_id", "room_name", "participant_name", "transport")
    @classmethod
    def _normalize_nonempty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("field must not be blank")
        return text


class _BotBuilderPreviewTokenResponse(BaseModel):
    server_url: str = Field(min_length=1)
    participant_token: str = Field(min_length=1)

    @field_validator("server_url", "participant_token")
    @classmethod
    def _normalize_nonempty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("field must not be blank")
        return text


@dataclass(frozen=True)
class ResolvedWebRTCBootstrap:
    provider: str
    session_mode: str
    api_base_url: str
    agent_id: str
    version_id: str
    session_id: str
    room_name: str
    participant_name: str
    server_url: str
    participant_token: str
    join_timeout_s: int


@dataclass(frozen=True)
class ResolvedWebRTCToken:
    server_url: str
    participant_token: str


def _normalize_headers(headers: dict[str, object] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (headers or {}).items():
        normalized_key = str(key).strip()
        normalized_value = str(value).strip()
        if not normalized_key or not normalized_value:
            continue
        out[normalized_key] = normalized_value
    return out


def _normalize_preview_bootstrap_config(
    webrtc_config: dict[str, object],
) -> tuple[str, str, str, dict[str, str], int]:
    provider = str(webrtc_config.get("provider") or "").strip().lower() or "livekit"
    session_mode = (
        str(webrtc_config.get("session_mode") or "").strip().lower() or "bot_builder_preview"
    )
    api_base_url = str(webrtc_config.get("api_base_url") or "").strip().rstrip("/")
    join_timeout_raw = webrtc_config.get("join_timeout_s")
    join_timeout_s = int(join_timeout_raw) if join_timeout_raw is not None else 20
    headers = _normalize_headers(webrtc_config.get("auth_headers"))  # type: ignore[arg-type]

    if provider != "livekit":
        raise ValueError(f"Unsupported WebRTC provider: {provider!r}")
    if session_mode != "bot_builder_preview":
        raise ValueError(f"Unsupported WebRTC session mode: {session_mode!r}")
    if not api_base_url:
        raise ValueError("webrtc_config.api_base_url is required")

    return provider, session_mode, api_base_url, headers, join_timeout_s


async def resolve_bot_builder_preview_token(
    *,
    webrtc_config: dict[str, object],
    session_id: str,
    http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
) -> ResolvedWebRTCToken:
    provider, session_mode, api_base_url, headers, _join_timeout_s = _normalize_preview_bootstrap_config(
        webrtc_config
    )
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise ValueError("session_id is required")

    client_factory = http_client_cls or httpx.AsyncClient
    async with client_factory(base_url=api_base_url, timeout=httpx.Timeout(10.0), headers=headers) as client:
        token_resp = await client.post(f"/preview-sessions/{normalized_session_id}/token", json={})
        token_resp.raise_for_status()
        token_payload = token_resp.json()
        if not isinstance(token_payload, dict):
            raise ValueError("Bot builder preview token response must be a JSON object")
        try:
            token = _BotBuilderPreviewTokenResponse.model_validate(token_payload)
        except ValidationError as exc:
            raise ValueError("Invalid bot builder preview token response") from exc

    del provider, session_mode
    return ResolvedWebRTCToken(
        server_url=token.server_url,
        participant_token=token.participant_token,
    )


async def resolve_bot_builder_preview_bootstrap(
    *,
    webrtc_config: dict[str, object],
    http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
) -> ResolvedWebRTCBootstrap:
    provider, session_mode, api_base_url, headers, join_timeout_s = _normalize_preview_bootstrap_config(
        webrtc_config
    )
    agent_id = str(webrtc_config.get("agent_id") or "").strip()
    version_id = str(webrtc_config.get("version_id") or "").strip()
    if not agent_id:
        raise ValueError("webrtc_config.agent_id is required")
    if not version_id:
        raise ValueError("webrtc_config.version_id is required")

    client_factory = http_client_cls or httpx.AsyncClient
    async with client_factory(base_url=api_base_url, timeout=httpx.Timeout(10.0), headers=headers) as client:
        preview_session_resp = await client.post(
            f"/agents/{agent_id}/versions/{version_id}/preview-sessions"
        )
        preview_session_resp.raise_for_status()
        preview_session_payload = preview_session_resp.json()
        if not isinstance(preview_session_payload, dict):
            raise ValueError("Bot builder preview session response must be a JSON object")
        try:
            session = _BotBuilderPreviewSessionResponse.model_validate(preview_session_payload)
        except ValidationError as exc:
            raise ValueError("Invalid bot builder preview session response") from exc

    token = await resolve_bot_builder_preview_token(
        webrtc_config=webrtc_config,
        session_id=session.session_id,
        http_client_cls=http_client_cls,
    )

    return ResolvedWebRTCBootstrap(
        provider=provider,
        session_mode=session_mode,
        api_base_url=api_base_url,
        agent_id=agent_id,
        version_id=version_id,
        session_id=session.session_id,
        room_name=session.room_name,
        participant_name=session.participant_name,
        server_url=token.server_url,
        participant_token=token.participant_token,
        join_timeout_s=join_timeout_s,
    )
