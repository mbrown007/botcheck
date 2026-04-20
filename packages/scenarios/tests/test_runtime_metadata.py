import pytest
from pydantic import ValidationError

from botcheck_scenarios import (
    AIRunContextSnapshot,
    AIRunDispatchContext,
    RunExecutionMetadata,
    RunRoomMetadata,
)


def test_ai_run_context_snapshot_serializes_room_metadata_keys() -> None:
    snapshot = AIRunContextSnapshot(
        dataset_input="Need help with a delayed flight",
        expected_output="Confirm delay and offer next steps",
        persona_id="persona_traveler",
        persona_name="Delayed Traveler",
        scenario_brief="Traveler is calling about a missed connection",
        scenario_objective="Assess whether the bot handles delay support clearly",
        opening_strategy="wait_for_bot_greeting",
    )

    assert snapshot.room_metadata_items() == {
        "ai_dataset_input": "Need help with a delayed flight",
        "ai_expected_output": "Confirm delay and offer next steps",
        "ai_persona_id": "persona_traveler",
        "ai_persona_name": "Delayed Traveler",
        "ai_scenario_brief": "Traveler is calling about a missed connection",
        "ai_scenario_objective": "Assess whether the bot handles delay support clearly",
        "ai_opening_strategy": "wait_for_bot_greeting",
    }


def test_run_room_metadata_round_trips_json_with_extra_keys() -> None:
    metadata = RunRoomMetadata(
        run_id="run_abc123",
        scenario_id="scenario_alpha",
        scenario_kind="ai",
        tenant_id="tenant_a",
        trigger_source="scheduled",
        run_type="standard",
        bot_protocol="sip",
        transport="sip",
        dial_target="+441234567890",
        effective_tts_voice="openai:alloy",
        traceparent="00-abc-123-01",
        custom_marker="kept",
    )

    payload = metadata.model_dump_json(exclude_none=True)
    reparsed = RunRoomMetadata.model_validate_json(payload)

    assert reparsed.run_id == "run_abc123"
    assert reparsed.transport == "sip"
    assert reparsed.bot_protocol == "sip"
    assert reparsed.traceparent == "00-abc-123-01"
    assert reparsed.model_dump(mode="json", exclude_none=True)["custom_marker"] == "kept"


def test_ai_run_dispatch_context_normalizes_and_derives_fields() -> None:
    dispatch = AIRunDispatchContext.model_validate(
        {
            "ai_persona_name": "  Traveler  ",
            "ai_expected_output": "  fallback objective  ",
            "ai_scenario_brief": "  brief  ",
            "ai_scenario_objective": "  primary objective  ",
            "ai_opening_strategy": "  caller_opens  ",
        }
    )

    assert dispatch.ai_persona_name == "Traveler"
    assert dispatch.objective_hint() == "primary objective"
    assert dispatch.effective_opening_strategy() == "caller_opens"


def test_ai_run_dispatch_context_defaults_opening_strategy() -> None:
    dispatch = AIRunDispatchContext.model_validate({})

    assert dispatch.objective_hint() == ""
    assert dispatch.effective_opening_strategy() == "wait_for_bot_greeting"


def test_ai_run_dispatch_context_objective_hint_fallback_chain() -> None:
    # Falls back to brief when objective is absent
    brief_only = AIRunDispatchContext.model_validate(
        {"ai_scenario_brief": "brief text", "ai_expected_output": "expected"}
    )
    assert brief_only.objective_hint() == "brief text"

    # Falls back to expected_output when both objective fields are absent
    expected_only = AIRunDispatchContext.model_validate(
        {"ai_expected_output": "expected text"}
    )
    assert expected_only.objective_hint() == "expected text"


def test_ai_run_dispatch_context_normalizes_whitespace_only_to_none() -> None:
    dispatch = AIRunDispatchContext.model_validate({"ai_persona_name": "   "})
    assert dispatch.ai_persona_name is None


def test_ai_run_dispatch_context_ignores_extra_keys() -> None:
    dispatch = AIRunDispatchContext.model_validate(
        {"ai_persona_id": "p1", "run_id": "r1", "unknown_future_field": "v"}
    )
    assert dispatch.ai_persona_id == "p1"


def test_ai_run_context_snapshot_truncates_long_fields() -> None:
    long_value = "x" * 2000
    snapshot = AIRunContextSnapshot(
        dataset_input=long_value,
        expected_output="short",
        persona_id="p1",
    )
    items = snapshot.room_metadata_items()
    assert len(items["ai_dataset_input"]) == 1200
    assert items["ai_expected_output"] == "short"


def test_run_room_metadata_rejects_empty_run_id() -> None:
    with pytest.raises(ValidationError):
        RunRoomMetadata(run_id="", scenario_id="scenario_x")


def test_run_room_metadata_rejects_empty_scenario_id() -> None:
    with pytest.raises(ValidationError):
        RunRoomMetadata(run_id="run_x", scenario_id="")


def test_run_room_metadata_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        RunRoomMetadata.model_validate_json("{}")


def test_run_execution_metadata_normalizes_transport_and_kind() -> None:
    metadata = RunExecutionMetadata.model_validate(
        {
            "scenario_kind": " AI ",
            "ai_opening_strategy": " Caller_Opens ",
            "run_type": " playground ",
            "bot_protocol": " mock ",
            "transport": " http ",
        }
    )

    assert metadata.normalized_scenario_kind() == "ai"
    assert metadata.effective_opening_strategy() == "caller_opens"
    assert metadata.transport_protocol() == "http"
    assert metadata.normalized_run_type() == "playground"


def test_run_execution_metadata_none_defaults() -> None:
    empty = RunExecutionMetadata.model_validate({})

    assert empty.normalized_scenario_kind() == ""
    # Default must be "wait_for_bot_greeting" so AI runs skip initial drain
    assert empty.effective_opening_strategy() == "wait_for_bot_greeting"
    assert empty.transport_protocol() == ""
    assert empty.normalized_run_type() == ""


def test_run_execution_metadata_transport_protocol_bot_protocol_fallback() -> None:
    meta = RunExecutionMetadata.model_validate({"bot_protocol": "mock"})
    assert meta.transport_protocol() == "mock"


def test_run_execution_metadata_ignores_extra_keys() -> None:
    meta = RunExecutionMetadata.model_validate(
        {"scenario_kind": "ai", "run_id": "r1", "unknown_field": "v"}
    )
    assert meta.normalized_scenario_kind() == "ai"
