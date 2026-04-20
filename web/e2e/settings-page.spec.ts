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

async function mockSettingsApi(page: Page, role: "viewer" | "operator" | "admin"): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      await ok(route, {
        tts_cache_enabled: true,
        destinations_enabled: false,
        ai_scenarios_enabled: true,
        provider_degraded: false,
        harness_degraded: false,
        harness_state: "closed",
        provider_circuits: [],
      });
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

    if (pathname === "/providers/available" && method === "GET") {
      await ok(route, {
        items: [
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            runtime_scopes: ["judge"],
            credential_source: "db_encrypted",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
          },
          {
            provider_id: "openai:gpt-4o-mini-tts",
            vendor: "openai",
            model: "gpt-4o-mini-tts",
            capability: "tts",
            runtime_scopes: ["agent", "api"],
            credential_source: "env",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
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

test("settings surfaces tenant provider quota and access for operator-capable roles", async ({
  page,
}) => {
  await installAuthSession(page, { role: "admin" });
  await mockSettingsApi(page, "admin");

  await page.goto("/settings");

  await expect(page.getByTestId("settings-provider-quota-card")).toBeVisible();
  await expect(page.getByText("Provider usage & quotas")).toBeVisible();
  await expect(
    page
      .getByTestId("settings-provider-quota-warning-panel")
      .getByText(/provider quota needs attention/i)
  ).toBeVisible();
  await expect(
    page
      .getByTestId("settings-provider-quota-card")
      .getByText("anthropic:claude-sonnet-4-6", { exact: true })
  ).toBeVisible();
  await expect(
    page
      .getByTestId("settings-provider-quota-card")
      .getByText("openai:gpt-4o-mini-tts", { exact: true })
  ).toBeVisible();
  await expect(page.getByTestId("settings-tenant-provider-access-card")).toBeVisible();
});

test("settings surfaces provider quota for operator role (exact floor)", async ({ page }) => {
  await installAuthSession(page, { role: "operator" });
  await mockSettingsApi(page, "operator");

  await page.goto("/settings");

  await expect(page.getByTestId("settings-provider-quota-card")).toBeVisible();
  await expect(page.getByTestId("settings-provider-visibility-card")).toHaveCount(0);
});

test("settings hides provider quota surface for viewer role", async ({ page }) => {
  await installAuthSession(page, { role: "viewer" });
  await mockSettingsApi(page, "viewer");

  await page.goto("/settings");

  await expect(page.getByTestId("settings-provider-visibility-card")).toBeVisible();
  await expect(page.getByText(/operator role/i)).toBeVisible();
  await expect(page.getByTestId("settings-provider-quota-card")).toHaveCount(0);
});
