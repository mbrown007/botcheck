import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const SCENARIO_ID = "scenario_http_smoke";
const RUN_ID = "run_http_smoke";
const DESTINATION_ID = "dest_http_profile";
const DESTINATION_NAME = "Direct Bot API";
const DESTINATION_ENDPOINT = "https://bot.internal/chat";

interface RunsState {
  runs: Array<Record<string, unknown>>;
  createBodies: Array<Record<string, unknown>>;
}

async function mockRunsApi(page: Page, state: RunsState): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "operator" })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          destinations_enabled: true,
          ai_scenarios_enabled: true,
          harness_degraded: false,
          harness_state: "closed",
        }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: SCENARIO_ID,
            name: "HTTP Smoke Scenario",
            scenario_kind: "graph",
          },
        ]),
      });
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }

    if (pathname === "/destinations/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            destination_id: DESTINATION_ID,
            transport_profile_id: DESTINATION_ID,
            name: DESTINATION_NAME,
            protocol: "http",
            endpoint: DESTINATION_ENDPOINT,
            default_dial_target: DESTINATION_ENDPOINT,
            is_active: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]),
      });
    }

    if (pathname === "/runs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.runs),
      });
    }

    if (pathname === "/runs/" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.createBodies.push(body);
      const run = {
        run_id: RUN_ID,
        scenario_id: SCENARIO_ID,
        state: "pending",
        trigger_source: "manual",
        transport: "http",
        destination_id_at_start: DESTINATION_ID,
        transport_profile_id_at_start: DESTINATION_ID,
        dial_target_at_start: DESTINATION_ENDPOINT,
        created_at: new Date().toISOString(),
        gate_result: null,
        events: [],
        conversation: [],
      };
      state.runs = [run];
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(run),
      });
    }

    if (pathname === `/runs/${RUN_ID}` && method === "GET") {
      const run = state.runs[0];
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(run),
      });
    }

    if (pathname === `/scenarios/${SCENARIO_ID}` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: SCENARIO_ID,
          name: "HTTP Smoke Scenario",
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

test.describe("@smoke Runs direct HTTP transport", () => {
  test("creates a run with an HTTP transport profile and shows operator-facing attribution", async ({ page }) => {
    const state: RunsState = {
      runs: [],
      createBodies: [],
    };

    await installAuthSession(page, { role: "operator" });
    await mockRunsApi(page, state);
    await page.goto("/runs");

    await page.getByRole("button", { name: "New Run" }).click();
    await page.getByTestId("create-run-graph-scenario-id").selectOption(SCENARIO_ID);
    await page.getByTestId("create-run-destination-id").selectOption(DESTINATION_ID);

    await expect(page.getByText("Will use Direct Bot API's default endpoint: https://bot.internal/chat.")).toBeVisible();

    await page.getByRole("button", { name: "Create Run" }).click();
    await expect(page.getByText("Run Monitor")).toBeVisible();
    await expect(page.getByText(DESTINATION_ID, { exact: true }).first()).toBeVisible();
    await expect(page.getByText(DESTINATION_ENDPOINT, { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();

    await expect(page.getByText(`transport: ${DESTINATION_NAME} (${DESTINATION_ID}) · target: ${DESTINATION_ENDPOINT}`)).toBeVisible();

    expect(state.createBodies).toHaveLength(1);
    expect(state.createBodies[0]).toEqual({
      scenario_id: SCENARIO_ID,
      transport_profile_id: DESTINATION_ID,
    });
  });
});
