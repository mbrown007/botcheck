import assert from "node:assert/strict";
import test from "node:test";

import { derivePlaygroundDebugEntries } from "@/lib/playground-debug";

test("derivePlaygroundDebugEntries maps harness debug events in order", () => {
  const entries = derivePlaygroundDebugEntries([
    {
      run_id: "run_1",
      sequence_number: 4,
      event_type: "harness.classifier_input",
      payload: { transcript: "What date works for you?" },
      created_at: "2026-03-12T10:00:00Z",
    },
    {
      run_id: "run_1",
      sequence_number: 5,
      event_type: "harness.classifier_output",
      payload: { selected_case: "continue", confidence: 0.82 },
      created_at: "2026-03-12T10:00:01Z",
    },
    {
      run_id: "run_1",
      sequence_number: 6,
      event_type: "harness.caller_reasoning",
      payload: { summary: "Continue by proposing a concrete appointment time." },
      created_at: "2026-03-12T10:00:02Z",
    },
  ]);

  assert.deepEqual(entries, [
    {
      sequenceNumber: 4,
      kind: "classifier_input",
      title: "Classifier input",
      body: "What date works for you?",
      confidence: null,
    },
    {
      sequenceNumber: 5,
      kind: "classifier_output",
      title: "Classifier output",
      body: "continue",
      confidence: 0.82,
    },
    {
      sequenceNumber: 6,
      kind: "reasoning",
      title: "Caller reasoning",
      body: "Continue by proposing a concrete appointment time.",
      confidence: null,
    },
  ]);
});
