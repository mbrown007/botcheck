from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import openai
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

logger = logging.getLogger("botcheck.api.runs.playground_tools")

_EXTRACT_MODEL = "gpt-4o-mini"
_EXTRACT_TIMEOUT_S = 10.0
_EXTRACT_SYSTEM_PROMPT = """\
You extract callable tool signatures from bot system prompts.

Be conservative:
- Only include tools that are explicitly described as callable tools, functions,
  actions, APIs, or lookups the bot can use.
- If the prompt is ambiguous or mentions no callable tools, return [].
- Do not invent hidden tools or internal capabilities.

Return JSON only.
Return a top-level array where each entry has:
{
  "name": "<tool_name>",
  "description": "<short description>",
  "parameters": {
    "type": "object",
    "properties": {
      "<param_name>": {"type": "string", "description": "<optional>"}
    },
    "required": ["<param_name>"]
  }
}

If a tool has no described parameters, return:
{"type":"object","properties":{},"required":[]}
"""


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


class _PlaygroundToolParameters(BaseModel):
    type: str = "object"
    properties: dict[str, object] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class _PlaygroundToolPayload(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)

    @field_validator("parameters", mode="before")
    @classmethod
    def _default_invalid_parameters(cls, value: object) -> dict[str, object]:
        # Coerce any non-dict (including None and LLM-hallucinated scalars) to an
        # empty dict so the model always provides a valid parameters schema.
        return value if isinstance(value, dict) else {}


_TOOL_ARRAY_JSON = TypeAdapter(list[object] | dict[str, object])


def _parse_tool_array(raw_text: str) -> list[dict[str, object]]:
    candidate = (raw_text or "").strip()
    if not candidate:
        return []
    stripped = (
        candidate.removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    try:
        payload = _TOOL_ARRAY_JSON.validate_json(stripped)
    except ValidationError:
        logger.warning("playground_extract_tools_unparseable_json")
        return []

    if isinstance(payload, dict):
        payload = payload.get("tools", [])
    if not isinstance(payload, list):
        return []

    tools: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            parsed = _PlaygroundToolPayload.model_validate(entry)
        except ValidationError:
            continue
        name = _normalize_text(parsed.name)
        if not name:
            continue
        description = _normalize_text(parsed.description)
        parameters = _PlaygroundToolParameters.model_validate(parsed.parameters).model_dump()

        tools.append(
            {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )
    return tools


_GENERATE_MODEL = "gpt-4o-mini"
_GENERATE_TIMEOUT_S = 15.0
_GENERATE_SYSTEM_PROMPT = """\
You generate realistic stub return values for tool functions used by an AI assistant.

Rules:
- Produce plausible values that are consistent with the scenario described by the user.
- Each stub must be a valid JSON object (even if empty).
- Tools with no parameters default to {}.
- Do not invent data that contradicts the scenario context.
- All string values must be plausible for the scenario domain.

Return JSON only. Return a single top-level object keyed by tool name:
{
  "tool_name": { "<param_name>": "<value>", ... },
  ...
}
"""


_STUB_MAP_JSON = TypeAdapter(dict[str, object])


def _parse_stub_map(
    raw_text: str, tool_names: list[str]
) -> dict[str, dict[str, object]]:
    candidate = (raw_text or "").strip()
    stripped = (
        candidate.removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    try:
        payload = _STUB_MAP_JSON.validate_json(stripped)
    except ValidationError:
        logger.warning("playground_generate_stubs_unparseable_json")
        return {name: {} for name in tool_names}

    result: dict[str, dict[str, object]] = {}
    for name in tool_names:
        entry = payload.get(name)
        if not isinstance(entry, dict):
            result[name] = {}
            continue
        result[name] = entry
    return result


async def generate_stub_values(
    *,
    tools: list[dict[str, object]],
    scenario_summary: str,
    openai_api_key: str,
    model: str = _GENERATE_MODEL,
) -> dict[str, dict[str, object]]:
    """Return a stub map ``{tool_name: {param: value}}`` for each tool."""
    if not tools:
        return {}
    if not _normalize_text(openai_api_key):
        raise RuntimeError("OpenAI API key is required for playground stub generation")

    tool_names = [str(t.get("name") or "") for t in tools if t.get("name")]
    # Tools with no parameters can be resolved immediately.
    no_param_names = {
        name
        for tool, name in zip(tools, tool_names)
        if not (
            isinstance(tool.get("parameters"), dict)
            and tool["parameters"].get("properties")
        )
    }

    summary = _normalize_text(scenario_summary) or "generic assistant scenario"
    tool_descriptions = json.dumps(
        [
            {
                "name": str(t.get("name") or ""),
                "description": str(t.get("description") or ""),
                "parameters": t.get("parameters") or {},
            }
            for t in tools
            if t.get("name")
        ],
        indent=2,
    )

    client = openai.AsyncOpenAI(api_key=openai_api_key, timeout=_GENERATE_TIMEOUT_S)
    async with asyncio.timeout(_GENERATE_TIMEOUT_S):
        response = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=1600,
            messages=[
                {"role": "system", "content": _GENERATE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Scenario context: {summary}\n\n"
                        f"Tools:\n{tool_descriptions}\n\n"
                        "Generate one realistic stub return value object for each tool. "
                        "Return only the JSON object keyed by tool name."
                    ),
                },
            ],
        )

    content = response.choices[0].message.content or ""
    stubs = _parse_stub_map(content, tool_names)

    # Ensure no-parameter tools always return {}
    for name in no_param_names:
        stubs[name] = {}
    return stubs


async def extract_tool_signatures(
    *,
    system_prompt: str | None,
    openai_api_key: str,
    model: str = _EXTRACT_MODEL,
) -> list[dict[str, object]]:
    prompt = _normalize_text(system_prompt)
    if not prompt:
        return []
    if not _normalize_text(openai_api_key):
        raise RuntimeError("OpenAI API key is required for playground tool extraction")

    client = openai.AsyncOpenAI(api_key=openai_api_key, timeout=_EXTRACT_TIMEOUT_S)
    async with asyncio.timeout(_EXTRACT_TIMEOUT_S):
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract only the explicitly described callable tools from this "
                        "system prompt. Return [] if none are explicitly described.\n\n"
                        f"{prompt}"
                    ),
                },
            ],
        )

    content = response.choices[0].message.content or ""
    return _parse_tool_array(content)
