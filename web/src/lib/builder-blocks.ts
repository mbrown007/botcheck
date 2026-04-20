import {
  getBuilderTurnSpeaker,
  getBuilderTurnText,
  type BuilderTurn,
} from "@/lib/builder-types";
import { getNodeDescriptor } from "@/lib/node-registry";
import type { BuilderEdge, BuilderNode } from "@/lib/flow-translator";
import { selectNodeTypeForTurn } from "@/lib/node-type-selector";

export const BUILDER_BLOCK_DND_MIME = "application/x-botcheck-builder-block";
export const BRANCH_CASE_COUNT_MIN = 1;
export const BRANCH_CASE_COUNT_MAX = 6;
export const BRANCH_CASE_COUNT_DEFAULT = 2;

export type BuilderPaletteBlockKind =
  | "say_something"
  | "listen_silence"
  | "decide_branch"
  | "time_route"
  | "wait_pause"
  | "hangup_end";

export interface InsertPaletteBlockInput {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  kind: BuilderPaletteBlockKind;
  position: { x: number; y: number };
  branchCaseCount?: number;
}

export interface InsertPaletteBlockResult {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  primaryNodeId: string;
  addedNodeIds: string[];
}

export interface DuplicateTurnBlockInput {
  nodes: BuilderNode[];
  turn: BuilderTurn;
  sourceTurnId: string;
  position: { x: number; y: number };
  sourceNodeData?: Partial<BuilderNode["data"]>;
}

export interface DuplicateTurnBlockResult {
  nodes: BuilderNode[];
  nodeId: string;
}

export interface DeleteBlocksInput {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  nodeIds: Iterable<string>;
}

export interface DeleteBlocksResult {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  deletedNodeIds: string[];
}

function normalizeNumber(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Number(value);
}

export function clampBranchCaseCount(value: number | undefined): number {
  const normalized = Math.floor(normalizeNumber(value, BRANCH_CASE_COUNT_DEFAULT));
  return Math.min(
    BRANCH_CASE_COUNT_MAX,
    Math.max(BRANCH_CASE_COUNT_MIN, normalized)
  );
}

function existingTurnIds(nodes: BuilderNode[]): Set<string> {
  return new Set(nodes.map((node) => node.id));
}

function nextOrderIndex(nodes: BuilderNode[]): number {
  let highest = -1;
  for (const node of nodes) {
    const maybeOrder = node.data?.orderIndex;
    if (typeof maybeOrder === "number" && Number.isFinite(maybeOrder)) {
      highest = Math.max(highest, maybeOrder);
    }
  }
  return highest + 1;
}

function nextTurnId(usedIds: Set<string>, base: string): string {
  const normalizedBase = base.trim() || "turn";
  if (!usedIds.has(normalizedBase)) {
    usedIds.add(normalizedBase);
    return normalizedBase;
  }
  let suffix = 2;
  while (usedIds.has(`${normalizedBase}_${suffix}`)) {
    suffix += 1;
  }
  const id = `${normalizedBase}_${suffix}`;
  usedIds.add(id);
  return id;
}

function createNodeFromTurn(
  turn: BuilderTurn,
  orderIndex: number,
  position: { x: number; y: number },
  dataOverrides?: Partial<BuilderNode["data"]>
): BuilderNode {
  const nodeType = selectNodeTypeForTurn(turn);
  const descriptor = getNodeDescriptor(nodeType);
  const speaker = getBuilderTurnSpeaker(turn);
  const data = descriptor
    ? descriptor.fromYaml(turn, orderIndex)
    : {
        turnId: String(turn.id),
        orderIndex,
        speaker,
        text: getBuilderTurnText(turn),
        turn: { ...turn },
      };
  return {
    id: String(turn.id),
    type: nodeType,
    position,
    data: {
      ...data,
      ...(dataOverrides ?? {}),
    },
  };
}

function createSaySomethingTurn(turnId: string): BuilderTurn {
  return {
    id: turnId,
    kind: "harness_prompt",
    content: {
      text: "Thanks for calling. How can I help you today?",
    },
    listen: true,
  };
}

function createListenTurn(turnId: string): BuilderTurn {
  return {
    id: turnId,
    kind: "harness_prompt",
    content: {
      silence_s: 2,
    },
    listen: true,
  };
}

function createHangupTurn(turnId: string): BuilderTurn {
  return {
    id: turnId,
    kind: "hangup",
  };
}

function createWaitTurn(turnId: string): BuilderTurn {
  return {
    id: turnId,
    kind: "wait",
    wait_s: 2,
  };
}

function createTimeRouteTurn(turnId: string): BuilderTurn {
  return {
    id: turnId,
    kind: "time_route",
    timezone: "UTC",
    windows: [
      {
        label: "business_hours",
        start: "09:00",
        end: "17:00",
        next: "",
      },
      {
        label: "after_hours",
        start: "17:00",
        end: "09:00",
        next: "",
      },
    ],
    default: "",
  };
}

