import assert from "node:assert/strict";
import test from "node:test";

import type {
  GraiEvalRunHistorySummary,
  RunResponse,
  ScheduleResponse,
  TenantProviderQuotaListResponse,
  TenantProviderUsageListResponse,
} from "@/lib/api";
import {
  buildDashboardQuotaSections,
  buildDashboardQuotaWarningSummary,
  buildPlatformHealthItems,
  formatDashboardRelativeTime,
  summarizeTenantDashboard,
} from "@/components/dashboard/tenant-dashboard-data";

function makeRun(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    run_id: "run_1",
    scenario_id: "scenario_1",
    run_type: "standard",
    retention_profile: "standard",
    summary: "",
    transport: "sip",
    trigger_source: "manual",
    state: "complete",
    scores: {},
    findings: [],
    failed_dimensions: [],
    conversation: [],
    created_at: "2026-03-17T10:00:00Z",
    schedule_id: null,
    gate_result: null,
    tts_cache_status_at_start: null,
    cost_pence: null,
    events: [],
    transport_profile_id_at_start: null,
    dial_target_at_start: null,
    ...overrides,
  };
}

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
    name: "Daily smoke",
    ...overrides,
  };
}

function makeEvalRun(overrides: Partial<GraiEvalRunHistorySummary> = {}): GraiEvalRunHistorySummary {
  return {
    eval_run_id: "gerun_1",
    suite_id: "suite_1",
    transport_profile_id: "dest_1",
    transport_profile_ids: ["dest_1"],
    destination_count: 1,
    destinations: [
      {
        destination_index: 0,
        transport_profile_id: "dest_1",
        label: "Primary HTTP bot",
      },
    ],
    status: "complete",
    trigger_source: "manual",
    schedule_id: null,
    triggered_by: "user_1",
    prompt_count: 2,
    case_count: 2,
    total_pairs: 4,
    dispatched_count: 4,
    completed_count: 4,
    failed_count: 0,
    created_at: "2026-03-17T09:15:00Z",
    updated_at: "2026-03-17T09:17:00Z",
    ...overrides,
  };
}

test("summarizeTenantDashboard prioritizes scheduled risk and recent failures", () => {
  const now = new Date("2026-03-17T12:00:00Z");
  const summary = summarizeTenantDashboard({
    now,
    runs: [
      makeRun({
        run_id: "run_sched_failed",
        trigger_source: "schedule",
        schedule_id: "sched_alerting",
        state: "failed",
        created_at: "2026-03-17T11:20:00Z",
      }),
      makeRun({
        run_id: "run_sched_ok",
        trigger_source: "schedule",
        schedule_id: "sched_alerting",
        state: "complete",
        created_at: "2026-03-17T10:20:00Z",
      }),
      makeRun({
        run_id: "run_manual_failed",
        state: "error",
        created_at: "2026-03-17T09:20:00Z",
      }),
      makeRun({
        run_id: "run_old_failed",
        trigger_source: "schedule",
        schedule_id: "sched_old",
        state: "failed",
        created_at: "2026-03-15T09:20:00Z",
      }),
    ],
    schedules: [
      makeSchedule({
        schedule_id: "sched_alerting",
        retry_on_failure: true,
        consecutive_failures: 2,
      }),
      makeSchedule({
        schedule_id: "sched_normal",
        name: "Standard run",
        retry_on_failure: false,
        consecutive_failures: 1,
      }),
    ],
    evalRuns: [
      makeEvalRun(),
      makeEvalRun({
        eval_run_id: "gerun_failed",
        status: "failed",
        failed_count: 2,
        created_at: "2026-03-17T11:45:00Z",
        updated_at: "2026-03-17T11:46:00Z",
      }),
    ],
  });

  assert.equal(summary.scheduledRuns24h, 2);
  assert.equal(summary.recentScheduledFailures24h, 1);
  assert.equal(summary.totalRuns24h, 3);
  assert.equal(summary.failedRuns24h, 2);
  assert.equal(summary.alertingSchedules.length, 1);
  assert.equal(summary.alertingSchedules[0]?.schedule_id, "sched_alerting");
  assert.equal(summary.lastFailedScheduledRun?.run_id, "run_sched_failed");
  assert.equal(summary.recentFailedRuns[0]?.run_id, "run_sched_failed");
  assert.equal(summary.evalRuns24h, 2);
  assert.equal(summary.failedEvalRuns24h, 1);
  assert.equal(summary.lastEvalRun?.eval_run_id, "gerun_failed");
  assert.equal(summary.activity.length, 12);
});

