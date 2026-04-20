import test from "node:test";
import assert from "node:assert/strict";
import {
  addScenarioId,
  moveScenarioId,
  parseTagCsv,
  removeScenarioId,
} from "@/lib/pack-editor";

test("parseTagCsv trims, removes empties, and deduplicates", () => {
  const tags = parseTagCsv(" smoke, regression , ,smoke,voice ");
  assert.deepEqual(tags, ["smoke", "regression", "voice"]);
});

test("addScenarioId appends only unique ids", () => {
  const selected = ["s1"];
  assert.deepEqual(addScenarioId(selected, "s2"), ["s1", "s2"]);
  assert.deepEqual(addScenarioId(selected, "s1"), ["s1"]);
  assert.deepEqual(addScenarioId(selected, "  "), ["s1"]);
});

test("removeScenarioId removes a selected id", () => {
  assert.deepEqual(removeScenarioId(["s1", "s2", "s3"], "s2"), ["s1", "s3"]);
});

test("moveScenarioId reorders selected ids within bounds", () => {
  const base = ["s1", "s2", "s3"];
  assert.deepEqual(moveScenarioId(base, "s2", -1), ["s2", "s1", "s3"]);
  assert.deepEqual(moveScenarioId(base, "s2", 1), ["s1", "s3", "s2"]);
  assert.deepEqual(moveScenarioId(base, "s1", -1), base);
  assert.deepEqual(moveScenarioId(base, "s3", 1), base);
  assert.deepEqual(moveScenarioId(base, "missing", 1), base);
});
