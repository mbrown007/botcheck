import YAML, { Scalar } from "yaml";

import {
  decisionConditionForSlot,
} from "@/lib/builder-decision";
import {
  getBuilderTimeRouteDefault,
  getBuilderTimeRouteTimezone,
  getBuilderTimeRouteWindows,
  getBuilderTurnKind,
  type BuilderTurn,
} from "@/lib/builder-types";
import { inferDecisionSlotFromEdge } from "@/lib/builder-decision";
import {
  decisionPathSlot,
  decisionPathSlotIndex,
} from "@/lib/decision-slots";

import { KNOWN_TOP_LEVEL_FIELDS } from "./constants";
import { builderNodeToTurn } from "./registry-adapter";
import {
  cloneObject,
  edgeCondition,
  isDefaultCondition,
  isRecord,
} from "./shared";
import type { BuilderEdge, FlowToYamlInput } from "./types";

function sortNodesByOrderIndex(nodes: FlowToYamlInput["nodes"]) {
  return [...nodes].sort((left, right) => {
    const leftOrder =
      typeof left.data?.orderIndex === "number"
        ? left.data.orderIndex
        : Number.MAX_SAFE_INTEGER;
    const rightOrder =
      typeof right.data?.orderIndex === "number"
        ? right.data.orderIndex
        : Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.id.localeCompare(right.id);
  });
}

function preferredEntryNodeId(
  sortedNodes: FlowToYamlInput["nodes"],
  edges: FlowToYamlInput["edges"]
): string | null {
  const incomingCounts = new Map<string, number>();
  for (const node of sortedNodes) {
    incomingCounts.set(node.id, 0);
  }
  for (const edge of edges) {
    incomingCounts.set(edge.target, (incomingCounts.get(edge.target) ?? 0) + 1);
  }
  const roots = sortedNodes.filter((node) => (incomingCounts.get(node.id) ?? 0) === 0);
  return roots.length === 1 ? roots[0]!.id : null;
}

// Wrap an HH:MM time string in a YAML Scalar that forces double-quote style.
// YAML 1.1 parsers interpret bare 09:00 as a base-60 integer; quoting at the
// AST level prevents the regex post-processing approach that would
// inadvertently affect any other start/end fields in the document.
function quotedTimeScalar(value: string): Scalar {
  const s = new Scalar(value);
  s.type = Scalar.QUOTE_DOUBLE;
  return s;
}

