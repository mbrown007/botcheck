import test from "node:test";
import assert from "node:assert/strict";
import {
  connectWithBranchingRules,
  removeEdgeWithRebalance,
  shouldPromptForBranchCondition,
  updateEdgeCondition,
} from "../lib/builder-edges";
import type { BuilderEdge } from "../lib/flow-translator";

test("first connection creates linear next edge without prompt", () => {
  const edges = connectWithBranchingRules({
    edges: [],
    source: "t1",
    target: "t2",
  }).edges;
  assert.equal(edges.length, 1);
  assert.equal(edges[0]?.source, "t1");
  assert.equal(edges[0]?.target, "t2");
  assert.equal(edges[0]?.data?.kind, "next");
  assert.equal(shouldPromptForBranchCondition(edges, "t1"), true);
});

test("first connection with explicit condition creates branch case edge", () => {
  const result = connectWithBranchingRules({
    edges: [],
    source: "t_decide",
    target: "t_target",
    condition: "path_1",
    sourceHandle: "decision-output:path_1",
  });
  assert.equal(result.error, undefined);
  assert.equal(result.edges.length, 1);
  assert.equal(result.edges[0]?.label, "path_1");
  assert.equal(result.edges[0]?.data?.kind, "branch_case");
  assert.equal(result.edges[0]?.sourceHandle, "decision-output:path_1");
});

test("allowDefaultCondition enables explicit default edge creation", () => {
  const result = connectWithBranchingRules({
    edges: [],
    source: "t_decide",
    target: "t_fallback",
    condition: "default",
    sourceHandle: "decision-output:default",
    allowDefaultCondition: true,
  });
  assert.equal(result.error, undefined);
  assert.equal(result.edges.length, 1);
  assert.equal(result.edges[0]?.label, "default");
  assert.equal(result.edges[0]?.data?.kind, "branch_default");
  assert.equal(result.edges[0]?.sourceHandle, "decision-output:default");
});

test("shouldPromptForBranchCondition returns false with no existing source edges", () => {
  const edges: BuilderEdge[] = [
    {
      id: "t2::next::t3",
      source: "t2",
      target: "t3",
      data: { kind: "next" },
    },
  ];
  assert.equal(shouldPromptForBranchCondition(edges, "t1"), false);
});

test("second connection promotes existing unlabeled edge to default", () => {
  const initial: BuilderEdge[] = [
    {
      id: "t1::next::t2",
      source: "t1",
      target: "t2",
      data: { kind: "next" },
    },
  ];
  const result = connectWithBranchingRules({
    edges: initial,
    source: "t1",
    target: "t3",
    condition: "billing support",
  });
  assert.equal(result.error, undefined);
  assert.equal(result.edges.length, 2);
  const defaultEdge = result.edges.find((edge) => edge.label === "default");
  const caseEdge = result.edges.find((edge) => edge.label === "billing support");
  assert.ok(defaultEdge);
  assert.ok(caseEdge);
  assert.equal(defaultEdge?.target, "t2");
  assert.equal(caseEdge?.target, "t3");
});

test("blank condition auto-generates path_n condition", () => {
  const initial: BuilderEdge[] = [
    {
      id: "default",
      source: "t1",
      target: "t2",
      label: "default",
      data: { condition: "default", kind: "branch_default" },
    },
  ];
  const result = connectWithBranchingRules({
    edges: initial,
    source: "t1",
    target: "t3",
    condition: "   ",
  });
  const caseEdge = result.edges.find((edge) => edge.source === "t1" && edge.target === "t3");
  assert.ok(caseEdge);
  assert.equal(caseEdge?.label, "path_1");
});

test("duplicate condition returns error and keeps edges unchanged", () => {
  const initial: BuilderEdge[] = [
    {
      id: "default",
      source: "t1",
      target: "t2",
      label: "default",
      data: { condition: "default", kind: "branch_default" },
    },
    {
      id: "case",
      source: "t1",
      target: "t3",
      label: "billing",
      data: { condition: "billing", kind: "branch_case" },
    },
  ];
  const result = connectWithBranchingRules({
    edges: initial,
    source: "t1",
    target: "t4",
    condition: "billing",
  });
  assert.ok(result.error);
  assert.equal(result.edges.length, initial.length);
});

test("reserved default condition returns error", () => {
  const initial: BuilderEdge[] = [
    {
      id: "next",
      source: "t1",
      target: "t2",
      data: { kind: "next" },
    },
  ];
  const result = connectWithBranchingRules({
    edges: initial,
    source: "t1",
    target: "t3",
    condition: "default",
  });
  assert.ok(result.error);
});

test("updateEdgeCondition returns clearer message when turn has only one edge", () => {
  const initial: BuilderEdge[] = [
    {
      id: "only",
      source: "t1",
      target: "t2",
      data: { kind: "next" },
    },
  ];
  const result = updateEdgeCondition({
    edges: initial,
    edgeId: "only",
    condition: "billing",
  });
  assert.equal(
    result.error,
    "This turn has only one exit; add another connection to enable condition labels."
  );
});

test("removeEdgeWithRebalance promotes a default when removing case from no-default fanout", () => {
  const initial: BuilderEdge[] = [
    {
      id: "case-a",
      source: "t1",
      target: "t2",
      label: "a",
      data: { condition: "a", kind: "branch_case" },
    },
    {
      id: "case-b",
      source: "t1",
      target: "t3",
      label: "b",
      data: { condition: "b", kind: "branch_case" },
    },
    {
      id: "case-c",
      source: "t1",
      target: "t4",
      label: "c",
      data: { condition: "c", kind: "branch_case" },
    },
  ];
  const result = removeEdgeWithRebalance({
    edges: initial,
    edgeId: "case-b",
  });
  assert.equal(result.error, undefined);
  const defaults = result.edges.filter((edge) => edge.label === "default");
  assert.equal(defaults.length, 1);
  assert.equal(defaults[0]?.id, "case-a");
});

test("removeEdgeWithRebalance demotes to linear when one edge remains", () => {
  const initial: BuilderEdge[] = [
    {
      id: "default",
      source: "t1",
      target: "t2",
      label: "default",
      data: { condition: "default", kind: "branch_default" },
    },
    {
      id: "case-a",
      source: "t1",
      target: "t3",
      label: "a",
      data: { condition: "a", kind: "branch_case" },
    },
  ];
  const result = removeEdgeWithRebalance({
    edges: initial,
    edgeId: "case-a",
  });
  assert.equal(result.error, undefined);
  const remaining = result.edges.filter((edge) => edge.source === "t1");
  assert.equal(remaining.length, 1);
  assert.equal(remaining[0]?.label, undefined);
  assert.equal(remaining[0]?.data?.kind, "next");
});

test("removeEdgeWithRebalance promotes a case when default is deleted", () => {
  const initial: BuilderEdge[] = [
    {
      id: "default",
      source: "t1",
      target: "t2",
      label: "default",
      data: { condition: "default", kind: "branch_default" },
    },
    {
      id: "case-a",
      source: "t1",
      target: "t3",
      label: "a",
      data: { condition: "a", kind: "branch_case" },
    },
    {
      id: "case-b",
      source: "t1",
      target: "t4",
      label: "b",
      data: { condition: "b", kind: "branch_case" },
    },
  ];
  const result = removeEdgeWithRebalance({
    edges: initial,
    edgeId: "default",
  });
  assert.equal(result.error, undefined);
  const defaults = result.edges.filter((edge) => edge.label === "default");
  assert.equal(defaults.length, 1);
  assert.equal(defaults[0]?.id, "case-a");
  assert.equal(defaults[0]?.data?.kind, "branch_default");
});
