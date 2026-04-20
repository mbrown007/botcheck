import assert from "node:assert/strict";
import test from "node:test";
import { getScenarioSchemaHint } from "@/lib/scenario-schema-hints";

test("getScenarioSchemaHint exposes required root-field metadata", () => {
  const hint = getScenarioSchemaHint(["type"]);
  assert.ok(hint);
  assert.match(hint, /required/);
  assert.match(hint, /one of:/);
});

test("getScenarioSchemaHint exposes nested runtime defaults and ranges", () => {
  const hint = getScenarioSchemaHint(["config", "max_total_turns"]);
  assert.equal(hint, "integer · >= 1 · default 50");
});

test("getScenarioSchemaHint returns null for unknown paths", () => {
  assert.equal(getScenarioSchemaHint(["config", "definitely_missing"]), null);
});
