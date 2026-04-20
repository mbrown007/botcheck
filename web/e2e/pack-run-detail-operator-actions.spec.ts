import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_RUN_ID = "packrun_detail_ops";

interface MockState {
  state: string;
  gateOutcome: string;
  markFailedBody: Record<string, unknown> | null;
}

function buildPackRunDetail(state: MockState): Record<string, unknown> {
  const now = new Date().toISOString();
  return {
    pack_run_id: PACK_RUN_ID,
    pack_id: "pack_detail_ops",
    pack_name: "Detail Ops Pack",
    state: state.state,
    gate_outcome: state.gateOutcome,
    trigger_source: "manual",
    schedule_id: null,
    triggered_by: "qa_engineer",
    total_scenarios: 2,
    dispatched: 2,
    completed: state.state === "running" ? 1 : 2,
    passed: state.state === "failed" ? 1 : 1,
    blocked: state.state === "failed" ? 1 : 0,
    failed: state.state === "failed" ? 1 : 0,
    destination_id: null,
    dimension_heatmap: {},
    previous_dimension_heatmap: {},
    previous_pack_run_id: null,
    cost_pence: null,
    created_at: now,
    updated_at: now,
  };
}

function buildChildrenResponse(): Record<string, unknown> {
  return {
    pack_run_id: PACK_RUN_ID,
    total: 1,
    items: [
      {
        pack_run_item_id: "pritem_detail_1",
        scenario_id: "scenario_detail",
        scenario_version_hash: "v1",
        order_index: 0,
        state: "dispatched",
        run_state: "running",
        gate_result: "pending",
        run_id: "run_detail_1",
        duration_s: 4.2,
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

async function mockPackRunDetailApi(page: Page, state: MockState): Promise<void> {
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
        body: JSON.stringify(buildPackRunDetail(state)),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/runs` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(buildChildrenResponse()),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/cancel` && method === "POST") {
      state.state = "cancelled";
      state.gateOutcome = "cancelled";
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          pack_run_id: PACK_RUN_ID,
          applied: true,
          state: "cancelled",
          reason: "cancelled",
        }),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/mark-failed` && method === "POST") {
      state.markFailedBody = (request.postDataJSON() as Record<string, unknown>) ?? {};
      state.state = "failed";
      state.gateOutcome = "blocked";
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          pack_run_id: PACK_RUN_ID,
          applied: true,
          state: "failed",
          reason: "mark_failed",
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

test.describe("@smoke Pack run detail operator actions", () => {
  test("cancel run action updates detail state", async ({ page }) => {
    const state: MockState = {
      state: "running",
      gateOutcome: "pending",
      markFailedBody: null,
    };

    await installAuthSession(page, { role: "operator" });
    await mockPackRunDetailApi(page, state);

    await page.goto(`/pack-runs/${PACK_RUN_ID}`);
    await expect(page.getByRole("heading", { name: "Detail Ops Pack" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel Run" })).toBeVisible();

    const cancelRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/cancel`)
    );
    await page.getByRole("button", { name: "Cancel Run" }).click();
    await cancelRequest;

    await expect(page.getByRole("button", { name: "Cancel Run" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark Failed" })).toHaveCount(0);
    await expect(page.locator("main")).toContainText("cancelled");
  });

  test("mark failed action sends reason and updates detail state", async ({ page }) => {
    const state: MockState = {
      state: "running",
      gateOutcome: "pending",
      markFailedBody: null,
    };

    await installAuthSession(page, { role: "operator" });
    await mockPackRunDetailApi(page, state);

    await page.goto(`/pack-runs/${PACK_RUN_ID}`);
    await expect(page.getByRole("button", { name: "Mark Failed" })).toBeVisible();

    page.once("dialog", (dialog) => dialog.accept());

    const markRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/mark-failed`)
    );
    await page.getByRole("button", { name: "Mark Failed" }).click();
    await markRequest;

    expect(state.markFailedBody).toEqual({
      reason: "Marked failed by operator from pack run detail",
    });

    await expect(page.getByRole("button", { name: "Cancel Run" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark Failed" })).toHaveCount(0);
    await expect(page.locator("main")).toContainText("failed");
  });
});
