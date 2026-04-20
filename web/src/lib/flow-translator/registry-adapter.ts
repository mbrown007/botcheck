import {
  getBuilderTimeRouteDefault,
  getBuilderTurnKind,
  getBuilderTurnBranchMode,
  getBuilderTurnSpeaker,
  getBuilderTurnText,
  type BuilderTurn,
} from "@/lib/builder-types";
import { decisionPathSlotIndex } from "@/lib/decision-slots";
import {
  branchCaseRulesForTurn,
  getNodeDescriptor,
  type BuilderNodeData,
} from "@/lib/node-registry";
import { selectNodeTypeForTurn } from "@/lib/node-type-selector";

import { cloneObject, isRecord } from "./shared";
import type { BuilderNode } from "./types";

function defaultNodeData(turn: BuilderTurn, orderIndex: number): BuilderNodeData {
  return {
    turnId: String(turn.id),
    orderIndex,
    speaker: getBuilderTurnSpeaker(turn),
    text: getBuilderTurnText(turn),
    branchMode: getBuilderTurnBranchMode(turn),
    branchCaseRules: branchCaseRulesForTurn(turn),
    turn: { ...turn },
  };
}

export function turnToBuilderNode(turn: BuilderTurn, orderIndex: number): BuilderNode {
  const nodeType = selectNodeTypeForTurn(turn);
  const descriptor = getNodeDescriptor(nodeType);
  const data = descriptor ? descriptor.fromYaml(turn, orderIndex) : defaultNodeData(turn, orderIndex);

  const branching = isRecord(turn.branching)
    ? (turn.branching as Record<string, unknown>)
    : null;
  const branchingCases = Array.isArray(branching?.cases)
    ? branching.cases.filter((entry): entry is Record<string, unknown> => isRecord(entry))
    : [];
  const hasBranchingDefault =
    typeof branching?.default === "string" && branching.default.trim().length > 0;

  if (branchingCases.length > 0 || hasBranchingDefault) {
    data.isBranchDecision = true;
    data.branchOutputCount = Math.max(
      1,
      branchingCases.length + (hasBranchingDefault ? 1 : 0)
    );
  }

  return {
    id: String(turn.id),
    type: nodeType,
    position: { x: 0, y: 0 },
    data,
  } satisfies BuilderNode;
}

export function builderNodeToTurn(node: BuilderNode): BuilderTurn {
  const descriptor = getNodeDescriptor(node.type ?? "harnessNode");
  const baseTurn = descriptor ? descriptor.toYaml(node.data) : cloneObject(node.data.turn);
  const turn = (isRecord(baseTurn) ? cloneObject(baseTurn) : {}) as BuilderTurn;
  if (node.type === "timeRouteNode" || getBuilderTurnKind(turn) === "time_route") {
    turn.id = node.id;
    if (typeof turn.default !== "string") {
      turn.default = getBuilderTimeRouteDefault(turn) ?? "";
    }
    return turn;
  }
  const branchMode =
    node.data.branchMode === "keyword" || node.data.branchMode === "regex"
      ? node.data.branchMode
      : "classifier";
  const branchCaseRules = isRecord(node.data.branchCaseRules)
    ? (node.data.branchCaseRules as Record<string, { match?: string; regex?: string }>)
    : {};
  const cases = Object.entries(branchCaseRules)
    .map(([slot, rule]) => ({
      slot,
      rule,
    }))
    .sort((left, right) => {
      const li = decisionPathSlotIndex(left.slot) ?? 0;
      const ri = decisionPathSlotIndex(right.slot) ?? 0;
      return li - ri;
    })
    .map(({ slot, rule }) => {
      const nextCase: { condition: string; next: string; match?: string; regex?: string } = {
        condition: slot,
        next: "",
      };
      if (typeof rule?.match === "string" && rule.match.trim()) {
        nextCase.match = rule.match.trim();
      }
      if (typeof rule?.regex === "string" && rule.regex.trim()) {
        nextCase.regex = rule.regex.trim();
      }
      return nextCase;
    });
  const existingBranching = isRecord(turn.branching)
    ? (turn.branching as Record<string, unknown>)
    : null;
  const existingDefault =
    typeof existingBranching?.default === "string" ? existingBranching.default : "";
  if (node.data.isBranchDecision === true || existingBranching) {
    turn.branching = {
      cases,
      default: existingDefault,
      mode: branchMode,
    };
  }
  turn.id = node.id;
  return turn;
}
