from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from botcheck_api.runs.service_playground_tools import (
    extract_tool_signatures,
    generate_stub_values,
)


def _response_with_content(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return self._response


class _FakeAsyncOpenAI:
    def __init__(self, *, response):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response))


@pytest.mark.asyncio
async def test_extract_tool_signatures_returns_multiple_tools(monkeypatch):
    response = _response_with_content(
        """
        [
          {
            "name": "lookup_account",
            "description": "Look up the customer account.",
            "parameters": {
              "type": "object",
              "properties": {
                "account_id": {"type": "string", "description": "Customer ID"}
              },
              "required": ["account_id"]
            }
          },
          {
            "name": "transfer_call",
            "description": "Transfer the caller to billing.",
            "parameters": {"type": "object", "properties": {}, "required": []}
          }
        ]
        """
    )

    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(response=response),
    )

    tools = await extract_tool_signatures(
        system_prompt=(
            "You can call lookup_account(account_id) and transfer_call() "
            "when the customer requests billing."
        ),
        openai_api_key="test-openai-key",
    )

    assert [tool["name"] for tool in tools] == ["lookup_account", "transfer_call"]
    assert tools[0]["parameters"]["required"] == ["account_id"]


@pytest.mark.asyncio
async def test_extract_tool_signatures_accepts_tools_wrapper_and_defaults_invalid_parameters(
    monkeypatch,
):
    response = _response_with_content(
        """
        {
          "tools": [
            {
              "name": " lookup_account ",
              "description": " Look up the customer account. ",
              "parameters": "not-an-object"
            }
          ]
        }
        """
    )

    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(response=response),
    )

    tools = await extract_tool_signatures(
        system_prompt="You can call lookup_account(account_id).",
        openai_api_key="test-openai-key",
    )

    assert tools == [
        {
            "name": "lookup_account",
            "description": "Look up the customer account.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    ]


@pytest.mark.asyncio
async def test_extract_tool_signatures_returns_empty_for_blank_prompt(monkeypatch):
    called = False

    def _fake_client(**kwargs):
        nonlocal called
        called = True
        return _FakeAsyncOpenAI(response=_response_with_content("[]"))

    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        _fake_client,
    )

    tools = await extract_tool_signatures(
        system_prompt="   ",
        openai_api_key="test-openai-key",
    )

    assert tools == []
    assert called is False


@pytest.mark.asyncio
async def test_extract_tool_signatures_returns_empty_for_explicit_no_tools(monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(response=_response_with_content("[]")),
    )

    tools = await extract_tool_signatures(
        system_prompt="You are a receptionist bot. You never call tools.",
        openai_api_key="test-openai-key",
    )

    assert tools == []


@pytest.mark.asyncio
async def test_generate_stub_values_returns_empty_for_no_tools(monkeypatch):
    called = False

    def _fake_client(**kwargs):
        nonlocal called
        called = True
        return _FakeAsyncOpenAI(response=_response_with_content("{}"))

    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        _fake_client,
    )

    stubs = await generate_stub_values(
        tools=[],
        scenario_summary="Billing bot scenario",
        openai_api_key="test-openai-key",
    )

    assert stubs == {}
    assert called is False


@pytest.mark.asyncio
async def test_generate_stub_values_scenario_grounded_example(monkeypatch):
    """Stub values are plausible for a billing-bot scenario and keyed by tool name."""
    llm_response = '{"lookup_account": {"account_id": "ACC-001"}, "transfer_call": {}}'
    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(response=_response_with_content(llm_response)),
    )

    tools = [
        {
            "name": "lookup_account",
            "description": "Look up a customer account.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
        {
            "name": "transfer_call",
            "description": "Transfer to billing queue.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ]

    stubs = await generate_stub_values(
        tools=tools,
        scenario_summary="Adversarial caller trying to extract account details from billing bot.",
        openai_api_key="test-openai-key",
    )

    assert set(stubs.keys()) == {"lookup_account", "transfer_call"}
    assert isinstance(stubs["lookup_account"], dict)
    # transfer_call has no parameters — stub must be {}
    assert stubs["transfer_call"] == {}


@pytest.mark.asyncio
async def test_generate_stub_values_no_param_tools_always_empty(monkeypatch):
    """Tools with no properties are forced to {} regardless of LLM response."""
    llm_response = '{"ping": {"unexpected": "value"}}'
    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(response=_response_with_content(llm_response)),
    )

    tools = [
        {
            "name": "ping",
            "description": "No-op ping.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    ]

    stubs = await generate_stub_values(
        tools=tools,
        scenario_summary="Health check probe",
        openai_api_key="test-openai-key",
    )

    assert stubs["ping"] == {}


@pytest.mark.asyncio
async def test_generate_stub_values_handles_unparseable_json(monkeypatch):
    """Unparseable JSON returns empty dict per tool name."""
    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(
            response=_response_with_content("not valid json at all")
        ),
    )

    tools = [
        {
            "name": "get_policy",
            "description": "Get policy.",
            "parameters": {
                "type": "object",
                "properties": {"policy_id": {"type": "string"}},
                "required": ["policy_id"],
            },
        }
    ]

    stubs = await generate_stub_values(
        tools=tools,
        scenario_summary="Insurance bot",
        openai_api_key="test-openai-key",
    )

    assert stubs == {"get_policy": {}}


@pytest.mark.asyncio
async def test_generate_stub_values_ignores_non_object_tool_entries(monkeypatch):
    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _FakeAsyncOpenAI(
            response=_response_with_content('{"get_policy": "unexpected"}')
        ),
    )

    stubs = await generate_stub_values(
        tools=[
            {
                "name": "get_policy",
                "description": "Get policy.",
                "parameters": {
                    "type": "object",
                    "properties": {"policy_id": {"type": "string"}},
                    "required": ["policy_id"],
                },
            }
        ],
        scenario_summary="Insurance bot",
        openai_api_key="test-openai-key",
    )

    assert stubs == {"get_policy": {}}


@pytest.mark.asyncio
async def test_extract_tool_signatures_propagates_timeout(monkeypatch):
    class _TimeoutCompletions:
        async def create(self, **kwargs):
            raise TimeoutError("timed out")

    class _TimeoutClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_TimeoutCompletions())

    monkeypatch.setattr(
        "botcheck_api.runs.service_playground_tools.openai.AsyncOpenAI",
        lambda **_: _TimeoutClient(),
    )

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await extract_tool_signatures(
            system_prompt="You can call lookup_account(account_id).",
            openai_api_key="test-openai-key",
        )
