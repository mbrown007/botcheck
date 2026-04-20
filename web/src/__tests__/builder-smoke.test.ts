import test from "node:test";
import assert from "node:assert/strict";
import YAML from "yaml";
import { useBuilderStore } from "../lib/builder-store";
import { flowToYaml } from "../lib/flow-translator";
import { updateEdgeCondition } from "../lib/builder-edges";

const BRANCHING_YAML = `version: "1.0"
id: builder-smoke
name: Builder Smoke
type: reliability
description: smoke path for builder parity
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 12
scoring:
  overall_gate: false
  rubric: []
tags: []
turns:
  - id: t1
    speaker: harness
    text: Route request
    branching:
      cases:
        - condition: billing
          next: t2
      default: t3
  - id: t2
    speaker: harness
    text: Billing route
  - id: t3
    speaker: harness
    text: Default route
`;

const SHIPPED_BLOCKS_YAML = `version: "1.0"
id: shipped-blocks-smoke
name: Shipped Blocks Smoke
type: reliability
description: save reload coverage for shipped block kinds
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 12
scoring:
  overall_gate: false
  rubric: []
tags: []
turns:
  - id: t0_pickup
    kind: bot_listen
    next: t_route
  - id: t_route
    kind: time_route
    timezone: UTC
    windows:
      - label: business_hours
        start: "09:00"
        end: "17:00"
        next: t_hours
      - label: after_hours
        start: "17:00"
        end: "09:00"
        next: t_after
    default: t_default
  - id: t_hours
    kind: harness_prompt
    content:
      text: Business hours path
    listen: false
    next: t_wait
  - id: t_after
    kind: harness_prompt
    content:
      text: After hours path
    listen: false
    next: t_wait
  - id: t_default
    kind: harness_prompt
    content:
      text: Default path
    listen: false
    next: t_wait
  - id: t_wait
    kind: wait
    wait_s: 2
    next: t_end
  - id: t_end
    kind: hangup
`;

function parseYaml(yaml: string): Record<string, unknown> {
  const parsed = YAML.parse(yaml);
  assert.equal(typeof parsed, "object");
  assert.ok(parsed);
  assert.equal(Array.isArray(parsed), false);
  return parsed as Record<string, unknown>;
}

test("builder smoke: open, edit edge label, save, reload preserves branching condition", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BRANCHING_YAML);

  const initialState = useBuilderStore.getState();
  const billingEdge = initialState.edges.find(
    (edge) =>
      edge.source === "t1" &&
      edge.target === "t2" &&
      String(edge.label ?? edge.data?.condition ?? "").toLowerCase() === "billing"
  );
  assert.ok(billingEdge, "expected initial billing edge to exist");

  const relabeled = updateEdgeCondition({
    edges: initialState.edges,
    edgeId: billingEdge.id,
    condition: "account billing",
  });
  assert.equal(relabeled.error, undefined);
  useBuilderStore.getState().updateEdgesFromCanvas(relabeled.edges);

  const postEdit = useBuilderStore.getState();
  const savedYaml = flowToYaml({
    nodes: postEdit.nodes,
    edges: postEdit.edges,
    meta: postEdit.meta,
  });
  useBuilderStore.getState().setCanvasCanonicalYaml(savedYaml);
  useBuilderStore.getState().markSaved();

  const parsedSaved = parseYaml(savedYaml);
  const savedTurns = parsedSaved.turns as Array<Record<string, unknown>>;
  const t1 = savedTurns.find((turn) => turn.id === "t1");
  assert.ok(t1, "turn t1 missing after save");
  const branching = t1.branching as {
    cases: Array<{ condition: string; next: string }>;
    default: string;
  };
  assert.equal(branching.cases[0]?.condition, "account billing");
  assert.equal(branching.cases[0]?.next, "t2");
  assert.equal(branching.default, "t3");

  useBuilderStore.getState().hydrateFromYaml(savedYaml);
  const reloadedState = useBuilderStore.getState();
  const reloadedEdge = reloadedState.edges.find(
    (edge) =>
      edge.source === "t1" &&
      edge.target === "t2" &&
      String(edge.label ?? edge.data?.condition ?? "") === "account billing"
  );
  assert.ok(reloadedEdge, "relabeled edge missing after reload");
});

