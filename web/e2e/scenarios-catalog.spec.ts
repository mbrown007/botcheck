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

async function mockScenariosCatalogApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (
      await maybeMockIdentityRoute(route, { pathname, method }, { role: "editor" })
    ) {
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
          id: "billing-smoke",
          name: "Billing Smoke",
          description: "Happy path billing support",
          namespace: "support/billing",
          scenario_kind: "graph",
          turns: 3,
          tags: ["smoke", "http"],
          type: "smoke",
          cache_status: "warm",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-1",
        },
        {
          id: "billing-jailbreak",
          name: "Billing Jailbreak Probe",
          description: "Try to derail the agent off task",
          namespace: "support/billing",
          scenario_kind: "graph",
          turns: 5,
          tags: ["adversarial", "http"],
          type: "adversarial",
          cache_status: "cold",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-2",
        },
        {
          id: "refunds-voice",
          name: "Refunds Voice Flow",
          description: "Phone support escalation path",
          namespace: "support/refunds",
          scenario_kind: "graph",
          turns: 4,
          tags: ["voice"],
          type: "smoke",
          cache_status: "cold",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-3",
        },
        {
          id: "ungrouped-sanity",
          name: "Ungrouped Sanity Check",
          description: "Loose catch-all regression",
          namespace: null,
          scenario_kind: "graph",
          turns: 2,
          tags: ["smoke"],
          type: "smoke",
          cache_status: "cold",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-4",
        },
        {
          id: "hidden-ai-backing",
          name: "AI Backing Scenario",
          description: "",
          namespace: "support/ai",
          scenario_kind: "ai",
          turns: 2,
          tags: [],
          type: "smoke",
          cache_status: "cold",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-5",
        },
      ]);
    }

    return route.continue();
  });
}

test("scenarios catalog supports namespace filtering tags and search", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockScenariosCatalogApi(page);

  await page.goto("/scenarios");

  await expect(page.getByTestId("scenario-row-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("scenario-row-billing-jailbreak")).toBeVisible();
  await expect(page.getByTestId("scenario-row-refunds-voice")).toBeVisible();
  await expect(page.getByTestId("scenario-row-ungrouped-sanity")).toBeVisible();
  await expect(page.getByText("AI Backing Scenario")).not.toBeVisible();

  await page.getByTestId("scenario-catalog-toggle-namespaces").click();
  await page.getByTestId("scenario-namespace-support").click();
  await expect(page.getByTestId("scenario-row-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("scenario-row-refunds-voice")).toBeVisible();
  await expect(page.getByTestId("scenario-row-ungrouped-sanity")).not.toBeVisible();

  await page.getByTestId("scenario-catalog-toggle-tags").click();
  await page.getByTestId("scenario-tag-http").click();
  await expect(page.getByTestId("scenario-row-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("scenario-row-billing-jailbreak")).toBeVisible();
  await expect(page.getByTestId("scenario-row-refunds-voice")).not.toBeVisible();

  await page.getByTestId("scenario-search-input").fill("jailbreak");
  await expect(page.getByTestId("scenario-row-billing-jailbreak")).toBeVisible();
  await expect(page.getByTestId("scenario-row-billing-smoke")).not.toBeVisible();

  await page.getByTestId("scenario-namespace-__ungrouped__").click();
  await expect(page.getByTestId("scenario-row-ungrouped-sanity")).not.toBeVisible();
  await page.getByRole("button", { name: /clear/i }).click();
  await expect(page.getByTestId("scenario-row-ungrouped-sanity")).toBeVisible();

  await page.getByTestId("scenario-namespace-__ungrouped__").click();
  await expect(page.getByTestId("scenario-row-ungrouped-sanity")).toBeVisible();
  await expect(page.getByTestId("scenario-row-billing-smoke")).not.toBeVisible();
});

test("scenarios catalog rail can collapse and expand without losing filters", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockScenariosCatalogApi(page);

  await page.goto("/scenarios");

  await page.getByTestId("scenario-catalog-toggle-tags").click();
  await page.getByTestId("scenario-tag-http").click();
  await expect(page.getByTestId("scenario-row-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("scenario-row-refunds-voice")).not.toBeVisible();

  await page.getByTestId("scenario-catalog-collapse-toggle").click();
  await expect(page.getByTestId("scenario-search-input")).toHaveCount(0);
  await expect(page.getByTestId("scenario-catalog-clear-collapsed")).toBeVisible();

  await page.getByTestId("scenario-catalog-collapse-toggle").click();
  await expect(page.getByTestId("scenario-search-input")).toBeVisible();
  await expect(page.getByTestId("scenario-row-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("scenario-row-refunds-voice")).not.toBeVisible();
});

test("scenarios graph action menu opens upload dialog", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockScenariosCatalogApi(page);

  await page.goto("/scenarios");

  await page.getByTestId("scenario-graph-actions-trigger").click();
  await page.getByTestId("scenario-action-upload-yaml").click();
  await expect(page.getByRole("heading", { name: "Upload Scenario" })).toBeVisible();
});

test("scenarios graph action menu routes to builder", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockScenariosCatalogApi(page);

  await page.goto("/scenarios");

  await page.getByTestId("scenario-graph-actions-trigger").click();
  await page.getByTestId("scenario-action-new-graph").click();
  await page.waitForURL("**/builder");
  await expect(page.getByTestId("builder-landing-shell")).toBeVisible();
});
