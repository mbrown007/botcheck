import { expect, test, type Page } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

interface DestinationState {
  destinations: Array<Record<string, unknown>>;
  createBodies: Array<Record<string, unknown>>;
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

    if (pathname === "/destinations/trunks" && method === "GET") {
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
        body: JSON.stringify(state.destinations),
      });
    }

    if (pathname === "/destinations/" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.createBodies.push(body);
      state.destinations = [
        {
          destination_id: "dest_http_1",
          transport_profile_id: "dest_http_1",
          name: String(body.name ?? "Direct HTTP"),
          protocol: "http",
          endpoint: String(body.default_dial_target ?? ""),
          default_dial_target: String(body.default_dial_target ?? ""),
          direct_http_config: body.direct_http_config ?? {},
          is_active: true,
          active_schedule_count: 0,
          active_pack_run_count: 0,
          in_use: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ];
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(state.destinations[0]),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Settings HTTP transport profiles", () => {
  test("creates a direct HTTP transport profile with request/response mapping", async ({ page }) => {
    const state: DestinationState = {
      destinations: [],
      createBodies: [],
    };

    await installAuthSession(page, { role: "editor" });
    await mockSettingsApi(page, state);
    await page.goto("/settings");

    const transportCard = page.locator("section,div").filter({ hasText: "Transport Profiles" }).first();

    await transportCard.getByRole("textbox", { name: "Name" }).fill("Direct Bot API");
    await transportCard.getByRole("combobox", { name: "Protocol" }).selectOption("http");
    await transportCard.getByRole("textbox", { name: "Endpoint URL" }).fill("https://bot.internal/chat");
    await transportCard.getByRole("textbox", { name: "Request Text Field" }).fill("prompt");
    await transportCard.getByRole("textbox", { name: "Response Text Field" }).fill("data.text");
    await transportCard.getByRole("textbox", { name: "Timeout (s)" }).fill("12");
    await transportCard.getByRole("textbox", { name: "Max Retries" }).fill("2");

    await transportCard.getByRole("button", { name: "Create Transport Profile" }).click();

    await expect(page.getByText("Transport profile created.")).toBeVisible();
    await expect(page.getByText("HTTP · https://bot.internal/chat")).toBeVisible();
    await expect(page.getByText("Request field: prompt · Response field: data.text")).toBeVisible();

    expect(state.createBodies).toHaveLength(1);
    expect(state.createBodies[0]).toMatchObject({
      name: "Direct Bot API",
      protocol: "http",
      default_dial_target: "https://bot.internal/chat",
      direct_http_config: {
        request_text_field: "prompt",
        response_text_field: "data.text",
        timeout_s: 12,
        max_retries: 2,
      },
    });
  });
});
