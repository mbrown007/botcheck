import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_ID = "pack_ops_smoke";
const PACK_RUN_ID = "packrun_ops_smoke_1";

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

interface MockState {
  run: MockRunSummary;
  markFailedBody: Record<string, unknown> | null;
}

function createRunningSummary(): MockRunSummary {
  const now = new Date().toISOString();
  return {
    pack_run_id: PACK_RUN_ID,
    pack_id: PACK_ID,
    state: "running",
    gate_outcome: "pending",
    total_scenarios: 3,
    dispatched: 3,
    completed: 1,
    passed: 1,
    blocked: 0,
    failed: 0,
    trigger_source: "manual",
    triggered_by: "qa_engineer",
    schedule_id: null,
    destination_id: null,
    created_at: now,
    updated_at: now,
  };
}

async function mockPackRunsApi(page: Page, state: MockState): Promise<void> {
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

    if (pathname === "/packs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            pack_id: PACK_ID,
            name: "Ops Pack",
            description: "Pack operations",
            execution_mode: "parallel",
            scenario_count: 3,
            tags: ["ops"],
          },
        ]),
      });
    }

    if (pathname === "/pack-runs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([state.run]),
      });
    }

    if (pathname === `/pack-runs/${PACK_RUN_ID}/cancel` && method === "POST") {
      state.run = {
        ...state.run,
        state: "cancelled",
        gate_outcome: "cancelled",
        updated_at: new Date().toISOString(),
      };
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
      state.run = {
        ...state.run,
        state: "failed",
        gate_outcome: "blocked",
        failed: 1,
        completed: state.run.total_scenarios,
        updated_at: new Date().toISOString(),
      };
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

test.describe("@smoke Pack runs operator actions", () => {
  test("cancel transitions running pack run to cancelled", async ({ page }) => {
    const state: MockState = {
      run: createRunningSummary(),
      markFailedBody: null,
    };

    await installAuthSession(page, { role: "operator" });
    await mockPackRunsApi(page, state);

    await page.goto("/pack-runs");
    await expect(page.getByRole("heading", { name: "Pack Runs" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();

    page.once("dialog", (dialog) => dialog.accept());

    const cancelRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/cancel`)
    );
    await page.getByRole("button", { name: "Cancel" }).click();
    await cancelRequest;

    const runRow = page.locator("tr", { hasText: PACK_ID }).first();
    await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark Failed" })).toHaveCount(0);
    await expect(runRow).toContainText("cancelled");
  });

  test("mark failed sends operator reason payload and updates state", async ({ page }) => {
    const state: MockState = {
      run: createRunningSummary(),
      markFailedBody: null,
    };

    await installAuthSession(page, { role: "operator" });
    await mockPackRunsApi(page, state);

    await page.goto("/pack-runs");
    await expect(page.getByRole("button", { name: "Mark Failed" })).toBeVisible();

    page.once("dialog", (dialog) => dialog.accept());

    const markFailedRequest = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().includes(`/pack-runs/${PACK_RUN_ID}/mark-failed`)
    );

    await page.getByRole("button", { name: "Mark Failed" }).click();
    await markFailedRequest;

    expect(state.markFailedBody).toEqual({
      reason: "Marked failed by operator from pack run list",
    });

    const runRow = page.locator("tr", { hasText: PACK_ID }).first();
    await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark Failed" })).toHaveCount(0);
    await expect(runRow).toContainText("failed");
  });
});
