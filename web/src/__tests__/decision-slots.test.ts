import test from "node:test";
import assert from "node:assert/strict";
import {
  DECISION_DEFAULT_SLOT,
  decisionHandleId,
  decisionOutputSlotsFromCount,
  decisionPathSlot,
  decisionPathSlotIndex,
  parseDecisionHandleSlot,
  isDefaultDecisionSlot,
  isPathDecisionSlot,
} from "../lib/decision-slots";

test("decisionOutputSlotsFromCount returns default and indexed path slots", () => {
  assert.deepEqual(decisionOutputSlotsFromCount(1), [DECISION_DEFAULT_SLOT]);
  assert.deepEqual(decisionOutputSlotsFromCount(3), [
    DECISION_DEFAULT_SLOT,
    "path_1",
    "path_2",
  ]);
});

test("decisionPathSlot clamps values to a minimum of one", () => {
  assert.equal(decisionPathSlot(1), "path_1");
  assert.equal(decisionPathSlot(0), "path_1");
});

test("decisionHandleId and parseDecisionHandleSlot round trip", () => {
  const slot = "path_2";
  const handleId = decisionHandleId(slot);
  assert.equal(handleId, `decision-output:${slot}`);
  assert.equal(parseDecisionHandleSlot(handleId), slot);
  assert.equal(parseDecisionHandleSlot(""), null);
  assert.equal(parseDecisionHandleSlot("unexpected:path_2"), null);
});

test("decision slot predicates and path index parser behave correctly", () => {
  assert.equal(isDefaultDecisionSlot(" default "), true);
  assert.equal(isDefaultDecisionSlot("path_1"), false);
  assert.equal(isPathDecisionSlot(" path_7 "), true);
  assert.equal(isPathDecisionSlot(DECISION_DEFAULT_SLOT), false);
  assert.equal(decisionPathSlotIndex("path_3"), 3);
  assert.equal(decisionPathSlotIndex("path_0"), null);
  assert.equal(decisionPathSlotIndex("default"), null);
});