test("builder smoke: metadata edits serialize and reload from canvas state", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BRANCHING_YAML);

  const state = useBuilderStore.getState();
  useBuilderStore.getState().updateMeta({
    ...state.meta,
    id: "builder-smoke-copy",
    name: "Builder Smoke Copy",
    type: "compliance",
    version: "2.0",
    description: "metadata edit smoke",
    config: {
      ...(typeof state.meta.config === "object" && state.meta.config
        ? (state.meta.config as Record<string, unknown>)
        : {}),
      max_total_turns: 25,
      turn_timeout_s: 18,
    },
  });

  const updated = useBuilderStore.getState();
  const savedYaml = flowToYaml({
    nodes: updated.nodes,
    edges: updated.edges,
    meta: updated.meta,
  });

  const parsedSaved = parseYaml(savedYaml);
  assert.equal(parsedSaved.id, "builder-smoke-copy");
  assert.equal(parsedSaved.name, "Builder Smoke Copy");
  assert.equal(parsedSaved.type, "compliance");
  assert.equal(parsedSaved.version, "2.0");
  assert.equal(parsedSaved.description, "metadata edit smoke");
  const config = parsedSaved.config as Record<string, unknown>;
  assert.equal(config.max_total_turns, 25);
  assert.equal(config.turn_timeout_s, 18);

  useBuilderStore.getState().hydrateFromYaml(savedYaml);
  const reloaded = useBuilderStore.getState();
  assert.equal(reloaded.meta.id, "builder-smoke-copy");
  assert.equal(reloaded.meta.name, "Builder Smoke Copy");
  assert.equal(reloaded.meta.type, "compliance");
  assert.equal(reloaded.meta.version, "2.0");
});

test("builder smoke: node turn edits keep branch mode and rules through save and reload", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BRANCHING_YAML);

  const state = useBuilderStore.getState();
  const node = state.nodes.find((entry) => entry.id === "t1");
  assert.ok(node, "expected decision node t1");
  // BRANCHING_YAML has no mode: field, so branchMode defaults to "classifier".
  assert.equal(node.data.branchMode, "classifier", "initial branchMode should be classifier");

  useBuilderStore.getState().updateNodeTurn("t1", {
    ...node.data.turn,
    branching: {
      mode: "regex",
      cases: [
        {
          condition: "billing",
          regex: "billing|payments",
          next: "t2",
        },
      ],
      default: "t3",
    },
  });

  const updated = useBuilderStore.getState();
  const updatedNode = updated.nodes.find((entry) => entry.id === "t1");
  assert.ok(updatedNode, "updated node missing");
  assert.equal(updatedNode.data.branchMode, "regex");
  assert.deepEqual(updatedNode.data.branchCaseRules, {
    path_1: { regex: "billing|payments" },
  });

  const savedYaml = flowToYaml({
    nodes: updated.nodes,
    edges: updated.edges,
    meta: updated.meta,
  });
  const parsedSaved = parseYaml(savedYaml);
  const savedTurns = parsedSaved.turns as Array<Record<string, unknown>>;
  const savedTurn = savedTurns.find((turn) => turn.id === "t1");
  assert.ok(savedTurn, "turn t1 missing after save");
  assert.deepEqual(savedTurn.branching, {
    mode: "regex",
    cases: [
      {
        condition: "billing",
        regex: "billing|payments",
        next: "t2",
      },
    ],
    default: "t3",
  });

  useBuilderStore.getState().hydrateFromYaml(savedYaml);
  const reloaded = useBuilderStore.getState();
  const reloadedNode = reloaded.nodes.find((entry) => entry.id === "t1");
  assert.ok(reloadedNode, "reloaded node missing");
  assert.equal(reloadedNode.data.branchMode, "regex");
  assert.deepEqual(reloadedNode.data.branchCaseRules, {
    path_1: { regex: "billing|payments" },
  });
});

