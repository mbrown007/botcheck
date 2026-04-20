import type { BuilderNodePositionMap } from "@/lib/flow-layout-storage";
import {
  getBuilderTimeRouteDefault,
  getBuilderTimeRouteWindows,
  getBuilderTurnKind,
  type BuilderTurn,
} from "@/lib/builder-types";
import {
  DECISION_DEFAULT_SLOT,
  decisionPathSlot,
} from "@/lib/decision-slots";

import { DECISION_OUTPUT_HANDLE_PREFIX } from "./constants";
import { applyDagreLayout, mergeSavedPositions } from "./layout";
import { turnToBuilderNode } from "./registry-adapter";
import {
  extractMetaFields,
  isRecord,
  normalizeTurnId,
  parseScenarioYaml,
  parseTurns,
} from "./shared";
import type { BuilderEdge, FlowDocument } from "./types";

function buildEdgesFromTurns(turns: BuilderTurn[]): BuilderEdge[] {
  const edges: BuilderEdge[] = [];
  const ids = turns.map((turn, index) => normalizeTurnId(turn, index));

  for (let index = 0; index < turns.length; index += 1) {
    const turn = turns[index];
    const sourceId = ids[index];
    if (getBuilderTurnKind(turn) === "time_route") {
      const windows = getBuilderTimeRouteWindows(turn);
      windows.forEach((window, windowIndex) => {
        const target = typeof window.next === "string" ? window.next.trim() : "";
        if (!target) {
          return;
        }
        const label = typeof window.label === "string" ? window.label.trim() : "";
        edges.push({
          id: `${sourceId}::window::${windowIndex}`,
          source: sourceId,
          target,
          sourceHandle: `${DECISION_OUTPUT_HANDLE_PREFIX}${decisionPathSlot(windowIndex + 1)}`,
          label: label || decisionPathSlot(windowIndex + 1),
          data: {
            condition: label || decisionPathSlot(windowIndex + 1),
            kind: "branch_case",
          },
        });
      });
      const defaultTarget = getBuilderTimeRouteDefault(turn)?.trim();
      if (defaultTarget) {
        edges.push({
          id: `${sourceId}::default`,
          source: sourceId,
          target: defaultTarget,
          sourceHandle: `${DECISION_OUTPUT_HANDLE_PREFIX}${DECISION_DEFAULT_SLOT}`,
          label: DECISION_DEFAULT_SLOT,
          data: {
            condition: DECISION_DEFAULT_SLOT,
            kind: "branch_default",
          },
        });
      }
      continue;
    }
    const branching = isRecord(turn.branching)
      ? (turn.branching as Record<string, unknown>)
      : null;

    const branchCases = Array.isArray(branching?.cases)
      ? branching.cases.filter((item): item is Record<string, unknown> => isRecord(item))
      : [];
    const branchDefault =
      branching && typeof branching.default === "string" && branching.default.trim()
        ? branching.default.trim()
        : null;

    if (branchCases.length > 0 || branchDefault) {
      branchCases.forEach((branchCase, caseIndex) => {
        const condition =
          typeof branchCase.condition === "string"
            ? branchCase.condition.trim()
            : "";
        const target =
          typeof branchCase.next === "string" ? branchCase.next.trim() : "";
        if (!target) {
          return;
        }
        edges.push({
          id: `${sourceId}::case::${caseIndex}`,
          source: sourceId,
          target,
          sourceHandle: `${DECISION_OUTPUT_HANDLE_PREFIX}${decisionPathSlot(caseIndex + 1)}`,
          label: condition,
          data: {
            condition,
            kind: "branch_case",
          },
        });
      });

      if (branchDefault) {
        edges.push({
          id: `${sourceId}::default`,
          source: sourceId,
          target: branchDefault,
          sourceHandle: `${DECISION_OUTPUT_HANDLE_PREFIX}${DECISION_DEFAULT_SLOT}`,
          label: DECISION_DEFAULT_SLOT,
          data: {
            condition: DECISION_DEFAULT_SLOT,
            kind: "branch_default",
          },
        });
      }
      continue;
    }

    if (typeof turn.next === "string" && turn.next.trim()) {
      const target = turn.next.trim();
      edges.push({
        id: `${sourceId}::next`,
        source: sourceId,
        target,
        data: {
          kind: "next",
        },
      });
      continue;
    }

    const implicitTarget = ids[index + 1];
    if (implicitTarget) {
      edges.push({
        id: `${sourceId}::implicit`,
        source: sourceId,
        target: implicitTarget,
        data: {
          implicit: true,
          kind: "next",
        },
      });
    }
  }

  return edges;
}

export function yamlToFlow(
  yaml: string,
  savedPositions?: BuilderNodePositionMap
): FlowDocument {
  const scenario = parseScenarioYaml(yaml);
  const turns = parseTurns(scenario.turns);

  const normalizedTurns = turns.map((turn, index) => ({
    ...turn,
    id: normalizeTurnId(turn, index),
  }));

  const nodes = normalizedTurns.map((turn, index) =>
    turnToBuilderNode(turn, index)
  );

  const edges = buildEdgesFromTurns(normalizedTurns);
  const laidOutNodes = applyDagreLayout(nodes, edges);
  const positionedNodes = mergeSavedPositions(laidOutNodes, savedPositions);
  const meta = extractMetaFields(scenario);

  return {
    nodes: positionedNodes,
    edges,
    meta,
  };
}
