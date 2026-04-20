import test from "node:test";
import assert from "node:assert/strict";
import {
  BRANCH_CASE_COUNT_DEFAULT,
  BRANCH_CASE_COUNT_MAX,
  BRANCH_CASE_COUNT_MIN,
  clampBranchCaseCount,
  deleteBlocksByNodeIds,
  duplicateTurnBlock,
  insertPaletteBlock,
} from "../lib/builder-blocks";
import type { BuilderEdge, BuilderNode } from "../lib/flow-translator";

const BASE_NODE: BuilderNode = {
  id: "t1",
  type: "harnessNode",
  position: { x: 10, y: 20 },
  data: {
    turnId: "t1",
    orderIndex: 0,
    speaker: "harness",
    text: "Hello",
    turn: {
      id: "t1",
      kind: "harness_prompt",
      content: {
        text: "Hello",
      },
      listen: true,
      next: "t2",
    },
  },
};

test("clampBranchCaseCount enforces limits and defaults", () => {
  assert.equal(clampBranchCaseCount(undefined), BRANCH_CASE_COUNT_DEFAULT);
  assert.equal(clampBranchCaseCount(0), BRANCH_CASE_COUNT_MIN);
  assert.equal(clampBranchCaseCount(999), BRANCH_CASE_COUNT_MAX);
  assert.equal(clampBranchCaseCount(3.8), 3);
});

test("insertPaletteBlock adds say_something node", () => {
  const existingEdges: BuilderEdge[] = [
    {
      id: "t1::next::t2",
      source: "t1",
      target: "t2",
      data: { kind: "next" },
    },
  ];
  const result = insertPaletteBlock({
    nodes: [],
    edges: existingEdges,
    kind: "say_something",
    position: { x: 120, y: 240 },
  });
  assert.equal(result.nodes.length, 1);
  assert.equal(result.edges.length, 1);
  assert.equal(result.nodes[0]?.id, "t_say");
  assert.equal(result.nodes[0]?.data.turn.kind, "harness_prompt");
  assert.equal(
    result.nodes[0]?.data.turn.content?.text,
    "Thanks for calling. How can I help you today?"
  );
  assert.equal(result.nodes[0]?.data.turn.listen, true);
  assert.equal(result.nodes[0]?.position.x, 120);
});

test("insertPaletteBlock adds listen_silence node", () => {
  const result = insertPaletteBlock({
    nodes: [],
    edges: [],
    kind: "listen_silence",
    position: { x: 80, y: 100 },
  });
  const turn = result.nodes[0]?.data.turn;
  assert.ok(turn);
  assert.equal(turn.kind, "harness_prompt");
  assert.equal(turn.content?.silence_s, 2);
  assert.equal(turn.listen, true);
});

test("insertPaletteBlock adds hangup_end terminal node", () => {
  const result = insertPaletteBlock({
    nodes: [],
    edges: [],
    kind: "hangup_end",
    position: { x: 140, y: 220 },
  });
  assert.equal(result.nodes.length, 1);
  const node = result.nodes[0];
  assert.ok(node);
  assert.equal(node.type, "hangupNode");
  assert.equal(node.data.turn.kind, "hangup");
});

test("insertPaletteBlock adds wait_pause node", () => {
  const result = insertPaletteBlock({
    nodes: [],
    edges: [],
    kind: "wait_pause",
    position: { x: 140, y: 220 },
  });
  assert.equal(result.nodes.length, 1);
  const node = result.nodes[0];
  assert.ok(node);
  assert.equal(node.type, "waitNode");
  assert.equal(node.data.turn.kind, "wait");
  assert.equal(node.data.turn.wait_s, 2);
});

test("insertPaletteBlock adds time_route node", () => {
  const result = insertPaletteBlock({
    nodes: [],
    edges: [],
    kind: "time_route",
    position: { x: 140, y: 220 },
  });
  assert.equal(result.nodes.length, 1);
  const node = result.nodes[0];
  assert.ok(node);
  assert.equal(node.type, "timeRouteNode");
  assert.equal(node.data.turn.kind, "time_route");
  assert.equal(node.data.turn.timezone, "UTC");
  assert.equal(node.data.turn.windows?.length, 2);
});

