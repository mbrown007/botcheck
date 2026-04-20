from __future__ import annotations

from functools import partial

import httpx
import pytest

from botcheck_api.runs.service_webrtc import resolve_bot_builder_preview_bootstrap


@pytest.mark.asyncio
async def test_resolve_bot_builder_preview_bootstrap_round_trips() -> None:
    seen_paths: list[str] = []
    seen_auth_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        seen_auth_headers.append(request.headers.get("Authorization"))
        if request.url.path == "/agents/monitoring-assistant/versions/ver_2026_04_03/preview-sessions":
            return httpx.Response(
                200,
                json={
                    "session_id": "preview_123",
                    "room_name": "preview-monitoring-assistant-preview_123",
                    "participant_name": "operator-preview_123",
                    "transport": "webrtc",
                },
            )
        if request.url.path == "/preview-sessions/preview_123/token":
            return httpx.Response(
                200,
                json={
                    "server_url": "wss://livekit.bot-builder.test",
                    "participant_token": "jwt-preview-token",
                },
            )
        raise AssertionError(f"unexpected request path: {request.url.path}")

    client_cls = partial(httpx.AsyncClient, transport=httpx.MockTransport(handler))

    bootstrap = await resolve_bot_builder_preview_bootstrap(
        webrtc_config={
            "provider": "livekit",
            "session_mode": "bot_builder_preview",
            "api_base_url": "http://bot-builder.internal",
            "agent_id": "monitoring-assistant",
            "version_id": "ver_2026_04_03",
            "auth_headers": {"Authorization": "Bearer bot-builder-token"},
            "join_timeout_s": 25,
        },
        http_client_cls=client_cls,
    )

    assert seen_paths == [
        "/agents/monitoring-assistant/versions/ver_2026_04_03/preview-sessions",
        "/preview-sessions/preview_123/token",
    ]
    assert seen_auth_headers == ["Bearer bot-builder-token", "Bearer bot-builder-token"]
    assert bootstrap.session_id == "preview_123"
    assert bootstrap.room_name == "preview-monitoring-assistant-preview_123"
    assert bootstrap.server_url == "wss://livekit.bot-builder.test"
    assert bootstrap.participant_token == "jwt-preview-token"
    assert bootstrap.join_timeout_s == 25


@pytest.mark.asyncio
async def test_resolve_bot_builder_preview_bootstrap_rejects_invalid_session_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"session_id": "preview_123"})

    client_cls = partial(httpx.AsyncClient, transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="Invalid bot builder preview session response"):
        await resolve_bot_builder_preview_bootstrap(
            webrtc_config={
                "api_base_url": "http://bot-builder.internal",
                "agent_id": "monitoring-assistant",
                "version_id": "ver_2026_04_03",
            },
            http_client_cls=client_cls,
        )
