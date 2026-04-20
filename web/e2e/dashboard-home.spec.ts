import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockDashboardApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "admin" })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      await ok(route, {
        tts_cache_enabled: true,
        destinations_enabled: true,
        ai_scenarios_enabled: true,
        provider_degraded: false,
        harness_degraded: false,
        harness_state: "closed",
        provider_circuits: [],
      });
      return;
    }

    if (pathname === "/health" && method === "GET") {
      await ok(route, {
        status: "ok",
        service: "botcheck-api",
      });
      return;
    }

    if (pathname === "/runs/" && method === "GET") {
      await ok(route, [
        {
          run_id: "run_sched_failed",
          scenario_id: "scenario_alpha",
          run_type: "standard",
          retention_profile: "standard",
          summary: "",
          transport: "sip",
          trigger_source: "schedule",
          triggered_by: "scheduler",
          state: "failed",
          created_at: "2026-03-17T11:40:00Z",
          schedule_id: "sched_alpha",
          scores: {},
          findings: [],
          failed_dimensions: [],
          conversation: [],
        },
        {
          run_id: "run_sched_ok",
          scenario_id: "scenario_alpha",
          run_type: "standard",
          retention_profile: "standard",
          summary: "",
          transport: "sip",
          trigger_source: "schedule",
          triggered_by: "scheduler",
          state: "complete",
          created_at: "2026-03-17T10:15:00Z",
          schedule_id: "sched_alpha",
          scores: {},
          findings: [],
          failed_dimensions: [],
          conversation: [],
        },
        {
          run_id: "run_manual_failed",
          scenario_id: "scenario_beta",
          run_type: "standard",
          retention_profile: "standard",
          summary: "",
          transport: "http",
          trigger_source: "manual",
          triggered_by: "user_e2e",
          state: "error",
          created_at: "2026-03-17T09:00:00Z",
          schedule_id: null,
          scores: {},
          findings: [],
          failed_dimensions: [],
          conversation: [],
        },
      ]);
      return;
    }

    if (pathname === "/schedules/" && method === "GET") {
      await ok(route, [
        {
          schedule_id: "sched_alpha",
          name: "Morning smoke",
          target_type: "scenario",
          scenario_id: "scenario_alpha",
          ai_scenario_id: null,
          pack_id: null,
          active: true,
          cron_expr: "0 9 * * *",
          timezone: "UTC",
          next_run_at: "2026-03-18T09:00:00Z",
          last_run_at: "2026-03-17T11:40:00Z",
          last_status: "failed",
          last_run_outcome: "failed",
          retry_on_failure: true,
          consecutive_failures: 2,
          misfire_policy: "skip",
          config_overrides: null,
          created_at: "2026-03-15T08:00:00Z",
          updated_at: "2026-03-17T11:41:00Z",
        },
      ]);
      return;
    }

    if (pathname === "/grai/suites" && method === "GET") {
      await ok(route, [
        {
          suite_id: "suite_eval_1",
          name: "HTTP billing suite",
          description: "Billing smoke coverage",
          prompt_count: 2,
          case_count: 2,
          has_source_yaml: true,
          created_at: "2026-03-15T08:00:00Z",
          updated_at: "2026-03-17T08:00:00Z",
        },
      ]);
      return;
    }

    if (pathname === "/grai/suites/suite_eval_1/runs" && method === "GET") {
      await ok(route, [
        {
          eval_run_id: "gerun_latest",
          suite_id: "suite_eval_1",
          transport_profile_id: "dest_http_primary",
          transport_profile_ids: ["dest_http_primary"],
          destination_count: 1,
          destinations: [
            {
              destination_index: 0,
              transport_profile_id: "dest_http_primary",
              label: "Primary HTTP bot",
            },
          ],
          status: "failed",
          trigger_source: "manual",
          schedule_id: null,
          triggered_by: "user_e2e",
          prompt_count: 2,
          case_count: 2,
          total_pairs: 4,
          dispatched_count: 4,
          completed_count: 4,
          failed_count: 1,
          created_at: "2026-03-17T11:10:00Z",
          updated_at: "2026-03-17T11:12:00Z",
        },
      ]);
      return;
    }

    if (pathname === "/tenants/me/providers/usage" && method === "GET") {
      await ok(route, {
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
      });
      return;
    }

    if (pathname === "/tenants/me/providers/quota" && method === "GET") {
      await ok(route, {
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
      });
      return;
    }

    await route.fulfill({
      status: 404,
      body: `Unhandled route: ${pathname}`,
    });
  });
}

test("dashboard home surfaces tenant pulse and schedule risk", async ({ page }) => {
  await installAuthSession(page, { role: "admin" });
  await mockDashboardApi(page);

  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: /keep unattended automation visible/i })).toBeVisible();
  await expect(page.getByText("Alerting schedules", { exact: true })).toBeVisible();
  await expect(page.getByText(/provider quota needs attention/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /Morning smoke 2 consecutive failures/i })).toBeVisible();
  await expect(page.getByText("Grai Evals landed")).toBeVisible();
  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: /run_sched_failed/i })).toBeVisible();
  await expect(page.getByText("anthropic:claude-sonnet-4-6", { exact: true })).toBeVisible();
  await expect(page.getByText("openai:gpt-4o-mini-tts", { exact: true })).toBeVisible();
  await expect(page.getByText("usage only")).toBeVisible();
  await expect(page.getByText("No retry-alerting schedules")).toHaveCount(0);
});
