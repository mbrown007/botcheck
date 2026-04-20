import assert from "node:assert/strict";
import test from "node:test";
import { extractAiContextFromRunEvents } from "../lib/run-ai-context";

test("extractAiContextFromRunEvents prefers run_created snapshot", () => {
  const context = extractAiContextFromRunEvents([
    {
      type: "run_judge_enqueued",
      detail: {
        ai_context: {
          dataset_input: "MUTATED",
          expected_output: "MUTATED",
          persona_id: "persona_mutated",
        },
      },
    },
    {
      type: "run_created",
      detail: {
        ai_context: {
          dataset_input: "Original input",
          expected_output: "Original expected output",
          persona_id: "persona_001",
          persona_name: "Persona One",
          scenario_objective: "objective-x",
        },
      },
    },
  ]);

  assert.deepEqual(context, {
    dataset_input: "Original input",
    expected_output: "Original expected output",
    persona_id: "persona_001",
    persona_name: "Persona One",
    scenario_objective: "objective-x",
  });
});

test("extractAiContextFromRunEvents falls back to judge payload when needed", () => {
  const context = extractAiContextFromRunEvents([
    {
      type: "run_judge_enqueued",
      detail: {
        ai_context: {
          dataset_input: "Fallback input",
          expected_output: "Fallback expected output",
          persona_id: "persona_fallback",
        },
      },
    },
  ]);
  assert.deepEqual(context, {
    dataset_input: "Fallback input",
    expected_output: "Fallback expected output",
    persona_id: "persona_fallback",
    persona_name: null,
    scenario_objective: null,
  });
});

test("extractAiContextFromRunEvents returns null for missing/invalid payloads", () => {
  assert.equal(extractAiContextFromRunEvents(undefined), null);
  assert.equal(
    extractAiContextFromRunEvents([
      { type: "run_created", detail: { ai_context: { dataset_input: "x" } } },
      { type: "run_judge_enqueued", detail: { ai_context: null } },
    ]),
    null
  );
});

