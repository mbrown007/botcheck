from botcheck_scenarios.decision_slots import (
    DECISION_DEFAULT_SLOT,
    DECISION_OUTPUT_HANDLE_PREFIX,
    decision_handle_id,
    decision_output_slots,
    decision_path_slot,
    decision_path_slot_index,
    is_default_decision_slot,
    is_path_decision_slot,
    parse_decision_handle_slot,
)


def test_decision_output_slots_includes_default_and_paths() -> None:
    assert decision_output_slots(1) == ["default"]
    assert decision_output_slots(3) == ["default", "path_1", "path_2"]
    assert decision_output_slots(0) == ["default"]


def test_decision_path_slot_clamps_to_one() -> None:
    assert decision_path_slot(1) == "path_1"
    assert decision_path_slot(0) == "path_1"


def test_decision_handle_round_trip() -> None:
    slot = "path_2"
    handle_id = decision_handle_id(slot)
    assert handle_id == f"{DECISION_OUTPUT_HANDLE_PREFIX}{slot}"
    assert parse_decision_handle_slot(handle_id) == slot
    assert parse_decision_handle_slot("") is None
    assert parse_decision_handle_slot("unexpected:path_2") is None


def test_decision_slot_predicates() -> None:
    assert is_default_decision_slot(DECISION_DEFAULT_SLOT)
    assert is_default_decision_slot(" DEFAULT ")
    assert not is_default_decision_slot("path_1")
    assert is_path_decision_slot("path_1")
    assert is_path_decision_slot(" PATH_3 ")
    assert not is_path_decision_slot("default")
    assert not is_path_decision_slot("path_")


def test_decision_path_slot_index_parses_and_rejects_invalid() -> None:
    assert decision_path_slot_index("path_3") == 3
    assert decision_path_slot_index(" PATH_7 ") == 7
    assert decision_path_slot_index("path_0") is None
    assert decision_path_slot_index("default") is None
