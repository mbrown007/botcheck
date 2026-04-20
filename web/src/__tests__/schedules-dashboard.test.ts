import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SchedulesDashboard } from "@/components/schedules/schedules-dashboard";
import type { ScheduleResponse } from "@/lib/api";

function makeSchedule(overrides: Partial<ScheduleResponse> = {}): ScheduleResponse {
  return {
    schedule_id: "sched_1",
    target_type: "scenario",
    scenario_id: "scenario_1",
    ai_scenario_id: null,
    pack_id: null,
    active: true,
    cron_expr: "0 9 * * *",
    timezone: "UTC",
    next_run_at: null,
    last_run_at: null,
    last_status: null,
    last_run_outcome: null,
    retry_on_failure: false,
    consecutive_failures: 0,
    misfire_policy: "skip",
    config_overrides: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

test("SchedulesDashboard renders aggregate schedule metrics", () => {
  const markup = renderToStaticMarkup(
    createElement(SchedulesDashboard, {
      schedules: [
        makeSchedule(),
        makeSchedule({
          schedule_id: "sched_2",
          retry_on_failure: true,
          last_run_outcome: "failed",
          consecutive_failures: 1,
        }),
        makeSchedule({
          schedule_id: "sched_3",
          active: false,
          retry_on_failure: true,
          last_run_outcome: "failed",
          consecutive_failures: 2,
        }),
      ],
    }),
  );

  assert.ok(markup.includes("Total Schedules"));
  assert.ok(markup.includes(">3<"));
  assert.ok(markup.includes("Retry Enabled"));
  assert.ok(markup.includes(">2<"));
  assert.ok(markup.includes("Failure Streaks"));
  assert.ok(markup.includes(">2<"));
  assert.ok(markup.includes("1 at 2+ failures"));
});

test("SchedulesDashboard returns empty markup when there are no schedules", () => {
  const markup = renderToStaticMarkup(
    createElement(SchedulesDashboard, {
      schedules: [],
    }),
  );

  assert.equal(markup, "");
});
