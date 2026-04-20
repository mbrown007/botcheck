import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_ID = "pack_smoke";
const PACK_RUN_ID = "packrun_smoke_1";
const DESTINATION_ID = "dest_carrier_a";
const DESTINATION_NAME = "Carrier A";

interface PacksMockState {
  packRuns: Array<Record<string, unknown>>;
}

function buildPackRunSummary(transportProfileId?: string, dialTarget?: string): Record<string, unknown> {
  const now = new Date().toISOString();
  return {
    pack_run_id: PACK_RUN_ID,
    pack_id: PACK_ID,
    state: "pending",
    gate_outcome: "pending",
    total_scenarios: 2,
    dispatched: 0,
    completed: 0,
    passed: 0,
    blocked: 0,
    failed: 0,
    trigger_source: "manual",
    triggered_by: "qa_engineer",
    schedule_id: null,
    destination_id: transportProfileId ?? null,
    transport_profile_id: transportProfileId ?? null,
    dial_target: dialTarget ?? null,
    created_at: now,
    updated_at: now,
  };
}

async function mockPacksApi(page: Page, state: PacksMockState): Promise<void> {
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
          destinations_enabled: true,
        }),
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
            protocol: "sip",
            endpoint: "sip:carrier-a@example.com",
            default_dial_target: "sip:carrier-a@example.com",
            is_active: true,
            capacity_scope: "carrier-a",
            effective_channels: 5,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]),
      });
    }

    if (pathname === "/packs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            pack_id: PACK_ID,
            name: "Smoke Pack",
            description: "SIP smoke scenarios",
            execution_mode: "parallel",
            scenario_count: 2,
            tags: ["smoke"],
          },
        ]),
      });
    }

    if (pathname === "/pack-runs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.packRuns),
      });
    }

    if (pathname === `/packs/${PACK_ID}/run` && method === "POST") {
      const body = request.postDataJSON() as {
        transport_profile_id?: string;
        dial_target?: string;
      };
      state.packRuns = [buildPackRunSummary(body.transport_profile_id, body.dial_target)];
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          pack_run_id: PACK_RUN_ID,
          state: "pending",
          total_scenarios: 2,
          destination_id: body.transport_profile_id ?? null,
          transport_profile_id: body.transport_profile_id ?? null,
          dial_target: body.dial_target ?? null,
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

test.describe("@smoke Pack Run transport profile override", () => {
  test("sends selected transport_profile_id and renders transport attribution", async ({ page }) => {
    const state: PacksMockState = {
      packRuns: [],
    };

    await installAuthSession(page, { role: "admin" });
    await mockPacksApi(page, state);

    await page.goto("/packs");
    await expect(page.getByRole("heading", { name: "Packs" })).toBeVisible();

    await page
      .getByLabel("Transport Profile (optional)")
      .selectOption(DESTINATION_ID);

    const runRequestPromise = page.waitForRequest(
      (request) =>
        request.method() === "POST" && request.url().includes(`/packs/${PACK_ID}/run`)
    );

    await page.getByRole("button", { name: "Run Now" }).click();

    const runRequest = await runRequestPromise;
    expect(runRequest.postDataJSON()).toEqual({ transport_profile_id: DESTINATION_ID });

    await expect(
      page.getByText(`transport: ${DESTINATION_NAME} (${DESTINATION_ID})`)
    ).toBeVisible();
  });
});
