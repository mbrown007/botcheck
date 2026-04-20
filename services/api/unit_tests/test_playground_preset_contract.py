from __future__ import annotations

import pytest
from pydantic import ValidationError

from botcheck_api.runs.runs import (
    PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH,
    PlaygroundPresetWrite,
)


def test_playground_preset_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "playground_mode": "mock",
                "system_prompt": "You are a test agent.",
            }
        )

    assert "Exactly one of scenario_id or ai_scenario_id is required" in str(exc_info.value)


def test_playground_preset_mock_requires_system_prompt() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "scenario_id": "scenario_1",
                "playground_mode": "mock",
            }
        )

    assert "system_prompt is required for mock playground runs" in str(exc_info.value)


def test_playground_preset_direct_http_requires_transport_profile() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "scenario_id": "scenario_1",
                "playground_mode": "direct_http",
            }
        )

    assert "transport_profile_id is required for direct_http playground runs" in str(exc_info.value)


def test_playground_preset_direct_http_rejects_system_prompt() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "scenario_id": "scenario_1",
                "playground_mode": "direct_http",
                "transport_profile_id": "dest_http_1",
                "system_prompt": "You are a helper.",
            }
        )

    assert "system_prompt is not allowed for direct_http playground runs" in str(exc_info.value)


def test_playground_preset_direct_http_rejects_tool_stubs() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "scenario_id": "scenario_1",
                "playground_mode": "direct_http",
                "transport_profile_id": "dest_http_1",
                "tool_stubs": {"lookup_account": {"ok": True}},
            }
        )

    assert "tool_stubs are not allowed for direct_http playground runs" in str(exc_info.value)


def test_playground_preset_normalizes_blank_values() -> None:
    body = PlaygroundPresetWrite.model_validate(
        {
            "name": "  Demo Preset  ",
            "scenario_id": "scenario_1",
            "playground_mode": "mock",
            "system_prompt": "  You are a helper.  ",
            "description": "   ",
            "tool_stubs": {" lookup_account ": {"ok": True}, "   ": {}},
        }
    )

    assert body.name == "Demo Preset"
    assert body.description is None
    assert body.system_prompt == "You are a helper."
    assert body.tool_stubs == {"lookup_account": {"ok": True}}


def test_playground_preset_applies_same_system_prompt_limit_as_runs() -> None:
    with pytest.raises(ValidationError):
        PlaygroundPresetWrite.model_validate(
            {
                "name": "Preset A",
                "scenario_id": "scenario_1",
                "playground_mode": "mock",
                "system_prompt": "x" * (PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH + 1),
            }
        )
