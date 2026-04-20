import assert from "node:assert/strict";
import test from "node:test";
import {
  packRunFailureCategoryLabel,
  packRunFailureCategoryTone,
} from "../lib/pack-run-failure-category";

test("packRunFailureCategoryLabel returns stable labels", () => {
  assert.equal(packRunFailureCategoryLabel("dispatch_error"), "Dispatch Error");
  assert.equal(packRunFailureCategoryLabel("run_error"), "Run Error");
  assert.equal(packRunFailureCategoryLabel("gate_blocked"), "Gate Blocked");
});

test("packRunFailureCategoryLabel returns null for missing values", () => {
  assert.equal(packRunFailureCategoryLabel(null), null);
  assert.equal(packRunFailureCategoryLabel(undefined), null);
});

test("packRunFailureCategoryTone maps dispatch/run to fail and gate to warn", () => {
  assert.equal(packRunFailureCategoryTone("dispatch_error"), "text-fail");
  assert.equal(packRunFailureCategoryTone("run_error"), "text-fail");
  assert.equal(packRunFailureCategoryTone("gate_blocked"), "text-warn");
  assert.equal(packRunFailureCategoryTone(null), "text-text-muted");
});

