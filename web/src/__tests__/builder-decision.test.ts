import test from "node:test";
import assert from "node:assert/strict";
import {
  decisionConditionForSlot,
  decisionHandleId,
  decisionOutputSlots,
  inferDecisionSlotFromEdge,
  parseDecisionHandleSlot,
  decisionSlotLabel,
} from "../lib/builder-decision";
import type { BuilderEdge } from "../lib/flow-translator";

test("decisionOutputSlots returns default plus path slots", () => {
  assert.deepEqual(decisionOutputSlots(1), ["default"]);
  assert.deepEqual(decisionOutputSlots(3), ["default", "path_1", "path_2"]);
});

test("decisionHandleId and parseDecisionHandleSlot round-trip", () => {
  const handleId = decisionHandleId("path_2");
  assert.equal(handleId, "decision-output:path_2");
  assert.equal(parseDecisionHandleSlot(handleId), "path_2");
  assert.equal(parseDecisionHandleSlot(""), null);
});

test("inferDecisionSlotFromEdge prefers source handle then condition", () => {
  const handleEdge: BuilderEdge = {
    id: "e1",
    source: "t1",
    target: "t2",
    sourceHandle: "decision-output:path_1",
    label: "billing support",
    data: { condition: "billing support", kind: "branch_case" },
  };
  assert.equal(inferDecisionSlotFromEdge(handleEdge), "path_1");

  const conditionEdge: BuilderEdge = {
    id: "e2",
    source: "t1",
    target: "t3",
    label: "path_2",
    data: { condition: "path_2", kind: "branch_case" },
  };
  assert.equal(inferDecisionSlotFromEdge(conditionEdge), "path_2");

  const defaultEdge: BuilderEdge = {
    id: "e3",
    source: "t1",
    target: "t4",
    label: "default",
    data: { condition: "default", kind: "branch_default" },
  };
  assert.equal(inferDecisionSlotFromEdge(defaultEdge), "default");
});

test("decisionSlotLabel humanizes path slots", () => {
  assert.equal(decisionSlotLabel("default"), "default");
  assert.equal(decisionSlotLabel("path_3"), "option 3");
  assert.equal(decisionSlotLabel("custom"), "custom");
});

test("decisionConditionForSlot prefers the user label over the raw slot name", () => {
  assert.equal(
    decisionConditionForSlot("path_1", {
      path_1: "billing support",
    }),
    "billing support"
  );
  assert.equal(
    decisionConditionForSlot("path_1", {
      path_1: "   ",
    }),
    "path_1"
  );
  assert.equal(decisionConditionForSlot("default", { default: "ignored" }), "default");
});