test("insertPaletteBlock adds decide_branch with dynamic outputs", () => {
  const result = insertPaletteBlock({
    nodes: [],
    edges: [],
    kind: "decide_branch",
    position: { x: 200, y: 300 },
    branchCaseCount: 3,
  });
  assert.equal(result.nodes.length, 1);
  assert.equal(result.edges.length, 0);
  const root = result.nodes.find((node) => node.id === result.primaryNodeId);
  assert.ok(root);
  assert.equal(root.data.isBranchDecision, true);
  assert.equal(root.data.branchOutputCount, 3);
  assert.equal(root.data.turn.branching, undefined);
});

test("insertPaletteBlock keeps IDs unique across existing nodes", () => {
  const existingNodes: BuilderNode[] = [
    BASE_NODE,
    {
      ...BASE_NODE,
      id: "t_say",
      data: {
        ...BASE_NODE.data,
        turnId: "t_say",
        orderIndex: 1,
        turn: {
          ...BASE_NODE.data.turn,
          id: "t_say",
        },
      },
    },
  ];
  const result = insertPaletteBlock({
    nodes: existingNodes,
    edges: [],
    kind: "say_something",
    position: { x: 0, y: 0 },
  });
  assert.ok(result.nodes.some((node) => node.id === "t_say_2"));
});

test("duplicateTurnBlock removes routing fields from copied turn", () => {
  const existingEdges: BuilderEdge[] = [];
  const copied = duplicateTurnBlock({
    nodes: [BASE_NODE],
    turn: BASE_NODE.data.turn,
    sourceTurnId: BASE_NODE.id,
    position: { x: 90, y: 180 },
  });
  assert.equal(copied.nodes.length, 2);
  const pasted = copied.nodes.find((node) => node.id !== BASE_NODE.id);
  assert.ok(pasted);
  assert.equal(pasted.id, "t1_copy");
  assert.equal(pasted.data.turn.next, undefined);
  assert.equal(pasted.data.turn.branching, undefined);
  assert.equal(existingEdges.length, 0);
});

test("duplicateTurnBlock preserves decision node metadata when provided", () => {
  const copied = duplicateTurnBlock({
    nodes: [BASE_NODE],
    turn: BASE_NODE.data.turn,
    sourceTurnId: BASE_NODE.id,
    sourceNodeData: {
      isBranchDecision: true,
      branchOutputCount: 4,
      decisionOutputLabels: {
        path_1: "billing support",
      },
    },
    position: { x: 90, y: 180 },
  });
  const pasted = copied.nodes.find((node) => node.id !== BASE_NODE.id);
  assert.ok(pasted);
  assert.equal(pasted.data.isBranchDecision, true);
  assert.equal(pasted.data.branchOutputCount, 4);
  assert.equal(pasted.data.decisionOutputLabels?.path_1, "billing support");
});

test("deleteBlocksByNodeIds removes selected nodes and attached edges", () => {
  const nodes: BuilderNode[] = [
    BASE_NODE,
    {
      ...BASE_NODE,
      id: "t2",
      data: {
        ...BASE_NODE.data,
        turnId: "t2",
        orderIndex: 1,
        turn: {
          ...BASE_NODE.data.turn,
          id: "t2",
          next: "t3",
        },
      },
    },
    {
      ...BASE_NODE,
      id: "t3",
      data: {
        ...BASE_NODE.data,
        turnId: "t3",
        orderIndex: 2,
        turn: {
          ...BASE_NODE.data.turn,
          id: "t3",
        },
      },
    },
  ];
  const edges: BuilderEdge[] = [
    { id: "e1", source: "t1", target: "t2", data: { kind: "next" } },
    { id: "e2", source: "t2", target: "t3", data: { kind: "next" } },
  ];
  const result = deleteBlocksByNodeIds({
    nodes,
    edges,
    nodeIds: ["t2"],
  });
  assert.deepEqual(result.deletedNodeIds, ["t2"]);
  assert.deepEqual(result.nodes.map((node) => node.id), ["t1", "t3"]);
  assert.equal(result.edges.length, 0);
});

test("deleteBlocksByNodeIds is no-op for empty IDs", () => {
  const result = deleteBlocksByNodeIds({
    nodes: [BASE_NODE],
    edges: [],
    nodeIds: [],
  });
  assert.equal(result.nodes.length, 1);
  assert.equal(result.edges.length, 0);
  assert.deepEqual(result.deletedNodeIds, []);
});
