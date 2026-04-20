import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const AI_SCENARIO_ID = "scenario_ai";
const GRAPH_SCENARIO_ID = "scenario_graph";

async function mockPackEditorApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (
      await maybeMockIdentityRoute(route, { pathname, method }, { role: "admin" })
    ) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tts_cache_enabled: true,
          packs_enabled: true,
          ai_scenarios_enabled: true,
        }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      const now = new Date().toISOString();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: AI_SCENARIO_ID,
            name: "Scenario AI Candidate",
            type: "reliability",
            tags: ["http"],
            turns: 2,
            version_hash: "v1",
            cache_status: "cold",
            created_at: now,
            scenario_kind: "graph",
            namespace: "support/refunds",
          },
          {
            id: GRAPH_SCENARIO_ID,
            name: "Scenario Graph Candidate",
            type: "reliability",
            tags: ["smoke", "http"],
            turns: 2,
            version_hash: "v2",
            cache_status: "cold",
            created_at: now,
            scenario_kind: "graph",
            namespace: "support/billing",
          },
        ]),
      });
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      const now = new Date().toISOString();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            ai_scenario_id: AI_SCENARIO_ID,
            name: "Scenario AI Candidate",
            namespace: "support/refunds",
            persona_id: "persona_demo",
            scoring_profile: null,
            dataset_source: null,
            record_count: 1,
            created_at: now,
            updated_at: now,
          },
        ]),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Pack editor scenario kind labels", () => {
  test("shows AI/GRAPH labels in available and selected scenario rows", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockPackEditorApi(page);

    await page.goto("/packs/new");
    await expect(page.getByRole("heading", { name: "New Pack" })).toBeVisible();

    const aiOption = page.getByTestId(`pack-scenario-option-${AI_SCENARIO_ID}`);
    const graphOption = page.getByTestId(`pack-scenario-option-${GRAPH_SCENARIO_ID}`);

    await expect(aiOption).toContainText("AI");
    await expect(graphOption).toContainText("GRAPH");

    await aiOption.getByRole("button", { name: "Add" }).click();
    await graphOption.getByRole("button", { name: "Add" }).click();

    const aiSelected = page.getByTestId(`pack-scenario-selected-${AI_SCENARIO_ID}`);
    const graphSelected = page.getByTestId(`pack-scenario-selected-${GRAPH_SCENARIO_ID}`);

    await expect(aiSelected).toContainText("AI");
    await expect(graphSelected).toContainText("GRAPH");
  });

  test("filters by namespace and bulk-adds all remaining scenarios in that namespace", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockPackEditorApi(page);

    await page.goto("/packs/new");
    await expect(page.getByRole("heading", { name: "New Pack" })).toBeVisible();

    await page.getByTestId("pack-namespace-option-support").click();
    await expect(page.getByTestId("pack-scenario-option-scenario_graph")).toBeVisible();
    await expect(page.getByTestId("pack-scenario-option-scenario_ai")).toBeVisible();

    await page.getByTestId("pack-namespace-option-support/billing").click();
    await expect(page.getByTestId("pack-add-all-from-namespace")).toContainText(
      "Add all from namespace (1)",
    );
    await expect(page.getByTestId("pack-scenario-option-scenario_graph")).toBeVisible();
    await expect(page.getByTestId("pack-scenario-option-scenario_ai")).toHaveCount(0);

    await page.getByTestId("pack-add-all-from-namespace").click();
    await expect(page.getByTestId("pack-scenario-selected-scenario_graph")).toBeVisible();
    await expect(page.getByTestId("pack-scenario-option-scenario_graph")).toHaveCount(0);
  });
});
