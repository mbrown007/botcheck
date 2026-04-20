import assert from "node:assert/strict";
import test from "node:test";
import {
  connectionConditionFormSchema,
  edgeConditionEditFormSchema,
  EMPTY_CONDITION_MESSAGE,
  RESERVED_DEFAULT_CONDITION_MESSAGE,
} from "../lib/schemas/branch-condition";

test("connectionConditionFormSchema allows blank condition for auto path labels", () => {
  const parsed = connectionConditionFormSchema.safeParse({ condition: "   " });
  assert.equal(parsed.success, true);
});

test("connectionConditionFormSchema rejects reserved default condition", () => {
  const parsed = connectionConditionFormSchema.safeParse({ condition: "DEFAULT" });
  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.equal(parsed.error.issues[0]?.message, RESERVED_DEFAULT_CONDITION_MESSAGE);
});

test("edgeConditionEditFormSchema requires a non-empty condition", () => {
  const parsed = edgeConditionEditFormSchema.safeParse({ condition: "   " });
  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.equal(parsed.error.issues[0]?.message, EMPTY_CONDITION_MESSAGE);
});

test("edgeConditionEditFormSchema rejects reserved default condition", () => {
  const parsed = edgeConditionEditFormSchema.safeParse({ condition: "default" });
  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.equal(parsed.error.issues[0]?.message, RESERVED_DEFAULT_CONDITION_MESSAGE);
});

test("edgeConditionEditFormSchema trims valid labels", () => {
  const parsed = edgeConditionEditFormSchema.parse({
    condition: "  billing support  ",
  });
  assert.equal(parsed.condition, "billing support");
});