function withoutRouting(turn: BuilderTurn): BuilderTurn {
  const copy = {
    ...turn,
  };
  delete copy.next;
  delete copy.branching;
  return copy;
}

export function duplicateTurnBlock({
  nodes,
  turn,
  sourceTurnId,
  position,
  sourceNodeData,
}: DuplicateTurnBlockInput): DuplicateTurnBlockResult {
  const usedIds = existingTurnIds(nodes);
  const nextId = nextTurnId(usedIds, `${sourceTurnId}_copy`);
  const copiedTurn: BuilderTurn = {
    ...withoutRouting(turn),
    id: nextId,
  };
  const appendedNode = createNodeFromTurn(copiedTurn, nextOrderIndex(nodes), position, {
    isBranchDecision: sourceNodeData?.isBranchDecision === true,
    branchOutputCount:
      typeof sourceNodeData?.branchOutputCount === "number"
        ? clampBranchCaseCount(sourceNodeData.branchOutputCount)
        : undefined,
    decisionOutputLabels: sourceNodeData?.decisionOutputLabels
      ? { ...(sourceNodeData.decisionOutputLabels as Record<string, string>) }
      : undefined,
  });
  return {
    nodes: [...nodes, appendedNode],
    nodeId: nextId,
  };
}

function insertSimpleBlock(
  nodes: BuilderNode[],
  edges: BuilderEdge[],
  baseId: string,
  turnFactory: (turnId: string) => BuilderTurn,
  position: { x: number; y: number }
): InsertPaletteBlockResult {
  const usedIds = existingTurnIds(nodes);
  const turnId = nextTurnId(usedIds, baseId);
  const turn = turnFactory(turnId);
  const node = createNodeFromTurn(turn, nextOrderIndex(nodes), position);
  return {
    nodes: [...nodes, node],
    edges,
    primaryNodeId: node.id,
    addedNodeIds: [node.id],
  };
}

function insertBranchBlock({
  nodes,
  edges,
  position,
  branchCaseCount,
}: Omit<InsertPaletteBlockInput, "kind">): InsertPaletteBlockResult {
  const usedTurnIds = existingTurnIds(nodes);
  const normalizedCaseCount = clampBranchCaseCount(branchCaseCount);

  const primaryTurnId = nextTurnId(usedTurnIds, "t_decide");

  const primaryTurn: BuilderTurn = {
    id: primaryTurnId,
    kind: "harness_prompt",
    content: {
      text: "Ask a routing question and branch based on the caller response.",
    },
    listen: true,
  };

  const decisionNode = createNodeFromTurn(
    primaryTurn,
    nextOrderIndex(nodes),
    position,
    {
      isBranchDecision: true,
      branchOutputCount: normalizedCaseCount,
    }
  );

  return {
    nodes: [...nodes, decisionNode],
    edges,
    primaryNodeId: primaryTurnId,
    addedNodeIds: [decisionNode.id],
  };
}

export function insertPaletteBlock({
  nodes,
  edges,
  kind,
  position,
  branchCaseCount,
}: InsertPaletteBlockInput): InsertPaletteBlockResult {
  if (kind === "say_something") {
    return insertSimpleBlock(nodes, edges, "t_say", createSaySomethingTurn, position);
  }
  if (kind === "listen_silence") {
    return insertSimpleBlock(nodes, edges, "t_listen", createListenTurn, position);
  }
  if (kind === "wait_pause") {
    return insertSimpleBlock(nodes, edges, "t_wait", createWaitTurn, position);
  }
  if (kind === "time_route") {
    return insertSimpleBlock(nodes, edges, "t_route", createTimeRouteTurn, position);
  }
  if (kind === "hangup_end") {
    return insertSimpleBlock(nodes, edges, "t_hangup", createHangupTurn, position);
  }
  return insertBranchBlock({
    nodes,
    edges,
    position,
    branchCaseCount,
  });
}

export function deleteBlocksByNodeIds({
  nodes,
  edges,
  nodeIds,
}: DeleteBlocksInput): DeleteBlocksResult {
  const ids = new Set(
    Array.from(nodeIds)
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0)
  );
  if (ids.size === 0) {
    return {
      nodes,
      edges,
      deletedNodeIds: [],
    };
  }

  const nextNodes = nodes.filter((node) => !ids.has(node.id));
  const nextEdges = edges.filter(
    (edge) => !ids.has(edge.source) && !ids.has(edge.target)
  );

  const deletedNodeIds = nodes
    .filter((node) => ids.has(node.id))
    .map((node) => node.id);

  return {
    nodes: nextNodes,
    edges: nextEdges,
    deletedNodeIds,
  };
}
