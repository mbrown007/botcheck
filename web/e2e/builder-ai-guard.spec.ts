import { expect, test, type Page, type Route } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const AI_SCENARIO_ID = "scenario_ai_guard";

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockBuilderGuardApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "admin" })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return ok(route, {
        tts_cache_enabled: true,
        ai_scenarios_enabled: true,
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return ok(route, [
        {
          id: AI_SCENARIO_ID,
          name: "AI Backing Scenario",
          type: "reliability",
          turns: 1,
          version_hash: "v1",
          cache_status: "cold",
          scenario_kind: "ai",
        },
      ]);
    }

    if (pathname === "/scenarios/personas" && method === "GET") {
      return ok(route, []);
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      return ok(route, []);
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Builder AI guard", () => {
  test("direct builder access redirects AI scenarios to AI Scenarios", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockBuilderGuardApi(page);

    await page.goto(`/builder?id=${AI_SCENARIO_ID}`);

    await expect(page.getByRole("heading", { name: "AI Scenarios" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Scenario Builder" })
    ).toHaveCount(0);
  });
});
