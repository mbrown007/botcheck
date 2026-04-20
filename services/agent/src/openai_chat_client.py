from __future__ import annotations

import logging
import threading
from typing import Any, Callable

import httpx

# Thread-local pool: each job thread (JobExecutorType.THREAD) runs its own asyncio
# event loop, so httpx.AsyncClient instances are bound to that loop. Using thread-local
# storage ensures every thread owns its own clients — no cross-event-loop access,
# no lock required. Multiple AI-caller turns within a single run still share one
# TLS connection because they all run in the same thread.
# NOTE: API key is passed per-request via Authorization header; the pool key is
# URL-only because all turns in one worker use the same api_base_url. If per-tenant
# isolation of connection pools is needed in future, key by (url, hash(api_key)).
_THREAD_LOCAL = threading.local()
_logger = logging.getLogger(__name__)
_SHARED_CHAT_CLIENT_LIMITS = httpx.Limits(
    max_keepalive_connections=5,
    max_connections=20,
    keepalive_expiry=30.0,
)


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def extract_chat_completion_content(
    payload: dict[str, Any],
    *,
    response_label: str,
) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"{response_label} response missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError(f"{response_label} response choice has invalid shape.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"{response_label} response missing message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{response_label} response content is empty.")
    return content


def _normalize_api_base_url(api_base_url: str) -> str:
    return api_base_url.rstrip("/")


def _thread_local_pool() -> dict[str, httpx.AsyncClient]:
    if not hasattr(_THREAD_LOCAL, "clients"):
        _THREAD_LOCAL.clients = {}
    return _THREAD_LOCAL.clients  # type: ignore[no-any-return]


def get_shared_chat_completion_client(*, api_base_url: str) -> httpx.AsyncClient:
    """Return the thread-local AsyncClient for api_base_url, creating it if needed.

    Expects api_base_url to be already normalised (no trailing slash).
    """
    pool = _thread_local_pool()
    client = pool.get(api_base_url)
    if client is None:
        client = httpx.AsyncClient(
            base_url=api_base_url,
            limits=_SHARED_CHAT_CLIENT_LIMITS,
        )
        pool[api_base_url] = client
    return client


async def aclose_shared_chat_clients() -> None:
    """Close all clients in the calling thread's pool.

    Call this at the end of a job entrypoint (or at worker shutdown) to release
    TLS connections held by the current thread. Safe to call even if the pool is empty.
    """
    pool = _thread_local_pool()
    clients = list(pool.values())
    pool.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:
            _logger.warning("Error closing shared chat client; ignoring.", exc_info=True)


async def request_chat_completion(
    *,
    api_key: str,
    api_base_url: str,
    timeout_s: float,
    payload: dict[str, Any],
    http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
    shared_http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    request_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if shared_http_client is not None:
        response = await shared_http_client.post(
            "/chat/completions",
            json=payload,
            headers=request_headers,
            timeout=timeout_s,
        )
    elif http_client_cls is None:
        shared_client = get_shared_chat_completion_client(
            api_base_url=_normalize_api_base_url(api_base_url)
        )
        response = await shared_client.post(
            "/chat/completions",
            json=payload,
            headers=request_headers,
            timeout=timeout_s,
        )
    else:
        async with http_client_cls(
            base_url=_normalize_api_base_url(api_base_url),
            timeout=timeout_s,
        ) as client:
            response = await client.post(
                "/chat/completions",
                json=payload,
                headers=request_headers,
            )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("OpenAI API response must be a JSON object.")
    return data
