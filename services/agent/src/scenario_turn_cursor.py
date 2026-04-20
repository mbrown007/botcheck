from __future__ import annotations

from collections import defaultdict

from .graph import GraphTraversal


class ScenarioTurnCursor:
    def __init__(self, *, scenario, graph_traversal=None) -> None:
        self._scenario = scenario
        self._graph_traversal = graph_traversal
        self._linear_idx = 0
        self._linear_turn_visit_counts: dict[str, int] = defaultdict(int)

    def next_step(self):
        if self._graph_traversal is not None:
            if not self._graph_traversal.has_next():
                return None
            step = self._graph_traversal.consume_current()
            return step.turn, step.visit

        if self._linear_idx >= len(self._scenario.turns):
            return None
        turn_def = self._scenario.turns[self._linear_idx]
        self._linear_idx += 1
        self._linear_turn_visit_counts[turn_def.id] += 1
        turn_visit = self._linear_turn_visit_counts[turn_def.id]
        return turn_def, turn_visit


def create_turn_cursor(
    *,
    scenario,
    enable_branching_graph: bool,
    max_total_turns_hard_cap: int,
) -> tuple[ScenarioTurnCursor, GraphTraversal | None]:
    graph_traversal = (
        GraphTraversal(
            scenario,
            max_total_turns_hard_cap=max_total_turns_hard_cap,
        )
        if enable_branching_graph
        else None
    )
    return (
        ScenarioTurnCursor(
            scenario=scenario,
            graph_traversal=graph_traversal,
        ),
        graph_traversal,
    )
