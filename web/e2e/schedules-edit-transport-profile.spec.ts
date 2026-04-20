import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const PACK_ID = "pack_smoke";
const DEST_A = "dest_carrier_a";
const DEST_B = "dest_carrier_b";

interface ScheduleState {
  schedules: Array<Record<string, unknown>>;
  lastPatchPayload: Record<string, unknown> | null;
}

function scheduleWithDestination(destinationId: string): Record<string, unknown> {
  return {
    schedule_id: "sched_pack_edit_1",
    target_type: "pack",
    scenario_id: null,
    pack_id: PACK_ID,
    cron_expr: "0 9 * * *",
    timezone: "UTC",
    active: true,
    misfire_policy: "skip",
    config_overrides: {
      transport_profile_id: destinationId,
      retention_profile: "strict",
    },
    last_run_at: null,
    next_run_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    last_status: "dispatched",
  };
}

function destinationFixtures(): Array<Record<string, unknown>> {
  const now = new Date().toISOString();
  return [
    {
      destination_id: DEST_A,
      transport_profile_id: DEST_A,
      name: "Carrier A",
      protocol: "sip",
      endpoint: "sip:carrier-a@example.com",
      default_dial_target: "sip:carrier-a@example.com",
      is_active: true,
      capacity_scope: "carrier-a",
      effective_channels: 5,
      created_at: now,
      updated_at: now,
    },
    {
      destination_id: DEST_B,
      transport_profile_id: DEST_B,
      name: "Carrier B",
      protocol: "sip",
      endpoint: "sip:carrier-b@example.com",
      default_dial_target: "sip:carrier-b@example.com",
      is_active: true,
      capacity_scope: "carrier-b",
      effective_channels: 7,
      created_at: now,
      updated_at: now,
    },
  ];
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
        body: JSON.stringify([]),
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
        body: JSON.stringify(destinationFixtures()),
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

    if (pathname === "/schedules/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.schedules),
      });
    }

    if (pathname === "/schedules/sched_pack_edit_1" && method === "PATCH") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.lastPatchPayload = payload;
      state.schedules = [
        {
          ...state.schedules[0],
          ...payload,
          config_overrides:
            payload.config_overrides !== undefined
              ? payload.config_overrides
              : state.schedules[0].config_overrides,
        },
      ];
      return route.fulfill({
        status: 200,
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

test.describe("@smoke Schedules edit destination override", () => {
  test("changing destination preserves non-destination overrides", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [scheduleWithDestination(DEST_A)],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state);

    await page.goto("/schedules");
    await expect(page.getByRole("heading", { name: "Schedules" })).toBeVisible();
    await expect(page.getByText(`transport: Carrier A (${DEST_A})`)).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();
    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "Edit Schedule" }) });

    const destinationSelect = modal.getByTestId("edit-schedule-destination-id");
    await expect(destinationSelect.locator(`option[value="${DEST_B}"]`)).toHaveCount(1);
    await destinationSelect.selectOption(DEST_B);

    const patchRequest = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        request.url().includes("/schedules/sched_pack_edit_1")
    );
    await modal.getByRole("button", { name: "Save Changes" }).click();
    await patchRequest;

    expect(state.lastPatchPayload).toMatchObject({
      target_type: "pack",
      pack_id: PACK_ID,
      config_overrides: {
        transport_profile_id: DEST_B,
        retention_profile: "strict",
      },
    });

    await expect(page.getByRole("heading", { name: "Edit Schedule" })).toHaveCount(0);
    await expect(page.getByText(`transport: Carrier B (${DEST_B})`)).toBeVisible();
  });

  test("clearing transport profile removes transport_profile_id but keeps other overrides", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [scheduleWithDestination(DEST_A)],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state);

    await page.goto("/schedules");
    await expect(page.getByText(`transport: Carrier A (${DEST_A})`)).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();
    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "Edit Schedule" }) });

    const destinationSelect = modal.getByTestId("edit-schedule-destination-id");
    await destinationSelect.selectOption("");

    const patchRequest = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        request.url().includes("/schedules/sched_pack_edit_1")
    );
    await modal.getByRole("button", { name: "Save Changes" }).click();
    await patchRequest;

    expect(state.lastPatchPayload).toMatchObject({
      target_type: "pack",
      pack_id: PACK_ID,
      config_overrides: {
        retention_profile: "strict",
      },
    });
    expect(
      (state.lastPatchPayload?.config_overrides as Record<string, unknown>).transport_profile_id
    ).toBe(undefined);

    await expect(page.getByRole("heading", { name: "Edit Schedule" })).toHaveCount(0);
    await expect(page.getByText(`transport: Carrier A (${DEST_A})`)).toHaveCount(0);
  });
});
