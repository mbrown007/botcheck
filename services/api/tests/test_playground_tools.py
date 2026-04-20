from __future__ import annotations

from unittest.mock import AsyncMock

from botcheck_api.config import settings


def _role_auth_headers(role: str) -> dict[str, str]:
    from datetime import UTC, datetime

    from jose import jwt

    token = jwt.encode(
        {
            "sub": f"{role}-playground-tools-user",
            "tenant_id": settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "amr": ["pwd", "dev_token"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_extract_tools_returns_tool_list(client, monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.runs_lifecycle.extract_tool_signatures",
        AsyncMock(
            return_value=[
                {
                    "name": "lookup_account",
                    "description": "Look up a customer account.",
                    "parameters": {
                        "type": "object",
                        "properties": {"account_id": {"type": "string"}},
                        "required": ["account_id"],
                    },
                }
            ]
        ),
    )

    resp = await client.post(
        "/runs/playground/extract-tools",
        json={"system_prompt": "You can call lookup_account(account_id)."},
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "name": "lookup_account",
            "description": "Look up a customer account.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        }
    ]


async def test_extract_tools_degrades_to_empty_list_on_failure(client, monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.runs_lifecycle.extract_tool_signatures",
        AsyncMock(side_effect=TimeoutError("timed out")),
    )

    resp = await client.post(
        "/runs/playground/extract-tools",
        json={"system_prompt": "You can call lookup_account(account_id)."},
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_extract_tools_returns_empty_list_for_blank_prompt(client):
    resp = await client.post(
        "/runs/playground/extract-tools",
        json={"system_prompt": "   "},
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_generate_stubs_returns_stub_map(client, monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.runs_lifecycle.generate_stub_values",
        AsyncMock(
            return_value={
                "lookup_account": {"account_id": "ACC-001"},
                "transfer_call": {},
            }
        ),
    )

    resp = await client.post(
        "/runs/playground/generate-stubs",
        json={
            "tools": [
                {
                    "name": "lookup_account",
                    "description": "Look up account.",
                    "parameters": {
                        "type": "object",
                        "properties": {"account_id": {"type": "string"}},
                        "required": ["account_id"],
                    },
                },
                {
                    "name": "transfer_call",
                    "description": "Transfer to billing.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            ],
            "scenario_summary": "Adversarial billing-bot test",
        },
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["lookup_account"]["account_id"] == "ACC-001"
    assert body["transfer_call"] == {}


async def test_generate_stubs_returns_empty_for_no_tools(client, monkeypatch):
    resp = await client.post(
        "/runs/playground/generate-stubs",
        json={"tools": [], "scenario_summary": "some scenario"},
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    assert resp.json() == {}


async def test_generate_stubs_degrades_on_llm_failure(client, monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.runs_lifecycle.generate_stub_values",
        AsyncMock(side_effect=TimeoutError("timed out")),
    )

    resp = await client.post(
        "/runs/playground/generate-stubs",
        json={
            "tools": [
                {
                    "name": "get_policy",
                    "description": "Fetch policy.",
                    "parameters": {
                        "type": "object",
                        "properties": {"policy_id": {"type": "string"}},
                        "required": ["policy_id"],
                    },
                }
            ],
            "scenario_summary": "Insurance bot",
        },
        headers=_role_auth_headers("editor"),
    )

    assert resp.status_code == 200
    # Degraded response: empty stubs per tool name
    assert resp.json() == {"get_policy": {}}