test("buildPlatformHealthItems reflects api, provider, and harness states", () => {
  const items = buildPlatformHealthItems({
    health: {
      status: "ok",
      service: "botcheck-api",
    },
    features: {
      tts_cache_enabled: true,
      provider_degraded: true,
      harness_degraded: false,
      harness_state: "closed",
      provider_circuits: [
        {
          source: "api",
          provider: "openai",
          service: "responses",
          component: "llm",
          state: "open",
        },
      ],
    },
  });

  assert.equal(items[0]?.status, "healthy");
  assert.equal(items[1]?.tone, "warn");
  assert.match(items[1]?.detail ?? "", /1 provider circuit open/);
  assert.equal(items[2]?.tone, "pass");
});

test("formatDashboardRelativeTime renders recent timestamps readably", () => {
  const value = formatDashboardRelativeTime(
    "2026-03-17T11:30:00Z",
    new Date("2026-03-17T12:00:00Z")
  );

  assert.match(value, /30 minutes ago|half an hour ago/);
});

test("buildDashboardQuotaSections prefers quota-backed entries and falls back to partial usage", () => {
  const quota: TenantProviderQuotaListResponse = {
    window_start: "2026-03-16T12:00:00Z",
    window_end: "2026-03-17T12:00:00Z",
    items: [
      {
        provider_id: "anthropic:claude-sonnet-4-6",
        vendor: "anthropic",
        model: "claude-sonnet-4-6",
        capability: "judge",
        metrics: [
          {
            metric: "input_tokens",
            limit_per_day: 100,
            used_24h: 82,
            remaining_24h: 18,
            soft_limit_pct: 70,
            percent_used: 82,
            status: "watch",
            soft_limit_reached: true,
            hard_limit_reached: false,
          },
        ],
      },
    ],
  };
  const usage: TenantProviderUsageListResponse = {
    window_start: "2026-03-16T12:00:00Z",
    window_end: "2026-03-17T12:00:00Z",
    items: [
      {
        provider_id: "anthropic:claude-sonnet-4-6",
        vendor: "anthropic",
        model: "claude-sonnet-4-6",
        capability: "judge",
        runtime_scopes: ["judge"],
        last_recorded_at: "2026-03-17T11:50:00Z",
        input_tokens_24h: 82,
        output_tokens_24h: 20,
        audio_seconds_24h: 0,
        characters_24h: 0,
        sip_minutes_24h: 0,
        request_count_24h: 1,
        calculated_cost_microcents_24h: 900,
      },
      {
        provider_id: "openai:gpt-4o-mini-tts",
        vendor: "openai",
        model: "gpt-4o-mini-tts",
        capability: "tts",
        runtime_scopes: ["agent", "api"],
        last_recorded_at: "2026-03-17T11:40:00Z",
        input_tokens_24h: 0,
        output_tokens_24h: 0,
        audio_seconds_24h: 0,
        characters_24h: 240,
        sip_minutes_24h: 0,
        request_count_24h: 2,
        calculated_cost_microcents_24h: 120,
      },
    ],
  };

  const sections = buildDashboardQuotaSections({ quota, usage });

  assert.equal(sections[0]?.key, "llm");
  assert.equal(sections[0]?.state, "ready");
  assert.equal(sections[0]?.entries[0]?.providerId, "anthropic:claude-sonnet-4-6");
  assert.equal(sections[0]?.entries[0]?.badgeLabel, "watch");
  assert.equal(sections[1]?.key, "speech");
  assert.equal(sections[1]?.state, "partial");
  assert.equal(sections[1]?.entries[0]?.providerId, "openai:gpt-4o-mini-tts");
  assert.equal(sections[1]?.entries[0]?.badgeLabel, "usage only");
  assert.equal(sections[2]?.key, "sip");
  assert.equal(sections[2]?.state, "empty");
});

