import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_RUN_ID = "packrun_filter_smoke";

function packRunDetailResponse(): Record<string, unknown> {
  const now = new Date().toISOString();
  return {
    pack_run_id: PACK_RUN_ID,
    pack_id: "pack_filter_smoke",
    pack_name: "Filter Pack",
    state: "running",
    gate_outcome: "pending",
    trigger_source: "manual",
    schedule_id: null,
    triggered_by: "qa_engineer",
    total_scenarios: 2,
    dispatched: 2,
    completed: 1,
    passed: 1,
    blocked: 0,
    failed: 0,
    destination_id: null,
    dimension_heatmap: {},
    previous_dimension_heatmap: {},
    previous_pack_run_id: null,
    cost_pence: null,
    created_at: now,
    updated_at: now,
  };
}

function childrenResponse(failuresOnly: boolean): Record<string, unknown> {
  const shared = {
    scenario_version_hash: "v1",
    overall_status: null,
    created_at: new Date().toISOString(),
    cost_pence: null,
  };
  const passing = {
    ...shared,
    pack_run_item_id: "pritem_pass",
    scenario_id: "scenario_pass",
    order_index: 0,
    state: "complete",
    run_state: "complete",
    gate_result: "passed",
    run_id: "run_pass",
    duration_s: 9.2,
    summary: "Scenario passed",
    error_code: null,
    error_detail: null,
  };
  const failing = {
    ...shared,
    pack_run_item_id: "pritem_fail",
    scenario_id: "scenario_fail",
    order_index: 1,
    state: "failed",
    run_state: "failed",
    gate_result: "blocked",
    run_id: null,
    duration_s: null,
    summary: null,
    error_code: "scenario_version_mismatch",
    error_detail: "Scenario changed after snapshot",
  };
  const items = failuresOnly ? [failing] : [passing, failing];
  return {
    pack_run_id: PACK_RUN_ID,
    total: items.length,
    items,
  };
}

async function mockPackRunApi(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname, searchParams } = url;
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
        body: JSON.stringify(packRunDetailResponse()),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/runs` && method === "GET") {
      const failuresOnly = searchParams.get("failures_only") === "true";
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(childrenResponse(failuresOnly)),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Pack run failures-only toggle", () => {
  test("requests failures_only=true and filters child runs", async ({ page }) => {
    await installAuthSession(page, { role: "operator" });
    await mockPackRunApi(page);

    await page.goto(`/pack-runs/${PACK_RUN_ID}`);
    await expect(page.getByRole("heading", { name: "Filter Pack" })).toBeVisible();

    await expect(page.getByText("scenario_pass")).toBeVisible();
    await expect(page.getByText("scenario_fail")).toBeVisible();

    const failuresOnlyRequest = page.waitForRequest(
      (request) =>
        request.method() === "GET" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/runs`) &&
        request.url().includes("failures_only=true")
    );

    await page.getByRole("button", { name: "Failures Only" }).click();
    await failuresOnlyRequest;

    await expect(page.getByText("scenario_fail")).toBeVisible();
    await expect(page.getByText("scenario_pass")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Show All" })).toBeVisible();
  });
});
