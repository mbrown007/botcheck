"""Focused unit tests for loop-guard parsing in runs router."""

from botcheck_api.runs.service import parse_loop_guard_event_detail


def test_parse_loop_guard_event_detail_rejects_unknown_guard():
    payload = {
        "guard": "unknown_guard",
        "turn_id": "t1",
        "visit": 2,
        "effective_cap": 50,
    }
    detail = parse_loop_guard_event_detail(
        payload,
        end_reason="per_turn_loop_limit",
        end_source="harness",
    )
    assert detail is None


def test_parse_loop_guard_event_detail_parses_per_turn_loop_limit():
    payload = {
        "guard": "per_turn_loop_limit",
        "turn_id": "t1",
        "visit": 2,
        "max_visits": 1,
        "effective_cap": 50,
    }
    detail = parse_loop_guard_event_detail(
        payload,
        end_reason="per_turn_loop_limit",
        end_source="harness",
    )
    assert detail == {
        "source": "harness_fail",
        "guard": "per_turn_loop_limit",
        "end_reason": "per_turn_loop_limit",
        "end_source": "harness",
        "turn_id": "t1",
        "visit": 2,
        "effective_cap": 50,
        "max_visits": 1,
    }


def test_parse_loop_guard_event_detail_parses_max_turns_reached_minimal():
    payload = {
        "guard": "max_turns_reached",
        "effective_cap": 25,
        "turn_id": " ",
        "visit": 0,
    }
    detail = parse_loop_guard_event_detail(
        payload,
        end_reason="max_turns_reached",
        end_source="harness",
    )
    assert detail == {
        "source": "harness_fail",
        "guard": "max_turns_reached",
        "end_reason": "max_turns_reached",
        "end_source": "harness",
        "effective_cap": 25,
    }
