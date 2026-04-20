from __future__ import annotations

import pytest
from pydantic import ValidationError

from botcheck_api.runs.runs import PlaygroundRunCreate, RunCreate


def test_mock_playground_requires_system_prompt() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundRunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "playground_mode": "mock",
            }
        )

    assert "system_prompt is required for mock playground runs" in str(exc_info.value)


def test_mock_playground_rejects_transport_profile() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundRunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "playground_mode": "mock",
                "system_prompt": "You are a helper.",
                "transport_profile_id": "dest_http",
            }
        )

    assert "transport_profile_id is not allowed for mock playground runs" in str(exc_info.value)


def test_direct_http_playground_requires_transport_profile() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundRunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "playground_mode": "direct_http",
            }
        )

    assert "transport_profile_id is required for direct_http playground runs" in str(exc_info.value)


def test_direct_http_playground_rejects_mock_only_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PlaygroundRunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "playground_mode": "direct_http",
                "transport_profile_id": "dest_http",
                "system_prompt": "You are a helper.",
                "tool_stubs": {"lookup": {"ok": True}},
            }
        )

    message = str(exc_info.value)
    assert (
        "system_prompt is not allowed for direct_http playground runs" in message
        or "tool_stubs are not allowed for direct_http playground runs" in message
    )


def test_direct_http_playground_normalizes_blank_strings() -> None:
    body = PlaygroundRunCreate.model_validate(
        {
            "scenario_id": "scenario_1",
            "playground_mode": "direct_http",
            "transport_profile_id": "  dest_http  ",
        }
    )

    assert body.transport_profile_id == "dest_http"


def test_run_create_supports_ad_hoc_trunk_pool() -> None:
    body = RunCreate.model_validate(
        {
            "scenario_id": "scenario_1",
            "dial_target": "  +441234567890  ",
            "trunk_pool_id": "  pool_uk  ",
        }
    )

    assert body.dial_target == "+441234567890"
    assert body.trunk_pool_id == "pool_uk"


def test_run_create_rejects_trunk_pool_with_transport_profile() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "dial_target": "+441234567890",
                "trunk_pool_id": "pool_uk",
                "transport_profile_id": "dest_sip",
            }
        )

    assert "trunk_pool_id cannot be combined with transport_profile_id" in str(exc_info.value)


def test_run_create_requires_dial_target_for_trunk_pool() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RunCreate.model_validate(
            {
                "scenario_id": "scenario_1",
                "trunk_pool_id": "pool_uk",
            }
        )

    assert "dial_target is required when trunk_pool_id is provided" in str(exc_info.value)
