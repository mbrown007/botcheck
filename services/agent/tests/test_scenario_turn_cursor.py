from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.scenario_turn_cursor import ScenarioTurnCursor
from src import scenario_turn_cursor


@dataclass
class _FakeStep:
    turn: object
    visit: int


class _FakeGraphTraversal:
    def __init__(self, steps: list[_FakeStep]) -> None:
        self._steps = list(steps)

    def has_next(self) -> bool:
        return len(self._steps) > 0

    def consume_current(self):
        return self._steps.pop(0)


def test_cursor_linear_mode_tracks_visits_per_turn_id() -> None:
    turn_a1 = SimpleNamespace(id="t_a")
    turn_b = SimpleNamespace(id="t_b")
    turn_a2 = SimpleNamespace(id="t_a")
    scenario = SimpleNamespace(turns=[turn_a1, turn_b, turn_a2])

    cursor = ScenarioTurnCursor(scenario=scenario, graph_traversal=None)

    assert cursor.next_step() == (turn_a1, 1)
    assert cursor.next_step() == (turn_b, 1)
    assert cursor.next_step() == (turn_a2, 2)
    assert cursor.next_step() is None


def test_cursor_graph_mode_delegates_to_graph_steps() -> None:
    step1 = _FakeStep(turn=SimpleNamespace(id="t1"), visit=1)
    step2 = _FakeStep(turn=SimpleNamespace(id="t2"), visit=3)
    graph = _FakeGraphTraversal([step1, step2])
    cursor = ScenarioTurnCursor(
        scenario=SimpleNamespace(turns=[]),
        graph_traversal=graph,
    )

    assert cursor.next_step() == (step1.turn, 1)
    assert cursor.next_step() == (step2.turn, 3)
    assert cursor.next_step() is None


def test_create_turn_cursor_disables_graph_mode() -> None:
    scenario = SimpleNamespace(turns=[SimpleNamespace(id="t1")])
    cursor, graph = scenario_turn_cursor.create_turn_cursor(
        scenario=scenario,
        enable_branching_graph=False,
        max_total_turns_hard_cap=50,
    )
    assert graph is None
    assert cursor.next_step() == (scenario.turns[0], 1)


def test_create_turn_cursor_enables_graph_mode(monkeypatch) -> None:
    created = {}

    class _FakeGraphTraversal:
        def __init__(self, scenario, *, max_total_turns_hard_cap: int) -> None:
            created["scenario"] = scenario
            created["cap"] = max_total_turns_hard_cap

        def has_next(self) -> bool:
            return False

        def consume_current(self):
            raise AssertionError("not expected")

    monkeypatch.setattr(scenario_turn_cursor, "GraphTraversal", _FakeGraphTraversal)
    scenario = SimpleNamespace(turns=[SimpleNamespace(id="t1")])
    cursor, graph = scenario_turn_cursor.create_turn_cursor(
        scenario=scenario,
        enable_branching_graph=True,
        max_total_turns_hard_cap=77,
    )
    assert graph is not None
    assert created == {"scenario": scenario, "cap": 77}
    assert cursor.next_step() is None
