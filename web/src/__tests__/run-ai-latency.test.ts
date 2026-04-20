import assert from "node:assert/strict";
import test from "node:test";
import {
  aiLatencyDegradedComponents,
  deriveAiLatencyBreakdown,
  formatLatencyMs,
  hasAiLatencySamples,
} from "../lib/run-ai-latency";

test("deriveAiLatencyBreakdown summarizes reply gap and transcript timings", () => {
  const breakdown = deriveAiLatencyBreakdown([
    {
      turn_id: "bot-1",
      speaker: "bot",
      text: "Hello",
      audio_start_ms: 0,
      audio_end_ms: 300,
    },
    {
      turn_id: "harness-1",
      speaker: "harness",
      text: "Hi there",
      audio_start_ms: 500,
      audio_end_ms: 900,
    },
    {
      turn_id: "bot-2",
      speaker: "bot",
      text: "How can I help?",
      audio_start_ms: 1000,
      audio_end_ms: 1450,
    },
    {
      turn_id: "harness-2",
      speaker: "harness",
      text: "My flight is delayed.",
      audio_start_ms: 1750,
      audio_end_ms: 2150,
    },
  ]);

  assert.deepEqual(breakdown.replyGap, {
    samples: 2,
    avgMs: 250,
    p95Ms: 300,
    maxMs: 300,
  });
  assert.deepEqual(breakdown.botTurnDuration, {
    samples: 2,
    avgMs: 375,
    p95Ms: 450,
    maxMs: 450,
  });
  assert.deepEqual(breakdown.harnessPlayback, {
    samples: 2,
    avgMs: 400,
    p95Ms: 400,
    maxMs: 400,
  });
});

test("deriveAiLatencyBreakdown ignores incomplete or out-of-order timings", () => {
  const breakdown = deriveAiLatencyBreakdown([
    {
      turn_id: "bot-1",
      speaker: "bot",
      text: "Hello",
      audio_start_ms: 100,
      audio_end_ms: 50,
    },
    {
      turn_id: "harness-1",
      speaker: "harness",
      text: "Hi there",
      audio_start_ms: undefined,
      audio_end_ms: 900,
    },
  ]);

  assert.equal(breakdown.replyGap.samples, 0);
  assert.equal(breakdown.botTurnDuration.samples, 0);
  assert.equal(breakdown.harnessPlayback.samples, 0);
});

test("deriveAiLatencyBreakdown preserves zero-width bot turns as explicit samples", () => {
  const breakdown = deriveAiLatencyBreakdown([
    {
      turn_id: "bot-1",
      speaker: "bot",
      text: "Hello. And thank you for calling.",
      audio_start_ms: 0,
      audio_end_ms: 0,
    },
    {
      turn_id: "harness-1",
      speaker: "harness",
      text: "Hi there! Can you hear me clearly?",
      audio_start_ms: 7537,
      audio_end_ms: 12385,
    },
    {
      turn_id: "bot-2",
      speaker: "bot",
      text: "I can hear you clearly.",
      audio_start_ms: 12404,
      audio_end_ms: 12404,
    },
  ]);

  assert.deepEqual(breakdown.botTurnDuration, {
    samples: 2,
    avgMs: 0,
    p95Ms: 0,
    maxMs: 0,
  });
  assert.deepEqual(breakdown.harnessPlayback, {
    samples: 1,
    avgMs: 4848,
    p95Ms: 4848,
    maxMs: 4848,
  });
});

test("hasAiLatencySamples reports whether any latency bucket has persisted samples", () => {
  assert.equal(
    hasAiLatencySamples({
      replyGap: { samples: 0, avgMs: null, p95Ms: null, maxMs: null },
      botTurnDuration: { samples: 0, avgMs: null, p95Ms: null, maxMs: null },
      harnessPlayback: { samples: 0, avgMs: null, p95Ms: null, maxMs: null },
    }),
    false,
  );

  assert.equal(
    hasAiLatencySamples({
      replyGap: { samples: 0, avgMs: null, p95Ms: null, maxMs: null },
      botTurnDuration: { samples: 2, avgMs: 0, p95Ms: 0, maxMs: 0 },
      harnessPlayback: { samples: 1, avgMs: 4848, p95Ms: 4848, maxMs: 4848 },
    }),
    true,
  );
});

test("aiLatencyDegradedComponents returns only relevant live AI agent circuits", () => {
  const degraded = aiLatencyDegradedComponents([
    {
      source: "agent",
      provider: "openai",
      service: "tts",
      component: "agent_live_tts",
      state: "open",
    },
    {
      source: "agent",
      provider: "openai",
      service: "llm",
      component: "agent_ai_caller",
      state: "half_open",
    },
    {
      source: "api",
      provider: "openai",
      service: "tts",
      component: "api_preview",
      state: "open",
    },
  ]);

  assert.deepEqual(degraded, ["agent_live_tts:open", "agent_ai_caller:half_open"]);
});

test("formatLatencyMs formats finite values and blanks empty ones", () => {
  assert.equal(formatLatencyMs(249.4), "249 ms");
  assert.equal(formatLatencyMs(null), "—");
});
