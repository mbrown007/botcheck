import test from "node:test";
import assert from "node:assert/strict";
import {
  derivePackRunMonitorPhase,
  deriveRunMonitorPhase,
  describeRunEvent,
  formatRunEventLabel,
  latestPackRunActivity,
  latestRunEvents,
} from "@/lib/run-monitor";

test("deriveRunMonitorPhase reports queued for pending runs", () => {
  const phase = deriveRunMonitorPhase({
    state: "pending",
    conversation: [],
    error_code: null,
    end_reason: null,
  });
  assert.equal(phase.label, "Queued");
  assert.equal(phase.tone, "pending");
});

test("deriveRunMonitorPhase distinguishes running setup from live conversation", () => {
  const setup = deriveRunMonitorPhase({
    state: "running",
    conversation: [],
    error_code: null,
    end_reason: null,
  });
  const live = deriveRunMonitorPhase({
    state: "running",
    conversation: [{ turn_id: "t1", speaker: "bot", text: "hello" }],
    error_code: null,
    end_reason: null,
  });
  assert.equal(setup.label, "Starting Call");
  assert.equal(live.label, "Conversation Live");
});

test("deriveRunMonitorPhase prefers explicit error detail for failures", () => {
  const phase = deriveRunMonitorPhase({
    state: "error",
    conversation: [],
    error_code: "tts_cache_unavailable",
    end_reason: "timeout",
  });
  assert.equal(phase.label, "Failed");
  assert.equal(phase.description, "tts_cache_unavailable");
});

test("formatRunEventLabel humanizes event names", () => {
  assert.equal(formatRunEventLabel("run_created"), "run created");
  assert.equal(formatRunEventLabel(""), "event");
});

test("describeRunEvent formats common event types for operators", () => {
  assert.equal(describeRunEvent({ type: "run_created" }), "Run accepted and queued for execution.");
  assert.equal(
    describeRunEvent({ type: "branch_decision", detail: { condition_matched: "refused help" } }),
    "Branch matched refused help."
  );
});

test("latestRunEvents returns newest events first and limits output", () => {
  const events = [
    { type: "a" },
    { type: "b" },
    { type: "c" },
  ];
  assert.deepEqual(latestRunEvents(events, 2).map((event) => event.type), ["c", "b"]);
});

test("derivePackRunMonitorPhase distinguishes queued running and failed states", () => {
  assert.equal(derivePackRunMonitorPhase("pending").label, "Queued");
  assert.equal(derivePackRunMonitorPhase("running").label, "Dispatching");
  assert.equal(derivePackRunMonitorPhase("partial").tone, "fail");
});

test("latestPackRunActivity formats child activity for operators", () => {
  const activity = latestPackRunActivity(
    [
      {
        pack_run_item_id: "pritem_1",
        scenario_id: "scenario_graph",
        ai_scenario_id: null,
        order_index: 0,
        scenario_version_hash: "hash",
        state: "complete",
        run_id: "run_1",
        run_state: "complete",
        gate_result: "passed",
        error_code: null,
        failure_category: null,
        summary: "Completed cleanly.",
        duration_s: 18.2,
        created_at: "2026-03-08T10:00:00Z",
      },
      {
        pack_run_item_id: "pritem_2",
        scenario_id: "scenario_ai",
        ai_scenario_id: "ai_checkout",
        order_index: 1,
        scenario_version_hash: "hash",
        state: "failed",
        run_id: "run_2",
        run_state: "error",
        gate_result: null,
        error_code: "scenario_version_mismatch",
        failure_category: "dispatch_error",
        summary: null,
        duration_s: null,
        created_at: "2026-03-08T10:05:00Z",
      },
    ],
    2,
  );

  assert.equal(activity[0]?.title, "ai_checkout");
  assert.equal(activity[0]?.statusLabel, "Dispatch Failed");
  assert.equal(activity[0]?.tone, "fail");
  assert.equal(activity[0]?.detail, "scenario_version_mismatch");
  assert.equal(activity[1]?.title, "scenario_graph");
  assert.equal(activity[1]?.statusLabel, "Complete");
  assert.equal(activity[1]?.detail, "18.2s");
});
