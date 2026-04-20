import test from "node:test";
import assert from "node:assert/strict";

import {
  describePlaygroundStreamEvent,
  extractSseFrames,
  parseSseFrame,
  type PlaygroundStreamEvent,
} from "@/lib/playground-stream";

const GRAPH_SCENARIO = {
  turns: [
    {
      id: "t1",
      branching: {
        cases: [
          { condition: "billing", next: "billing_path" },
          { condition: "support", next: "support_path" },
          { condition: "sales", next: "sales_path" },
        ],
      },
    },
  ],
} as const;

test("extractSseFrames separates complete frames from trailing remainder", () => {
  const extracted = extractSseFrames(
    "id: 1\nevent: turn.start\ndata: {\"sequence_number\":1}\n\nid: 2\nevent: turn.response"
  );

  assert.deepEqual(extracted.frames, ['id: 1\nevent: turn.start\ndata: {"sequence_number":1}']);
  assert.equal(extracted.remainder, "id: 2\nevent: turn.response");
});

test("parseSseFrame returns a typed playground event", () => {
  const parsed = parseSseFrame(
    'id: 7\nevent: turn.response\ndata: {"run_id":"run_1","sequence_number":7,"event_type":"turn.response","payload":{"turn_id":"t1_bot","transcript":"Hello there","latency_ms":84},"created_at":"2026-03-12T10:00:00Z"}'
  );

  assert.deepEqual(parsed, {
    run_id: "run_1",
    sequence_number: 7,
    event_type: "turn.response",
    payload: {
      turn_id: "t1_bot",
      transcript: "Hello there",
      latency_ms: 84,
    },
    created_at: "2026-03-12T10:00:00Z",
  });
});

test("describePlaygroundStreamEvent formats conversation bubbles and expectations", () => {
  const harnessStart: PlaygroundStreamEvent = {
    run_id: "run_1",
    sequence_number: 1,
    event_type: "turn.start",
    payload: {
      turn_id: "t1",
      speaker: "harness",
      text: "Can you help with billing?",
    },
    created_at: "2026-03-12T10:00:00Z",
  };
  const botResponse: PlaygroundStreamEvent = {
    run_id: "run_1",
    sequence_number: 2,
    event_type: "turn.response",
    payload: {
      turn_id: "t1_bot",
      transcript: "Yes, I can help with billing.",
      latency_ms: 92,
    },
    created_at: "2026-03-12T10:00:01Z",
  };
  const expectation: PlaygroundStreamEvent = {
    run_id: "run_1",
    sequence_number: 3,
    event_type: "turn.expect",
    payload: {
      assertion: "transferred_to",
      passed: true,
    },
    created_at: "2026-03-12T10:00:02Z",
  };

  assert.deepEqual(describePlaygroundStreamEvent(harnessStart), {
    kind: "bubble",
    side: "right",
    title: "Harness",
    body: "Can you help with billing?",
    tone: "default",
  });
  assert.deepEqual(describePlaygroundStreamEvent(botResponse), {
    kind: "bubble",
    side: "left",
    title: "Bot",
    body: "Yes, I can help with billing.",
    tone: "default",
    collapsedDetail: "92ms",
  });
  assert.deepEqual(describePlaygroundStreamEvent(expectation), {
    kind: "expectation",
    side: "center",
    title: "Expectation",
    body: null,
    tone: "pass",
    chips: [
      { label: "transferred_to", tone: "pass" },
      { label: "passed", tone: "pass" },
    ],
  });
});

test("describePlaygroundStreamEvent shows collapsed branch alternatives from scenario order", () => {
  const branchEvent: PlaygroundStreamEvent = {
    run_id: "run_1",
    sequence_number: 4,
    event_type: "turn.branch",
    payload: {
      turn_id: "t1",
      selected_case: "billing",
    },
    created_at: "2026-03-12T10:00:03Z",
  };

  const descriptor = describePlaygroundStreamEvent(
    branchEvent,
    GRAPH_SCENARIO as never
  );

  assert.deepEqual(descriptor, {
    kind: "status",
    side: "center",
    title: "Branch Decision",
    body: "Selected billing.",
    tone: "warn",
    collapsedDetail: "2 other paths hidden",
  });
});

test("describePlaygroundStreamEvent hides harness debug events from the main feed", () => {
  const event: PlaygroundStreamEvent = {
    run_id: "run_1",
    sequence_number: 9,
    event_type: "harness.caller_reasoning",
    payload: { summary: "Continue toward the objective." },
    created_at: "2026-03-12T10:00:04Z",
  };

  assert.equal(describePlaygroundStreamEvent(event), null);
});
