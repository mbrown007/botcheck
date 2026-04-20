import test from "node:test";
import assert from "node:assert/strict";
import { formatScoreReasoning } from "@/lib/score-reasoning";

test("formatScoreReasoning returns plain summary when no structured suffix exists", () => {
  const result = formatScoreReasoning("The bot answered correctly.");
  assert.equal(result.summary, "The bot answered correctly.");
  assert.deepEqual(result.details, []);
});

test("formatScoreReasoning formats timing and failures into readable detail lines", () => {
  const result = formatScoreReasoning(
    "The conversation completed cleanly. | timing(p95_gap_ms=36, interruptions=1, long_pauses=0, interruption_recovery_pct=83.33, turn_taking_efficiency_pct=83.33) | failures=interruption_recovery_pct=83.33 < 90.00; turn_taking_efficiency_pct=83.33 < 95.00"
  );

  assert.equal(result.summary, "The conversation completed cleanly.");
  assert.deepEqual(result.details, [
    "Timing: P95 response gap: 36 ms, Interruptions: 1, Long pauses: 0, Interruption recovery: 83.33%, Turn-taking efficiency: 83.33%",
    "Failures: Interruption recovery: 83.33% < 90.00%; Turn-taking efficiency: 83.33% < 95.00%",
  ]);
});

test("formatScoreReasoning renders timing-within-thresholds cleanly", () => {
  const result = formatScoreReasoning(
    "No reliability issue. | timing(p95_gap_ms=24, interruptions=0, long_pauses=0, interruption_recovery_pct=100.00, turn_taking_efficiency_pct=100.00) | timing_within_thresholds"
  );

  assert.equal(result.summary, "No reliability issue.");
  assert.equal(result.details[1], "Timing was within configured thresholds.");
});