export function flowToYaml({ nodes, edges, meta }: FlowToYamlInput): string {
  const sortedNodes = sortNodesByOrderIndex(nodes);
  const entryNodeId = preferredEntryNodeId(sortedNodes, edges);
  const orderedNodes =
    entryNodeId && sortedNodes[0]?.id !== entryNodeId
      ? [
          sortedNodes.find((node) => node.id === entryNodeId)!,
          ...sortedNodes.filter((node) => node.id !== entryNodeId),
        ]
      : sortedNodes;

  // Turns are built for YAML serialization only, not for canvas state.
  // time_route windows embed YAML Scalar nodes for precise quoting, so the
  // array is typed as unknown[] rather than BuilderTurn[].
  const turns: unknown[] = orderedNodes.map((node) => {
    // Read branchMode from node.data (the authoritative source) before serializing the turn.
    const branchModeRaw = node.data.branchMode;
    const existingBranchMode =
      branchModeRaw === "keyword" || branchModeRaw === "regex" ? branchModeRaw : "classifier";
    const turn = builderNodeToTurn(node);
    const existingBranching =
      isRecord(turn.branching) && Array.isArray(turn.branching.cases)
        ? turn.branching
        : null;
    const existingCaseRulesBySlot = new Map<string, { match?: string; regex?: string }>();
    existingBranching?.cases.forEach((entry, index) => {
      const slot = decisionPathSlot(index + 1);
      const rule: { match?: string; regex?: string } = {};
      if (typeof entry.match === "string" && entry.match.trim()) {
        rule.match = entry.match.trim();
      }
      if (typeof entry.regex === "string" && entry.regex.trim()) {
        rule.regex = entry.regex.trim();
      }
      if (rule.match || rule.regex) {
        existingCaseRulesBySlot.set(slot, rule);
      }
    });

    const outgoingEdges = edges.filter((edge) => edge.source === node.id);
    const defaultEdge = outgoingEdges.find((edge) =>
      isDefaultCondition(edgeCondition(edge))
    );
    const caseEdges = outgoingEdges
      .filter((edge) => edge !== defaultEdge)
      .sort((left, right) => {
        const leftSlot = inferDecisionSlotFromEdge(left);
        const rightSlot = inferDecisionSlotFromEdge(right);
        const leftIndex = decisionPathSlotIndex(leftSlot);
        const rightIndex = decisionPathSlotIndex(rightSlot);
        if (leftIndex !== null && rightIndex !== null) {
          return leftIndex - rightIndex;
        }
        if (leftIndex !== null) {
          return -1;
        }
        if (rightIndex !== null) {
          return 1;
        }
        return left.id.localeCompare(right.id);
      });

    if (node.type === "timeRouteNode" || getBuilderTurnKind(turn) === "time_route") {
      const existingWindows = getBuilderTimeRouteWindows(turn);
      const nextDefaultTarget =
        defaultEdge?.target ?? getBuilderTimeRouteDefault(turn) ?? "";
      const windows = caseEdges.map((edge, index) => {
        const slot = inferDecisionSlotFromEdge(edge) ?? decisionPathSlot(index + 1);
        const existingWindow = existingWindows[(decisionPathSlotIndex(slot) ?? index + 1) - 1];
        const condition = (edgeCondition(edge) ?? "").trim();
        const existingLabel =
          typeof existingWindow?.label === "string" ? existingWindow.label.trim() : "";
        const startVal = typeof existingWindow?.start === "string" ? existingWindow.start.trim() : "";
        const endVal = typeof existingWindow?.end === "string" ? existingWindow.end.trim() : "";
        return {
          label:
            condition ||
            (existingLabel
              ? existingLabel
              : decisionConditionForSlot(slot, node.data.decisionOutputLabels)),
          start: quotedTimeScalar(startVal),
          end: quotedTimeScalar(endVal),
          next: edge.target,
        };
      });
      return {
        ...turn,
        kind: "time_route",
        timezone: getBuilderTimeRouteTimezone(turn) ?? "UTC",
        windows,
        default: nextDefaultTarget,
      };
    }

    const hasBranching =
      caseEdges.some((edge) => Boolean(edgeCondition(edge))) ||
      Boolean(defaultEdge) ||
      outgoingEdges.length > 1;

    if (hasBranching) {
      const existingDefault =
        existingBranching && typeof existingBranching.default === "string"
          ? existingBranching.default
          : undefined;

      const nextDefaultTarget =
        defaultEdge?.target ?? existingDefault ?? outgoingEdges[0]?.target ?? "";

      const explicitCases: Array<{
        condition: string;
        next: string;
        match?: string;
        regex?: string;
      }> = [];
      const unlabeledCases: BuilderEdge[] = [];
      for (const edge of caseEdges) {
        const condition = edgeCondition(edge);
        if (!condition || isDefaultCondition(condition)) {
          unlabeledCases.push(edge);
          continue;
        }
        const slot = inferDecisionSlotFromEdge(edge) ?? decisionPathSlot(explicitCases.length + 1);
        const existingRule = existingCaseRulesBySlot.get(slot);
        const nextCase: {
          condition: string;
          next: string;
          match?: string;
          regex?: string;
        } = {
          condition: condition.trim(),
          next: edge.target,
        };
        if (existingBranchMode === "keyword" && existingRule?.match) {
          nextCase.match = existingRule.match;
        }
        if (existingBranchMode === "regex" && existingRule?.regex) {
          nextCase.regex = existingRule.regex;
        }
        explicitCases.push(nextCase);
      }

      let skippedUnlabeledAsDefault = false;
      let autoConditionIndex = 1;
      for (const edge of unlabeledCases) {
        if (
          !defaultEdge &&
          !existingDefault &&
          !skippedUnlabeledAsDefault &&
          edge.target === nextDefaultTarget
        ) {
          skippedUnlabeledAsDefault = true;
          continue;
        }
        const slot =
          inferDecisionSlotFromEdge(edge) ?? decisionPathSlot(autoConditionIndex);
        const existingRule = existingCaseRulesBySlot.get(slot);
        const nextCase: {
          condition: string;
          next: string;
          match?: string;
          regex?: string;
        } = {
          condition: decisionPathSlot(autoConditionIndex),
          next: edge.target,
        };
        if (existingBranchMode === "keyword" && existingRule?.match) {
          nextCase.match = existingRule.match;
        }
        if (existingBranchMode === "regex" && existingRule?.regex) {
          nextCase.regex = existingRule.regex;
        }
        explicitCases.push(nextCase);
        autoConditionIndex += 1;
      }

      turn.branching = {
        cases: explicitCases,
        default: nextDefaultTarget,
        ...(existingBranchMode !== "classifier" ? { mode: existingBranchMode } : {}),
      };
      delete turn.next;
      return turn;
    }

    const nextEdge = outgoingEdges[0];
    if (nextEdge) {
      turn.next = nextEdge.target;
      delete turn.branching;
      return turn;
    }

    delete turn.next;
    delete turn.branching;
    return turn;
  });

  const doc: Record<string, unknown> = {};
  const knownFieldSet = new Set<string>(KNOWN_TOP_LEVEL_FIELDS);

  for (const field of KNOWN_TOP_LEVEL_FIELDS) {
    if (field in meta) {
      doc[field] = cloneObject(meta[field]);
    }
  }

  const unknownFieldOrder = Array.isArray(meta.__unknownTopLevelKeyOrder)
    ? meta.__unknownTopLevelKeyOrder
    : [];

  for (const key of unknownFieldOrder) {
    if (key in meta && key !== "turns" && key !== "__unknownTopLevelKeyOrder") {
      doc[key] = cloneObject(meta[key]);
    }
  }

  for (const [key, value] of Object.entries(meta)) {
    if (key === "turns" || key === "__unknownTopLevelKeyOrder") {
      continue;
    }
    if (knownFieldSet.has(key) || unknownFieldOrder.includes(key)) {
      continue;
    }
    doc[key] = cloneObject(value);
  }

  doc.turns = turns;
  return YAML.stringify(doc, { lineWidth: 0 });
}
