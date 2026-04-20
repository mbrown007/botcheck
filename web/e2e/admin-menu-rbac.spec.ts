import { expect, test, type Page, type Route } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute, type MockAppRole } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockShellApi(page: Page, role: MockAppRole): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return ok(route, {
        tts_cache_enabled: true,
        ai_scenarios_enabled: true,
        packs_enabled: true,
        destinations_enabled: true,
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return ok(route, []);
    }

    if (pathname === "/admin/users/" && method === "GET") {
      return ok(route, { total: 0, items: [] });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke account menu RBAC", () => {
  test("viewer sees only user settings and logout", async ({ page }) => {
    await installAuthSession(page, { role: "viewer" });
    await mockShellApi(page, "viewer");

    await page.goto("/scenarios");
    await page.getByRole("button", { name: "Open account menu" }).click();

    await expect(page.getByText("User Settings")).toBeVisible();
    await expect(page.getByText("General Settings")).toHaveCount(0);
    await expect(page.getByText("Admin")).toHaveCount(0);
    await expect(page.getByText("Administration")).toHaveCount(0);
  });

  test("tenant admin sees admin menu entries and can navigate to settings", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockShellApi(page, "admin");

    await page.goto("/scenarios");
    await page.getByRole("button", { name: "Open account menu" }).click();

    await expect(page.getByText("Administration", { exact: true })).toBeVisible();
    await expect(page.getByText("General Settings", { exact: true })).toBeVisible();
    await expect(page.getByText("Admin", { exact: true })).toBeVisible();

    await page.getByText("General Settings", { exact: true }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  });

  test("platform admin can open admin overview from the account menu", async ({ page }) => {
    await installAuthSession(page, { role: "system_admin" });
    await mockShellApi(page, "system_admin");

    await page.goto("/scenarios");
    await page.getByRole("button", { name: "Open account menu" }).click();
    await page.getByText("Admin", { exact: true }).click();

    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { name: "Admin", exact: true })).toBeVisible();
    await expect(page.getByText("User Admin", { exact: true })).toBeVisible();
    await expect(page.getByText("Tenant Admin", { exact: true })).toBeVisible();
    await expect(page.getByText("System Admin", { exact: true })).toBeVisible();
    await expect(page.getByText("SIP Admin", { exact: true })).toBeVisible();
  });
});
