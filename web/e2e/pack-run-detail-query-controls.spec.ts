import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_RUN_ID = "packrun_query_controls";

interface QueryCapture {
  seenQueries: string[];
}

function detailResponse(): Record<string, unknown> {
  const now = new Date().toISOString();
  return {
    pack_run_id: PACK_RUN_ID,
    pack_id: "pack_query",
    pack_name: "Query Controls Pack",
    state: "running",
    gate_outcome: "pending",
    trigger_source: "manual",
    schedule_id: null,
    triggered_by: "qa_engineer",
    total_scenarios: 120,
    dispatched: 120,
    completed: 60,
    passed: 58,
    blocked: 1,
    failed: 1,
    destination_id: null,
    dimension_heatmap: {},
    previous_dimension_heatmap: {},
    previous_pack_run_id: null,
    cost_pence: null,
    created_at: now,
    updated_at: now,
  };
}

function childrenResponse(): Record<string, unknown> {
  return {
    pack_run_id: PACK_RUN_ID,
    total: 120,
    items: [
      {
        pack_run_item_id: "pritem_query_1",
        scenario_id: "scenario_query_1",
        scenario_version_hash: "v1",
        order_index: 0,
        state: "dispatched",
        run_state: "running",
        gate_result: "pending",
        run_id: "run_query_1",
        duration_s: 5.5,
        cost_pence: null,
        summary: "In progress",
        error_code: null,
        error_detail: null,
        overall_status: null,
        created_at: new Date().toISOString(),
      },
    ],
  };
}

async function mockPackRunApi(page: Page, capture: QueryCapture): Promise<void> {
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
          packs_enabled: true,
          destinations_enabled: false,
        }),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(detailResponse()),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/runs` && method === "GET") {
      capture.seenQueries.push(url.search);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(childrenResponse()),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("Pack run detail query controls", () => {
  test("updates sort and pagination params for child run fetches", async ({ page }) => {
    const capture: QueryCapture = { seenQueries: [] };

    await installAuthSession(page, { role: "operator" });
    await mockPackRunApi(page, capture);

    await page.goto(`/pack-runs/${PACK_RUN_ID}`);
    await expect(page.getByRole("heading", { name: "Query Controls Pack" })).toBeVisible();

    await expect
      .poll(() => capture.seenQueries.some((q) => q.includes("sort_by=failures_first")))
      .toBeTruthy();

    const stateSortRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/runs`) &&
        request.url().includes("sort_by=state") &&
        request.url().includes("offset=0")
    );
    await page.getByLabel("Sort").selectOption("state");
    await stateSortRequest;

    const descRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/runs`) &&
        request.url().includes("sort_by=state") &&
        request.url().includes("sort_dir=desc")
    );
    await page.getByLabel("Direction").selectOption("desc");
    await descRequest;

    const nextPageRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/runs`) &&
        request.url().includes("offset=50") &&
        request.url().includes("limit=50")
    );
    await page.getByRole("button", { name: /^Next$/ }).click();
    await nextPageRequest;
  });
});
