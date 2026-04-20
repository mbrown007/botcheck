import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

async function mockSchedulesOverviewApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "editor" })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          destinations_enabled: true,
          ai_scenarios_enabled: false,
        }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { id: "scenario_a", name: "Scenario A", scenario_kind: "graph", type: "smoke", turns: 2 },
          { id: "scenario_b", name: "Scenario B", scenario_kind: "graph", type: "smoke", turns: 2 },
        ]),
      });
    }

    if (pathname === "/destinations/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }

    if (pathname === "/schedules/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            schedule_id: "sched_card_a",
            name: "Morning billing",
            target_type: "scenario",
            scenario_id: "scenario_a",
            pack_id: null,
            active: true,
            cron_expr: "0 9 * * *",
            timezone: "UTC",
            next_run_at: new Date("2026-03-15T09:00:00Z").toISOString(),
            last_run_at: new Date("2026-03-14T09:00:00Z").toISOString(),
            last_status: "dispatched",
            last_run_outcome: "passed",
            retry_on_failure: true,
            consecutive_failures: 0,
            misfire_policy: "skip",
            config_overrides: null,
          },
          {
            schedule_id: "sched_card_b",
            name: "Weekly smoke",
            target_type: "scenario",
            scenario_id: "scenario_b",
            pack_id: null,
            active: false,
            cron_expr: "0 9 * * 1",
            timezone: "UTC",
            next_run_at: new Date("2026-03-16T09:00:00Z").toISOString(),
            last_run_at: new Date("2026-03-10T09:00:00Z").toISOString(),
            last_status: "error_dispatch",
            last_run_outcome: "failed",
            retry_on_failure: false,
            consecutive_failures: 2,
            misfire_policy: "skip",
            config_overrides: null,
          },
        ]),
      });
    }

    if (pathname === "/schedules/preview" && method === "POST") {
      const body = request.postDataJSON() as { cron_expr?: string };
      const occurrences =
        body.cron_expr === "0 9 * * *"
          ? [
              new Date("2026-03-15T09:00:00Z").toISOString(),
              new Date("2026-03-16T09:00:00Z").toISOString(),
            ]
          : [new Date("2026-03-17T09:00:00Z").toISOString()];
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          timezone: "UTC",
          occurrences,
        }),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke schedules overview", () => {
  test("renders schedule cards and compact timeline with filter", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    await mockSchedulesOverviewApi(page);

    await page.goto("/schedules");

    await expect(page.getByTestId("schedule-card-sched_card_a")).toBeVisible();
    await expect(page.getByTestId("schedule-card-sched_card_b")).toBeVisible();
    await expect(page.getByText("Run timeline", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "7d" }).click();
    await page.getByTestId("schedule-timeline-filter").selectOption("sched_card_a");

    await expect(page.getByTestId("schedule-card-sched_card_a")).toContainText("Morning billing");
    await expect(page.getByTestId("schedule-card-sched_card_b")).toContainText("Weekly smoke");
    await expect(page.getByTitle(/scheduled run/i)).toHaveCount(7);

    await page.getByTitle(/scheduled run/i).first().click();
    await expect(page.getByTestId("schedule-card-sched_card_a")).toHaveClass(/ring-2/);
  });
});