test("buildDashboardQuotaSections selects hard_limit_reached metric over soft_limit_reached", () => {
  const quota: TenantProviderQuotaListResponse = {
    window_start: "2026-03-16T12:00:00Z",
    window_end: "2026-03-17T12:00:00Z",
    items: [
      {
        provider_id: "anthropic:claude-sonnet-4-6",
        vendor: "anthropic",
        model: "claude-sonnet-4-6",
        capability: "judge",
        metrics: [
          {
            metric: "output_tokens",
            limit_per_day: 100,
            used_24h: 75,
            remaining_24h: 25,
            soft_limit_pct: 70,
            percent_used: 75,
            status: "watch",
            soft_limit_reached: true,
            hard_limit_reached: false,
          },
          {
            metric: "input_tokens",
            limit_per_day: 100,
            used_24h: 100,
            remaining_24h: 0,
            soft_limit_pct: 70,
            percent_used: 100,
            status: "exceeded",
            soft_limit_reached: true,
            hard_limit_reached: true,
          },
        ],
      },
    ],
  };

  const sections = buildDashboardQuotaSections({ quota, usage: { window_start: "", window_end: "", items: [] } });

  assert.equal(sections[0]?.entries[0]?.badgeLabel, "exceeded");
  assert.equal(sections[0]?.entries[0]?.status, "fail");
});

test("buildDashboardQuotaWarningSummary prioritizes hard limits, then soft limits, then policy gaps", () => {
  const warningSummary = buildDashboardQuotaWarningSummary(
    buildDashboardQuotaSections({
      quota: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            metrics: [
              {
                metric: "input_tokens",
                limit_per_day: 100,
                used_24h: 100,
                remaining_24h: 0,
                soft_limit_pct: 70,
                percent_used: 100,
                status: "exceeded",
                soft_limit_reached: true,
                hard_limit_reached: true,
              },
            ],
          },
        ],
      },
      usage: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            runtime_scopes: ["judge"],
            last_recorded_at: "2026-03-17T11:50:00Z",
            input_tokens_24h: 100,
            output_tokens_24h: 20,
            audio_seconds_24h: 0,
            characters_24h: 0,
            sip_minutes_24h: 0,
            request_count_24h: 1,
            calculated_cost_microcents_24h: 900,
          },
          {
            provider_id: "openai:gpt-4o-mini-tts",
            vendor: "openai",
            model: "gpt-4o-mini-tts",
            capability: "tts",
            runtime_scopes: ["agent"],
            last_recorded_at: "2026-03-17T11:40:00Z",
            input_tokens_24h: 0,
            output_tokens_24h: 0,
            audio_seconds_24h: 0,
            characters_24h: 240,
            sip_minutes_24h: 0,
            request_count_24h: 2,
            calculated_cost_microcents_24h: 120,
          },
        ],
      },
    })
  );

  assert.equal(warningSummary.tone, "fail");
  assert.match(warningSummary.title, /over limit/i);
  assert.equal(warningSummary.items[0]?.tone, "fail");
});

test("buildDashboardQuotaWarningSummary returns healthy when there are no quota issues", () => {
  const warningSummary = buildDashboardQuotaWarningSummary(
    buildDashboardQuotaSections({
      quota: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            metrics: [
              {
                metric: "input_tokens",
                limit_per_day: 100,
                used_24h: 20,
                remaining_24h: 80,
                soft_limit_pct: 70,
                percent_used: 20,
                status: "healthy",
                soft_limit_reached: false,
                hard_limit_reached: false,
              },
            ],
          },
        ],
      },
      usage: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            runtime_scopes: ["judge"],
            last_recorded_at: "2026-03-17T11:50:00Z",
            input_tokens_24h: 20,
            output_tokens_24h: 5,
            audio_seconds_24h: 0,
            characters_24h: 0,
            sip_minutes_24h: 0,
            request_count_24h: 1,
            calculated_cost_microcents_24h: 200,
          },
        ],
      },
    })
  );

  assert.equal(warningSummary.tone, "pass");
  assert.match(warningSummary.title, /headroom looks healthy/i);
  assert.equal(warningSummary.items.length, 0);
});

