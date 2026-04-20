from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx
import pytest

from src.openai_chat_client import (
    _thread_local_pool,
    aclose_shared_chat_clients,
    get_shared_chat_completion_client,
)


@pytest.fixture(autouse=True)
async def _drain_pool():
    """Ensure the calling thread's pool is empty before and after each test."""
    await aclose_shared_chat_clients()
    yield
    await aclose_shared_chat_clients()


def test_pool_returns_same_client_for_same_base_url() -> None:
    c1 = get_shared_chat_completion_client(api_base_url="https://api.openai.com/v1")
    c2 = get_shared_chat_completion_client(api_base_url="https://api.openai.com/v1")
    assert c1 is c2


def test_pool_returns_different_clients_for_different_base_urls() -> None:
    c1 = get_shared_chat_completion_client(api_base_url="https://api.openai.com/v1")
    c2 = get_shared_chat_completion_client(api_base_url="https://api.openai.com/v2")
    assert c1 is not c2


@pytest.mark.asyncio
async def test_aclose_drains_pool() -> None:
    get_shared_chat_completion_client(api_base_url="https://api.openai.com/v1")
    assert len(_thread_local_pool()) == 1
    await aclose_shared_chat_clients()
    assert len(_thread_local_pool()) == 0


def test_pool_client_is_httpx_async_client() -> None:
    client = get_shared_chat_completion_client(api_base_url="https://api.openai.com/v1")
    assert isinstance(client, httpx.AsyncClient)


def test_pool_is_thread_local_different_threads_get_different_clients() -> None:
    """Clients created in different threads must be distinct (each thread owns its pool)."""
    results: dict[str, Any] = {}

    def _make_client(label: str) -> None:
        results[label] = get_shared_chat_completion_client(
            api_base_url="https://api.openai.com/v1"
        )

    t1 = threading.Thread(target=_make_client, args=("t1",))
    t2 = threading.Thread(target=_make_client, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["t1"] is not results["t2"], (
        "Thread-local pools must produce independent clients per thread"
    )


@pytest.mark.asyncio
async def test_concurrent_requests_use_single_pool_entry(monkeypatch) -> None:
    """Two concurrent calls for the same URL in the same event loop get the same client."""
    from src import openai_chat_client

    instances: list[Any] = []
    original_async_client = httpx.AsyncClient

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "ok"}}]}

    class _TrackingClient(original_async_client):  # type: ignore[misc]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            instances.append(self)

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            return _FakeResponse()

    monkeypatch.setattr(openai_chat_client.httpx, "AsyncClient", _TrackingClient)
    await aclose_shared_chat_clients()

    await asyncio.gather(
        openai_chat_client.request_chat_completion(
            api_key="sk-a",
            api_base_url="https://api.openai.com/v1",
            timeout_s=3.0,
            payload={"model": "gpt-4o-mini", "messages": []},
        ),
        openai_chat_client.request_chat_completion(
            api_key="sk-b",
            api_base_url="https://api.openai.com/v1",
            timeout_s=3.0,
            payload={"model": "gpt-4o-mini", "messages": []},
        ),
    )

    assert len(instances) == 1, "Two concurrent calls for the same URL must share one client"
