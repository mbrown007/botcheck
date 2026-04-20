import assert from "node:assert/strict";
import test from "node:test";
import {
  DECISION_LABEL_RESERVED_MESSAGE,
  decisionLabelsFormSchema,
  normalizeDecisionLabelInput,
} from "../lib/schemas/decision-labels";

test("decisionLabelsFormSchema allows blank labels for slot reset", () => {
  const parsed = decisionLabelsFormSchema.safeParse({
    labels: {
      path_1: "   ",
    },
  });
  assert.equal(parsed.success, true);
});

test("decisionLabelsFormSchema rejects reserved default label", () => {
  const parsed = decisionLabelsFormSchema.safeParse({
    labels: {
      path_1: "DEFAULT",
    },
  });
  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.equal(parsed.error.issues[0]?.message, DECISION_LABEL_RESERVED_MESSAGE);
});

test("normalizeDecisionLabelInput trims and collapses whitespace", () => {
  assert.equal(
    normalizeDecisionLabelInput("  billing    support   urgent "),
    "billing support urgent"
  );
});
