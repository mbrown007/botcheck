import test from "node:test";
import assert from "node:assert/strict";

import { derivePlaygroundProgressNodes } from "@/lib/playground-progress";
import type { PlaygroundStreamEvent } from "@/lib/playground-stream";

const SCENARIO = {
  name: "Billing Flow",
  bot: { protocol: "http" },
  turns: [
    {
      id: "t1",
      kind: "harness_prompt",
      content: { text: "I need help with billing." },
      branching: {
        cases: [
          { condition: "billing", next: "billing_path" },
          { condition: "support", next: "support_path" },
        ],
      },
    },
    {
      id: "t2",
      kind: "bot_listen",
    },
    {
      id: "t3",
      kind: "hangup",
    },
  ],
} as const;

test("derivePlaygroundProgressNodes marks active, passed, failed, and skipped states", () => {
  const events: PlaygroundStreamEvent[] = [
    {
      run_id: "run_1",
      sequence_number: 1,
      event_type: "turn.start",
      payload: { turn_id: "t1", speaker: "harness", text: "I need help with billing." },
      created_at: "2026-03-12T10:00:00Z",
    },
    {
      run_id: "run_1",
      sequence_number: 2,
      event_type: "turn.response",
      payload: { turn_id: "t1", transcript: "I need help with billing.", latency_ms: 1 },
      created_at: "2026-03-12T10:00:00Z",
    },
    {
      run_id: "run_1",
      sequence_number: 3,
      event_type: "turn.branch",
      payload: { turn_id: "t1", selected_case: "billing" },
      created_at: "2026-03-12T10:00:01Z",
    },
    {
      run_id: "run_1",
      sequence_number: 4,
      event_type: "turn.start",
      payload: { turn_id: "t2", speaker: "bot", text: "" },
      created_at: "2026-03-12T10:00:02Z",
    },
    {
      run_id: "run_1",
      sequence_number: 5,
      event_type: "turn.expect",
      payload: { turn_id: "t2", assertion: "policy", passed: false },
      created_at: "2026-03-12T10:00:03Z",
    },
    {
      run_id: "run_1",
      sequence_number: 6,
      event_type: "run.complete",
      payload: { run_id: "run_1", summary: "done" },
      created_at: "2026-03-12T10:00:05Z",
    },
  ];

  const nodes = derivePlaygroundProgressNodes(SCENARIO as never, events);

  assert.deepEqual(
    nodes.map((node) => ({
      turnId: node.turnId,
      status: node.status,
      cases: node.caseStates,
    })),
    [
      {
        turnId: "t1",
        status: "passed",
        cases: [
          { condition: "billing", status: "selected" },
          { condition: "support", status: "dimmed" },
        ],
      },
      {
        turnId: "t2",
        status: "failed",
        cases: [],
      },
      {
        turnId: "t3",
        status: "skipped",
        cases: [],
      },
    ]
  );
});

test("derivePlaygroundProgressNodes reads canonical block kinds and content", () => {
  const nodes = derivePlaygroundProgressNodes(SCENARIO as never, []);

  assert.deepEqual(
    nodes.map((node) => ({
      turnId: node.turnId,
      speaker: node.speaker,
      textPreview: node.textPreview,
    })),
    [
      {
        turnId: "t1",
        speaker: "harness",
        textPreview: "I need help with billing.",
      },
      {
        turnId: "t2",
        speaker: "bot",
        textPreview: "Bot response",
      },
      {
        turnId: "t3",
        speaker: "harness",
        textPreview: "Hang up",
      },
    ],
  );
});
