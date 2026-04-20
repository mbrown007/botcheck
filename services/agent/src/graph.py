from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from botcheck_scenarios import ScenarioBlock, ScenarioDefinition


class HarnessLoopError(RuntimeError):
    """Raised when a turn is visited more than its configured max_visits."""

    def __init__(
        self,
        *,
        turn_id: str,
        visit: int,
        max_visits: int,
        effective_cap: int,
    ) -> None:
        super().__init__(f"Turn '{turn_id}' exceeded max_visits={max_visits}")
        self.turn_id = turn_id
        self.visit = visit
        self.max_visits = max_visits
        self.effective_cap = effective_cap


class HarnessMaxTurnsError(RuntimeError):
    """Raised when traversal exceeds the effective run-level turn cap."""

    def __init__(
        self,
        *,
        effective_cap: int,
        turn_id: str | None = None,
        visit: int | None = None,
    ) -> None:
        super().__init__(f"Scenario exceeded effective max_total_turns={effective_cap}")
        self.effective_cap = effective_cap
        self.turn_id = turn_id
        self.visit = visit


@dataclass(frozen=True)
class TurnNode:
    turn: ScenarioBlock
    successors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionStep:
    turn: ScenarioBlock
    visit: int


class ScenarioGraph:
    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._nodes: dict[str, TurnNode] = {}
        self._entry: str = scenario.turns[0].id
        self._build(scenario)

    def _build(self, scenario: ScenarioDefinition) -> None:
        from botcheck_scenarios import HangupBlock, TimeRouteBlock

        turns = scenario.turns
        for idx, turn in enumerate(turns):
            successors: dict[str, str] = {}
            # HangupBlock is always terminal — never wire a fallthrough successor,
            # even when it appears mid-list. The loop executor breaks on it directly.
            if isinstance(turn, HangupBlock):
                self._nodes[turn.id] = TurnNode(turn=turn, successors=successors)
                continue
            if isinstance(turn, TimeRouteBlock):
                for window in turn.windows:
                    successors[window.label] = window.next
                successors["default"] = turn.default
                self._nodes[turn.id] = TurnNode(turn=turn, successors=successors)
                continue
            if turn.branching is not None:
                for case in turn.branching.cases:
                    successors[case.condition] = case.next
                successors["default"] = turn.branching.default
            elif turn.next is not None:
                successors["default"] = turn.next
            elif idx + 1 < len(turns):
                successors["default"] = turns[idx + 1].id
            self._nodes[turn.id] = TurnNode(turn=turn, successors=successors)

    def entry(self) -> TurnNode:
        return self._nodes[self._entry]

    def resolve_next(self, current_id: str, chosen_condition: str) -> TurnNode | None:
        node = self._nodes[current_id]
        next_id = node.successors.get(chosen_condition, node.successors.get("default"))
        if next_id is None:
            return None
        return self._nodes[next_id]


class GraphTraversal:
    """
    Runtime traversal cursor for graph execution.

    Call consume_current() once per executed turn, then advance() with the chosen
    condition for branching turns (or default).
    """

    def __init__(self, scenario: ScenarioDefinition, *, max_total_turns_hard_cap: int) -> None:
        self._graph = ScenarioGraph(scenario)
        self._current: TurnNode | None = self._graph.entry()
        self._visit_counts: dict[str, int] = defaultdict(int)
        self._effective_cap = min(scenario.config.max_total_turns, max_total_turns_hard_cap)
        self._executed_turns = 0

    @property
    def effective_cap(self) -> int:
        return self._effective_cap

    def has_next(self) -> bool:
        return self._current is not None

    def consume_current(self) -> ExecutionStep:
        if self._current is None:
            raise StopIteration("Graph traversal has no remaining nodes")
        if self._executed_turns >= self._effective_cap:
            next_turn = self._current.turn
            raise HarnessMaxTurnsError(
                effective_cap=self._effective_cap,
                turn_id=next_turn.id,
                visit=self._visit_counts[next_turn.id] + 1,
            )

        turn = self._current.turn
        self._visit_counts[turn.id] += 1
        visit = self._visit_counts[turn.id]
        if turn.max_visits > 0 and visit > turn.max_visits:
            raise HarnessLoopError(
                turn_id=turn.id,
                visit=visit,
                max_visits=turn.max_visits,
                effective_cap=self._effective_cap,
            )

        self._executed_turns += 1
        return ExecutionStep(turn=turn, visit=visit)

    def advance(self, chosen_condition: str = "default") -> None:
        if self._current is None:
            return
        self._current = self._graph.resolve_next(self._current.turn.id, chosen_condition)


def build_turn_sequence(
    scenario: ScenarioDefinition,
    *,
    max_total_turns_hard_cap: int,
    select_condition: Callable[[ScenarioBlock, list[str]], str] | None = None,
) -> list[ScenarioBlock]:
    """
    Build execution order for a scenario using graph traversal semantics.

    When select_condition is omitted, branching turns fall through to `default`.
    """
    traversal = GraphTraversal(
        scenario,
        max_total_turns_hard_cap=max_total_turns_hard_cap,
    )
    sequence: list[ScenarioBlock] = []

    while traversal.has_next():
        step = traversal.consume_current()
        turn = step.turn
        sequence.append(turn)
        chosen = "default"
        if turn.branching is not None:
            conditions = [case.condition for case in turn.branching.cases]
            if select_condition is not None:
                chosen = select_condition(turn, conditions)
        traversal.advance(chosen)

    return sequence
