import type { ScenarioDefinition, ScenarioTurn } from "@/lib/api/types";
import {
  getScenarioTurnKind,
  getScenarioTurnSpeaker,
  getScenarioTurnText,
} from "@/lib/scenario-turns";

import type { PlaygroundStreamEvent } from "@/lib/playground-stream";

export type PlaygroundProgressStatus =
  | "pending"
  | "active"
  | "passed"
  | "failed"
  | "skipped";

interface PlaygroundProgressCaseState {
  condition: string;
  status: "selected" | "dimmed" | "pending";
}

export interface PlaygroundProgressNode {
  turnId: string;
  speaker: "harness" | "bot";
  textPreview: string;
  status: PlaygroundProgressStatus;
  statusLabel: string;
  caseStates: PlaygroundProgressCaseState[];
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function summarizeTurnText(turn: ScenarioTurn): string {
  const text = getScenarioTurnText(turn).trim();
  if (!text) {
    if (getScenarioTurnKind(turn) === "hangup") {
      return "Hang up";
    }
    return getScenarioTurnSpeaker(turn) === "bot"
      ? "Bot response"
      : "Awaiting harness prompt";
  }
  return text.length > 88 ? `${text.slice(0, 88).trimEnd()}…` : text;
}

function statusLabel(status: PlaygroundProgressStatus): string {
  switch (status) {
    case "active":
      return "Active";
    case "passed":
      return "Passed";
    case "failed":
      return "Failed";
    case "skipped":
      return "Skipped";
    default:
      return "Pending";
  }
}

function branchingCases(turn: ScenarioTurn): string[] {
  const rawCases = Array.isArray(turn.branching?.cases) ? turn.branching.cases : [];
  return rawCases
    .map((entry) =>
      entry && typeof entry === "object" && typeof entry.condition === "string"
        ? entry.condition.trim()
        : ""
    )
    .filter(Boolean);
}

export function derivePlaygroundProgressNodes(
  scenario: ScenarioDefinition | null | undefined,
  events: PlaygroundStreamEvent[],
): PlaygroundProgressNode[] {
  if (!scenario) {
    return [];
  }

  const statuses = new Map<string, PlaygroundProgressStatus>();
  const selectedCases = new Map<string, string>();
  let completed = false;

  for (const event of events) {
    const turnId = asText(event.payload.turn_id);

    if (event.event_type === "turn.start" && turnId) {
      statuses.set(turnId, "active");
      continue;
    }

    if (event.event_type === "turn.response" && turnId) {
      if (statuses.get(turnId) !== "failed") {
        statuses.set(turnId, "passed");
      }
      continue;
    }

    if (event.event_type === "turn.expect" && turnId) {
      if (event.payload.passed === false) {
        statuses.set(turnId, "failed");
      } else if (!statuses.has(turnId)) {
        statuses.set(turnId, "passed");
      }
      continue;
    }

    if (event.event_type === "turn.branch" && turnId) {
      const selected = asText(event.payload.selected_case);
      if (selected) {
        selectedCases.set(turnId, selected);
      }
      continue;
    }

    if (event.event_type === "run.complete") {
      completed = true;
    }
  }

  return scenario.turns.map((turn) => {
    const turnId = String(turn.id);
    const rawStatus = statuses.get(turnId) ?? (completed ? "skipped" : "pending");
    const cases = branchingCases(turn);
    const selected = selectedCases.get(turnId);

    return {
      turnId,
      speaker: getScenarioTurnSpeaker(turn),
      textPreview: summarizeTurnText(turn),
      status: rawStatus,
      statusLabel: statusLabel(rawStatus),
      caseStates: cases.map((condition) => ({
        condition,
        status:
          !selected ? "pending" : condition === selected ? "selected" : "dimmed",
      })),
    };
  });
}
