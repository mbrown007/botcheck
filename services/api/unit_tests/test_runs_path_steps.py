"""Unit tests for judge taken-path extraction from run events."""

from botcheck_api.runs.service import build_taken_path_steps


def test_build_taken_path_steps_empty_when_no_turn_executed_events():
    events = [
        {"type": "run_created", "detail": {"source": "manual"}},
        {"type": "judge_enqueued", "detail": {"source": "harness_complete"}},
    ]
    assert build_taken_path_steps(events) == []


def test_build_taken_path_steps_orders_by_turn_number_and_dedupes():
    events = [
        {
            "type": "turn_executed",
            "detail": {"turn_id": "t2", "visit": 1, "turn_number": 2},
        },
        {
            "type": "turn_executed",
            "detail": {"turn_id": "t1", "visit": 1, "turn_number": 1},
        },
        {
            "type": "turn_executed",
            "detail": {"turn_id": "t1", "visit": 1, "turn_number": 1},
        },
    ]
    assert build_taken_path_steps(events) == [
        {"turn_id": "t1", "visit": 1, "turn_number": 1},
        {"turn_id": "t2", "visit": 1, "turn_number": 2},
    ]


def test_build_taken_path_steps_skips_invalid_details():
    events = [
        {"type": "turn_executed", "detail": {"turn_id": "", "visit": 1, "turn_number": 1}},
        {"type": "turn_executed", "detail": {"turn_id": "t1", "visit": 0, "turn_number": 1}},
        {"type": "turn_executed", "detail": {"turn_id": "t1", "visit": 1, "turn_number": 0}},
        {"type": "turn_executed", "detail": {"turn_id": "t1", "visit": 1, "turn_number": 1}},
    ]
    assert build_taken_path_steps(events) == [
        {"turn_id": "t1", "visit": 1, "turn_number": 1}
    ]
