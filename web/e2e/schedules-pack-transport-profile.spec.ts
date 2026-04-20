import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_ID = "pack_smoke";
const DESTINATION_ID = "dest_carrier_a";

interface ScheduleState {
  schedules: Array<Record<string, unknown>>;
  createPayload: Record<string, unknown> | null;
}

function makeCreatedSchedule(payload: Record<string, unknown>): Record<string, unknown> {
  return {
    schedule_id: "sched_pack_1",
    name: payload.name ?? null,
    target_type: "pack",
    scenario_id: null,
    pack_id: payload.pack_id ?? PACK_ID,
    cron_expr: payload.cron_expr ?? "0 9 * * *",
    timezone: payload.timezone ?? "UTC",
    active: true,
    misfire_policy: payload.misfire_policy ?? "skip",
    config_overrides: payload.config_overrides ?? null,
    last_run_at: null,
    next_run_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    last_status: null,
  };
}

async function mockSchedulesApi(page: Page, state: ScheduleState): Promise<void> {
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
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tts_cache_enabled: true,
          destinations_enabled: true,
        }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "scenario_smoke",
            name: "Scenario Smoke",
            type: "reliability",
            turns: 2,
            version_hash: "v1",
            cache_status: "cold",
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
            name: "Pack Smoke",
            description: "Pack regression",
            execution_mode: "parallel",
            scenario_count: 2,
            tags: ["smoke"],
          },
        ]),
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
            name: "Carrier A",
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

    if (pathname === "/schedules/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.schedules),
      });
    }

    if (pathname === "/schedules/preview" && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          timezone: "UTC",
          occurrences: [new Date(Date.now() + 60 * 60 * 1000).toISOString()],
        }),
      });
    }

    if (pathname === "/schedules/" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.createPayload = payload;
      state.schedules = [makeCreatedSchedule(payload)];
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(state.schedules[0]),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Schedules pack transport profile override", () => {
  test("creates a pack schedule with transport profile override and renders attribution", async ({
    page,
  }) => {
    const state: ScheduleState = {
      schedules: [],
      createPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state);

    await page.goto("/schedules");
    await expect(page.getByRole("heading", { name: "Schedules" })).toBeVisible();

    await page.getByRole("button", { name: "New Schedule" }).click();
    await expect(page.getByRole("heading", { name: "New Schedule" })).toBeVisible();
    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "New Schedule" }) });

    await modal.getByTestId("create-schedule-target-type").selectOption("pack");
    const packSelect = modal.getByTestId("create-schedule-target-id");
    await expect(packSelect.locator(`option[value=\"${PACK_ID}\"]`)).toHaveCount(1);
    await packSelect.selectOption(PACK_ID);

    const destinationSelect = modal.getByTestId("create-schedule-destination-id");
    await expect(destinationSelect.locator(`option[value=\"${DESTINATION_ID}\"]`)).toHaveCount(1);
    await destinationSelect.selectOption(DESTINATION_ID);
    await modal.getByTestId("create-schedule-name").fill("Morning pack smoke");

    const createRequest = page.waitForRequest(
      (request) => request.method() === "POST" && request.url().includes("/schedules/")
    );

    const createButton = modal.getByRole("button", { name: "Create Schedule" });
    await expect(createButton).toBeEnabled();
    await createButton.click();
    await createRequest;

    expect(state.createPayload).not.toBeNull();
    expect(state.createPayload).toMatchObject({
      target_type: "pack",
      name: "Morning pack smoke",
      pack_id: PACK_ID,
      scenario_id: null,
      config_overrides: {
        transport_profile_id: DESTINATION_ID,
      },
    });

    const scheduleCard = page.getByTestId("schedule-card-sched_pack_1");
    await expect(scheduleCard).toContainText("Morning pack smoke");
    await expect(scheduleCard).toContainText(`pack:${PACK_ID}`);
    await expect(scheduleCard).toContainText(`transport: Carrier A (${DESTINATION_ID})`);
  });
});