test("builder smoke: shipped block kinds save and reload without losing canonical shape", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(SHIPPED_BLOCKS_YAML);

  const initial = useBuilderStore.getState();
  assert.equal(initial.nodes.find((node) => node.id === "t0_pickup")?.type, "botNode");
  assert.equal(initial.nodes.find((node) => node.id === "t_route")?.type, "timeRouteNode");
  assert.equal(initial.nodes.find((node) => node.id === "t_wait")?.type, "waitNode");
  assert.equal(initial.nodes.find((node) => node.id === "t_end")?.type, "hangupNode");

  const savedYaml = flowToYaml({
    nodes: initial.nodes,
    edges: initial.edges,
    meta: initial.meta,
  });
  const parsedSaved = parseYaml(savedYaml);
  const savedTurns = parsedSaved.turns as Array<Record<string, unknown>>;
  assert.deepEqual(
    savedTurns.map((turn) => turn.kind),
    ["bot_listen", "time_route", "harness_prompt", "harness_prompt", "harness_prompt", "wait", "hangup"]
  );

  // bot_listen: next pointer must survive round-trip
  assert.deepEqual(savedTurns.find((turn) => turn.id === "t0_pickup"), {
    id: "t0_pickup",
    kind: "bot_listen",
    next: "t_route",
  });

  // harness_prompt: content wrapper, listen flag, and next pointer must all be preserved
  for (const [id, text, next] of [
    ["t_hours", "Business hours path", "t_wait"],
    ["t_after", "After hours path", "t_wait"],
    ["t_default", "Default path", "t_wait"],
  ] as const) {
    assert.deepEqual(savedTurns.find((turn) => turn.id === id), {
      id,
      kind: "harness_prompt",
      content: { text },
      listen: false,
      next,
    });
  }

  const routeTurn = savedTurns.find((turn) => turn.id === "t_route");
  assert.ok(routeTurn, "time_route turn missing after save");
  assert.deepEqual(routeTurn, {
    id: "t_route",
    kind: "time_route",
    timezone: "UTC",
    windows: [
      { label: "business_hours", start: "09:00", end: "17:00", next: "t_hours" },
      { label: "after_hours", start: "17:00", end: "09:00", next: "t_after" },
    ],
    default: "t_default",
  });

  const waitTurn = savedTurns.find((turn) => turn.id === "t_wait");
  assert.deepEqual(waitTurn, {
    id: "t_wait",
    kind: "wait",
    wait_s: 2,
    next: "t_end",
  });

  const hangupTurn = savedTurns.find((turn) => turn.id === "t_end");
  assert.deepEqual(hangupTurn, {
    id: "t_end",
    kind: "hangup",
  });

  useBuilderStore.getState().hydrateFromYaml(savedYaml);
  const reloaded = useBuilderStore.getState();
  assert.equal(reloaded.nodes.find((node) => node.id === "t0_pickup")?.type, "botNode");
  assert.equal(reloaded.nodes.find((node) => node.id === "t_route")?.type, "timeRouteNode");
  assert.equal(reloaded.nodes.find((node) => node.id === "t_wait")?.type, "waitNode");
  assert.equal(reloaded.nodes.find((node) => node.id === "t_end")?.type, "hangupNode");

  // time_route: routing edges use the shared decision-output:* handle namespace
  assert.deepEqual(
    reloaded.edges
      .filter((edge) => edge.source === "t_route")
      .sort((left, right) => String(left.sourceHandle).localeCompare(String(right.sourceHandle)))
      .map((edge) => [String(edge.sourceHandle), edge.target]),
    [
      ["decision-output:default", "t_default"],
      ["decision-output:path_1", "t_hours"],
      ["decision-output:path_2", "t_after"],
    ]
  );

  // time_route: window times and labels must survive the reload parse
  const reloadedRouteNode = reloaded.nodes.find((node) => node.id === "t_route");
  assert.deepEqual(
    (reloadedRouteNode?.data.turn as Record<string, unknown>).windows,
    [
      { label: "business_hours", start: "09:00", end: "17:00", next: "t_hours" },
      { label: "after_hours", start: "17:00", end: "09:00", next: "t_after" },
    ]
  );

  // wait: wait_s value must survive reload (fromYaml defaults to 1 if absent)
  const reloadedWaitNode = reloaded.nodes.find((node) => node.id === "t_wait");
  assert.equal((reloadedWaitNode?.data.turn as Record<string, unknown>).wait_s, 2);
});