test("buildDashboardQuotaWarningSummary returns warn tone when only soft limits are crossed", () => {
  const warningSummary = buildDashboardQuotaWarningSummary(
    buildDashboardQuotaSections({
      quota: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            metrics: [
              {
                metric: "input_tokens",
                limit_per_day: 100,
                used_24h: 75,
                remaining_24h: 25,
                soft_limit_pct: 70,
                percent_used: 75,
                status: "watch",
                soft_limit_reached: true,
                hard_limit_reached: false,
              },
            ],
          },
        ],
      },
      usage: { window_start: "", window_end: "", items: [] },
    })
  );

  assert.equal(warningSummary.tone, "warn");
  assert.match(warningSummary.title, /needs attention/i);
  assert.equal(warningSummary.items[0]?.tone, "warn");
  assert.equal(warningSummary.items[0]?.badgeLabel, "watch");
});

test("buildDashboardQuotaWarningSummary returns info tone when only usage-only providers exist", () => {
  const warningSummary = buildDashboardQuotaWarningSummary(
    buildDashboardQuotaSections({
      quota: { window_start: "", window_end: "", items: [] },
      usage: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "openai:gpt-4o-mini-tts",
            vendor: "openai",
            model: "gpt-4o-mini-tts",
            capability: "tts",
            runtime_scopes: ["agent", "api"],
            last_recorded_at: "2026-03-17T11:40:00Z",
            input_tokens_24h: 0,
            output_tokens_24h: 0,
            audio_seconds_24h: 0,
            characters_24h: 240,
            sip_minutes_24h: 0,
            request_count_24h: 2,
            calculated_cost_microcents_24h: 120,
          },
        ],
      },
    })
  );

  assert.equal(warningSummary.tone, "info");
  assert.match(warningSummary.title, /no quota policy/i);
  assert.equal(warningSummary.items[0]?.tone, "info");
  assert.equal(warningSummary.items[0]?.badgeLabel, "no policy");
});

test("buildDashboardQuotaWarningSummary includes info count in warn detail when both exist", () => {
  const warningSummary = buildDashboardQuotaWarningSummary(
    buildDashboardQuotaSections({
      quota: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            metrics: [
              {
                metric: "input_tokens",
                limit_per_day: 100,
                used_24h: 75,
                remaining_24h: 25,
                soft_limit_pct: 70,
                percent_used: 75,
                status: "watch",
                soft_limit_reached: true,
                hard_limit_reached: false,
              },
            ],
          },
        ],
      },
      usage: {
        window_start: "2026-03-16T12:00:00Z",
        window_end: "2026-03-17T12:00:00Z",
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            runtime_scopes: ["judge"],
            last_recorded_at: "2026-03-17T11:50:00Z",
            input_tokens_24h: 75,
            output_tokens_24h: 20,
            audio_seconds_24h: 0,
            characters_24h: 0,
            sip_minutes_24h: 0,
            request_count_24h: 1,
            calculated_cost_microcents_24h: 800,
          },
          {
            provider_id: "openai:gpt-4o-mini-tts",
            vendor: "openai",
            model: "gpt-4o-mini-tts",
            capability: "tts",
            runtime_scopes: ["agent"],
            last_recorded_at: "2026-03-17T11:40:00Z",
            input_tokens_24h: 0,
            output_tokens_24h: 0,
            audio_seconds_24h: 0,
            characters_24h: 240,
            sip_minutes_24h: 0,
            request_count_24h: 2,
            calculated_cost_microcents_24h: 120,
          },
        ],
      },
    })
  );

  // Warn takes precedence over info; detail mentions the usage-only gap
  assert.equal(warningSummary.tone, "warn");
  assert.match(warningSummary.detail, /no quota policy/i);
});
