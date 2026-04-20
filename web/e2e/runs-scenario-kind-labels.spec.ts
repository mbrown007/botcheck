import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const AI_SCENARIO_ID = "scenario_ai_run";
const GRAPH_SCENARIO_ID = "scenario_graph_run";

interface RunsModalState {
  createBodies: Array<Record<string, unknown>>;
}

async function mockRunsApi(page: Page, state?: RunsModalState): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (
      await maybeMockIdentityRoute(route, { pathname, method }, { role: "operator" })
    ) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tts_cache_enabled: true,
          ai_scenarios_enabled: true,
          destinations_enabled: false,
          harness_degraded: false,
          harness_state: "open",
        }),
      });
    }

    if (pathname === "/runs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
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
            name: "AI Run Scenario",
            type: "reliability",
            turns: 2,
            version_hash: "v1",
            cache_status: "cold",
            created_at: now,
            scenario_kind: "graph",
          },
          {
            id: GRAPH_SCENARIO_ID,
            name: "Graph Run Scenario",
            type: "reliability",
            turns: 2,
            version_hash: "v2",
            cache_status: "cold",
            created_at: now,
            scenario_kind: "graph",
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
            ai_scenario_id: "ai_run_public_id",
            name: "AI Run Scenario",
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

    if (pathname === "/sip/pools" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              trunk_pool_id: "pool_uk",
              pool_name: "UK Pool",
              provider_name: "Twilio",
              tenant_label: "UK Friendly",
              is_default: true,
              is_active: true,
              member_count: 1,
            },
          ],
          total: 1,
        }),
      });
    }

    if (pathname === "/runs/" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state?.createBodies.push(body);
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: "run_sip_pool",
          scenario_id: GRAPH_SCENARIO_ID,
          state: "pending",
          trigger_source: "manual",
          transport: "sip",
          events: [],
          conversation: [],
          created_at: new Date().toISOString(),
          dial_target_at_start: body.dial_target ?? null,
          transport_profile_id_at_start: null,
        }),
      });
    }

    if (pathname === "/runs/run_sip_pool" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: "run_sip_pool",
          scenario_id: GRAPH_SCENARIO_ID,
          state: "pending",
          trigger_source: "manual",
          transport: "sip",
          events: [],
          conversation: [],
          created_at: new Date().toISOString(),
          dial_target_at_start: "+441234567890",
          transport_profile_id_at_start: null,
        }),
      });
    }

    if (pathname === `/scenarios/${GRAPH_SCENARIO_ID}` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: GRAPH_SCENARIO_ID,
          name: "Graph Run Scenario",
          scenario_kind: "graph",
          turns: [],
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

test.describe("@smoke Runs modal scenario kind labels", () => {
  test("shows AI and GRAPH labels in New Run scenario selector", async ({ page }) => {
    await installAuthSession(page, { role: "operator" });
    await mockRunsApi(page);

    await page.goto("/runs");
    await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
    await page.getByRole("button", { name: "New Run" }).click();

    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "New Run" }) });
    await expect(modal.getByTestId("create-run-graph-scenario-id")).toBeVisible();
    await expect(modal.getByTestId("create-run-ai-scenario-id")).toBeVisible();
    await expect(
      modal
        .getByTestId("create-run-graph-scenario-id")
        .locator(`option[value="${GRAPH_SCENARIO_ID}"]`)
    ).toContainText("Graph Run Scenario");
    await expect(
      modal
        .getByTestId("create-run-ai-scenario-id")
        .locator('option[value="ai_run_public_id"]')
    ).toContainText("AI Run Scenario");
  });

  test("shows destination phone number input even when destinations feature is off", async ({
    page,
  }) => {
    await installAuthSession(page, { role: "operator" });
    await mockRunsApi(page);

    await page.goto("/runs");
    await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
    await page.getByRole("button", { name: "New Run" }).click();

    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "New Run" }) });

    await expect(modal.getByTestId("create-run-bot-endpoint")).toBeVisible();
    await expect(modal.getByTestId("create-run-destination-id")).toHaveCount(0);
  });

  test("supports ad hoc SIP pool selection without a transport profile", async ({ page }) => {
    const state: RunsModalState = { createBodies: [] };
    await installAuthSession(page, { role: "operator" });
    await mockRunsApi(page, state);

    await page.goto("/runs");
    await page.getByRole("button", { name: "New Run" }).click();

    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "New Run" }) });

    await modal.getByTestId("create-run-graph-scenario-id").selectOption(GRAPH_SCENARIO_ID);
    await modal.getByTestId("create-run-bot-endpoint").fill("+441234567890");
    await modal.getByTestId("create-run-trunk-pool-id").selectOption("pool_uk");
    await expect(modal.getByText("Will dial +441234567890 through UK Friendly (pool_uk).")).toBeVisible();

    await modal.getByRole("button", { name: "Create Run" }).click();
    await expect(page.getByText("Run Monitor")).toBeVisible();

    expect(state.createBodies).toHaveLength(1);
    expect(state.createBodies[0]).toEqual({
      scenario_id: GRAPH_SCENARIO_ID,
      dial_target: "+441234567890",
      trunk_pool_id: "pool_uk",
    });
  });
});
