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

async function mockAdminApi(page: Page, role: MockAppRole): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname, search } = url;
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

    if (pathname === "/admin/users/" && method === "GET") {
      return ok(route, {
        total: 1,
        items: [
          {
            user_id: "user_1",
            email: "user@example.com",
            tenant_id: "default-tenant",
            role: "viewer",
            is_active: true,
            totp_enabled: false,
            active_session_count: 2,
            last_login_at: "2026-03-11T12:00:00Z",
            locked_until: null,
          },
        ],
      });
    }

    if (pathname === "/admin/system/health" && method === "GET") {
      return ok(route, {
        database: { status: "ok" },
        redis: { status: "ok" },
        livekit: { status: "configured" },
        providers: {
          deepgram: { configured: false, key_location: "agent" },
          openai: { configured: true, key_location: "api" },
        },
      });
    }

    if (pathname === "/admin/system/config" && method === "GET") {
      return ok(route, {
        config: {
          feature_tts_provider_openai_enabled: true,
          feature_stt_provider_azure_enabled: true,
        },
      });
    }

    if (pathname === "/admin/system/quotas" && method === "GET") {
      return ok(route, {
        quota_defaults: {
          max_concurrent_runs: 5,
          max_runs_per_day: 500,
          max_schedules: 50,
        },
      });
    }

    if (pathname === "/admin/system/quotas" && method === "PATCH") {
      const body = request.postDataJSON() as Record<string, unknown>;
      return ok(route, body);
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname}${search} not mocked` }),
    });
  });
}

test.describe("@smoke admin web surfaces", () => {
  test("tenant admin can load user admin", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockAdminApi(page, "admin");

    await page.goto("/admin/users");

    await expect(page.getByRole("heading", { name: "User Admin" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Create User" })).toBeVisible();
    await expect(page.getByText("user@example.com")).toBeVisible();
    await expect(page.getByRole("button", { name: "Lock" })).toBeVisible();
  });

  test("viewer is blocked from user admin", async ({ page }) => {
    await installAuthSession(page, { role: "viewer" });
    await mockAdminApi(page, "viewer");

    await page.goto("/admin/users");

    await expect(page.getByText("User administration is restricted to admin role or above.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Back to dashboard" })).toBeVisible();
  });

  test("platform admin can load system admin", async ({ page }) => {
    await installAuthSession(page, { role: "system_admin" });
    await mockAdminApi(page, "system_admin");

    await page.goto("/admin/system");

    await expect(page.getByRole("heading", { name: "System Admin" })).toBeVisible();
    await expect(page.getByText("Platform Quota Defaults")).toBeVisible();
    await expect(page.getByText("Effective Config")).toBeVisible();
    await expect(page.getByText("deepgram")).toBeVisible();
    await expect(page.getByText("via agent")).toBeVisible();
  });
});
