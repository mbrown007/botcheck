import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";

interface DestinationState {
  destinations: Array<Record<string, unknown>>;
  deleteCalls: string[];
  pools: Array<Record<string, unknown>>;
}

function makeDestination(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    destination_id: "dest_default",
    transport_profile_id: "dest_default",
    name: "Destination Default",
    protocol: "sip",
    endpoint: "sip:default@example.com",
    default_dial_target: "sip:default@example.com",
    is_active: true,
    capacity_scope: "carrier-default",
    effective_channels: 5,
    active_schedule_count: 0,
    active_pack_run_count: 0,
    in_use: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

async function mockSettingsApi(page: Page, state: DestinationState): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (
      await maybeMockIdentityRoute(route, { pathname, method }, {
        role: "editor",
        tenantResponse: { default_retention_profile: "standard" },
      })
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

    if (pathname === "/destinations/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.destinations),
      });
    }

    if (pathname === "/sip/pools" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: state.pools,
          total: state.pools.length,
        }),
      });
    }

    if (pathname.startsWith("/destinations/") && method === "DELETE") {
      const destinationId = pathname.split("/")[2] ?? "";
      state.deleteCalls.push(destinationId);
      state.destinations = state.destinations.filter(
        (row) => String(row.destination_id ?? "") !== destinationId
      );
      return route.fulfill({ status: 204 });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Settings destination usage indicators", () => {
  test("shows in-use counts and disables delete for protected destinations", async ({ page }) => {
    const state: DestinationState = {
      destinations: [
        makeDestination({
          destination_id: "dest_in_use",
          name: "Carrier In Use",
          trunk_pool_id: "pool_default",
          active_schedule_count: 2,
          active_pack_run_count: 1,
          in_use: true,
        }),
        makeDestination({
          destination_id: "dest_free",
          name: "Carrier Free",
          trunk_pool_id: "pool_default",
          active_schedule_count: 0,
          active_pack_run_count: 0,
          in_use: false,
        }),
      ],
      deleteCalls: [],
      pools: [
        {
          trunk_pool_id: "pool_default",
          pool_name: "Default Pool",
          provider_name: "Twilio",
          tenant_label: "Default Tenant Pool",
          is_default: true,
          is_active: true,
          member_count: 1,
        },
      ],
    };

    await installAuthSession(page, { role: "editor" });
    await mockSettingsApi(page, state);
    await page.goto("/settings");

    const inUseRow = page
      .locator("div.rounded-md.border.border-border.bg-bg-elevated.px-3.py-2")
      .filter({ hasText: "Carrier In Use" });
    await expect(inUseRow).toContainText("In use · Active schedules: 2 · Active pack runs: 1");
    await expect(inUseRow.getByRole("button", { name: "Delete" })).toBeDisabled();

    const freeRow = page
      .locator("div.rounded-md.border.border-border.bg-bg-elevated.px-3.py-2")
      .filter({ hasText: "Carrier Free" });
    await expect(freeRow.getByRole("button", { name: "Delete" })).toBeEnabled();
  });

  test("allows deleting unused destination and refreshes list", async ({ page }) => {
    const state: DestinationState = {
      destinations: [
        makeDestination({
          destination_id: "dest_delete_me",
          name: "Carrier Delete Me",
          trunk_pool_id: "pool_default",
          in_use: false,
        }),
      ],
      deleteCalls: [],
      pools: [
        {
          trunk_pool_id: "pool_default",
          pool_name: "Default Pool",
          provider_name: "Twilio",
          tenant_label: "Default Tenant Pool",
          is_default: true,
          is_active: true,
          member_count: 1,
        },
      ],
    };

    await installAuthSession(page, { role: "editor" });
    await mockSettingsApi(page, state);
    await page.goto("/settings");

    const row = page
      .locator("div.rounded-md.border.border-border.bg-bg-elevated.px-3.py-2")
      .filter({ hasText: "Carrier Delete Me" });
    await expect(row).toBeVisible();

    page.once("dialog", (dialog) => dialog.accept());
    await row.getByRole("button", { name: "Delete" }).click();

    await expect(page.getByText("Transport profile deleted.")).toBeVisible();
    await expect(page.getByText("Carrier Delete Me")).toHaveCount(0);
    expect(state.deleteCalls).toEqual(["dest_delete_me"]);
  });
});
