import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_A_ID = "pack_alpha";
const PACK_B_ID = "pack_beta";

interface MockRunSummary {
  pack_run_id: string;
  pack_id: string;
  state: string;
  gate_outcome: string;
  total_scenarios: number;
  dispatched: number;
  completed: number;
  passed: number;
  blocked: number;
  failed: number;
  trigger_source: string;
  triggered_by?: string | null;
  schedule_id?: string | null;
  destination_id?: string | null;
  created_at: string;
  updated_at: string;
}

interface FilterCapture {
  seenQueries: string[];
}

function makeRun(packRunId: string, packId: string, state: string): MockRunSummary {
  const now = new Date().toISOString();
  return {
    pack_run_id: packRunId,
    pack_id: packId,
    state,
    gate_outcome: state === "failed" ? "blocked" : "pending",
    total_scenarios: 2,
    dispatched: 2,
    completed: state === "failed" ? 2 : 1,
    passed: state === "failed" ? 1 : 1,
    blocked: state === "failed" ? 1 : 0,
    failed: state === "failed" ? 1 : 0,
    trigger_source: "manual",
    triggered_by: "qa_engineer",
    schedule_id: null,
    destination_id: null,
    created_at: now,
    updated_at: now,
  };
}

function filterRuns(
  runs: MockRunSummary[],
  params: URLSearchParams
): MockRunSummary[] {
  const packId = params.get("pack_id");
  const state = params.get("state");
  return runs.filter((run) => {
    if (packId && run.pack_id !== packId) {
      return false;
    }
    if (state && run.state !== state) {
      return false;
    }
    return true;
  });
}

async function mockPackRunsApi(page: Page, capture: FilterCapture): Promise<void> {
  const allRuns: MockRunSummary[] = [
    makeRun("packrun_alpha_1", PACK_A_ID, "running"),
    makeRun("packrun_beta_1", PACK_B_ID, "failed"),
  ];

  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname, searchParams, search } = url;
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
          packs_enabled: true,
          destinations_enabled: false,
        }),
      });
    }

    if (pathname === "/packs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            pack_id: PACK_A_ID,
            name: "Pack Alpha",
            description: "Alpha set",
            execution_mode: "parallel",
            scenario_count: 2,
            tags: ["alpha"],
          },
          {
            pack_id: PACK_B_ID,
            name: "Pack Beta",
            description: "Beta set",
            execution_mode: "parallel",
            scenario_count: 2,
            tags: ["beta"],
          },
        ]),
      });
    }

    if (pathname === "/pack-runs/" && method === "GET") {
      capture.seenQueries.push(search);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(filterRuns(allRuns, searchParams)),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Pack runs list filters", () => {
  test("sends pack/state query params and updates visible rows", async ({ page }) => {
    const capture: FilterCapture = { seenQueries: [] };
    const runsTable = page.getByRole("table");

    await installAuthSession(page, { role: "operator" });
    await mockPackRunsApi(page, capture);

    await page.goto("/pack-runs");
    await expect(page.getByRole("heading", { name: "Pack Runs" })).toBeVisible();

    await expect(runsTable.getByText("Pack Alpha")).toBeVisible();
    await expect(runsTable.getByText("Pack Beta")).toBeVisible();

    const packFilterRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes("/pack-runs/?") &&
        request.url().includes(`pack_id=${PACK_A_ID}`)
    );
    await page.getByLabel("Pack").selectOption(PACK_A_ID);
    await packFilterRequest;

    await expect(runsTable.getByText("Pack Alpha")).toBeVisible();
    await expect(runsTable.getByText("Pack Beta")).toHaveCount(0);

    const stateFilterRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes("/pack-runs/?") &&
        request.url().includes(`pack_id=${PACK_A_ID}`) &&
        request.url().includes("state=failed")
    );
    await page.getByLabel("State").selectOption("failed");
    await stateFilterRequest;

    await expect(page.getByText("No pack runs found.")).toBeVisible();

    const clearPackRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes("/pack-runs/?") &&
        !request.url().includes("pack_id=") &&
        request.url().includes("state=failed")
    );
    await page.getByLabel("Pack").selectOption("");
    await clearPackRequest;

    await expect(runsTable.getByText("Pack Beta")).toBeVisible();
    await expect(runsTable.getByText("Pack Alpha")).toHaveCount(0);

    expect(capture.seenQueries.length).toBeGreaterThanOrEqual(4);
  });
});
