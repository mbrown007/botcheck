from __future__ import annotations

import httpx
import pytest

from src import openai_chat_client


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    instances: list["_FakeAsyncClient"] = []

    def __init__(self, *, base_url: str, headers=None, limits=None, timeout=None) -> None:
        self.base_url = base_url
        self.headers = headers
        self.limits = limits
        self.timeout = timeout
        self.closed = False
        self.posts: list[dict[str, object]] = []
        _FakeAsyncClient.instances.append(self)

    async def post(self, path: str, *, json: dict[str, object], headers=None, timeout=None):
        self.posts.append(
            {
                "path": path,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_request_chat_completion_reuses_shared_client_and_keeps_auth_per_request(
    monkeypatch,
) -> None:
    monkeypatch.setattr(openai_chat_client.httpx, "AsyncClient", _FakeAsyncClient)
    await openai_chat_client.aclose_shared_chat_clients()
    _FakeAsyncClient.instances.clear()

    payload = {"model": "gpt-4o-mini", "messages": []}
    await openai_chat_client.request_chat_completion(
        api_key="sk-one",
        api_base_url="https://api.openai.com/v1",
        timeout_s=3.0,
        payload=payload,
    )
    await openai_chat_client.request_chat_completion(
        api_key="sk-two",
        api_base_url="https://api.openai.com/v1/",
        timeout_s=4.0,
        payload=payload,
    )

    assert len(_FakeAsyncClient.instances) == 1
    client = _FakeAsyncClient.instances[0]
    assert client.base_url == "https://api.openai.com/v1"
    assert client.headers is None  # Content-Type is passed per-request, not at client init
    assert client.posts[0]["headers"] == {
        "Authorization": "Bearer sk-one",
        "Content-Type": "application/json",
    }
    assert client.posts[0]["timeout"] == 3.0
    assert client.posts[1]["headers"] == {
        "Authorization": "Bearer sk-two",
        "Content-Type": "application/json",
    }
    assert client.posts[1]["timeout"] == 4.0

    await openai_chat_client.aclose_shared_chat_clients()
    assert client.closed is True


@pytest.mark.asyncio
async def test_request_chat_completion_uses_ephemeral_client_for_custom_client_cls() -> None:
    captured: dict[str, object] = {}

    class _EphemeralClient:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, path: str, *, json: dict[str, object], headers=None):
            captured["path"] = path
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    await openai_chat_client.request_chat_completion(
        api_key="sk-test",
        api_base_url="https://example.invalid/v1",
        timeout_s=5.0,
        payload={"model": "gpt-4o-mini", "messages": []},
        http_client_cls=lambda **kwargs: _EphemeralClient(**kwargs),
    )

    assert captured["init_kwargs"] == {
        "base_url": "https://example.invalid/v1",
        "timeout": 5.0,
    }
    assert captured["path"] == "/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer sk-test",
        "Content-Type": "application/json",
    }
