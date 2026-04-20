import { expect, test, type Page, type Route } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

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

async function mockAdminSipApi(page: Page): Promise<void> {
  const trunks = [
    {
      trunk_id: "trunk-uk-1",
      name: "Twilio UK",
      provider_name: "Twilio",
      address: "sip:uk.twilio.example.com",
      is_active: true,
      numbers: ["+442079460000"],
      last_synced_at: "2026-03-14T08:00:00Z",
    },
    {
      trunk_id: "trunk-uk-2",
      name: "Twilio UK Backup",
      provider_name: "Twilio",
      address: "sip:uk2.twilio.example.com",
      is_active: true,
      numbers: ["+442079460001"],
      last_synced_at: "2026-03-14T08:00:00Z",
    },
    {
      trunk_id: "trunk-us-1",
      name: "Twilio US",
      provider_name: "Twilio",
      address: "sip:us.twilio.example.com",
      is_active: true,
      numbers: ["+12125550100"],
      last_synced_at: "2026-03-14T08:00:00Z",
    },
  ];

  let pools = [
    {
      trunk_pool_id: "pool-uk-primary",
      name: "UK Outbound",
      provider_name: "Twilio",
      selection_policy: "first_available",
      is_active: true,
      members: [
        {
          trunk_id: "trunk-uk-1",
          name: "Twilio UK",
          provider_name: "Twilio",
          priority: 100,
        },
      ],
      assignments: [
        {
          tenant_id: "tenant-acme",
          tenant_label: "Acme UK",
          is_default: false,
          is_active: true,
          max_channels: 24 as number | null,
          reserved_channels: 6 as number | null,
        },
      ],
    },
  ];

  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "system_admin" })) {
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

    if (pathname === "/admin/sip/trunks" && method === "GET") {
      return ok(route, { total: trunks.length, items: trunks });
    }

    if (pathname === "/admin/sip/pools" && method === "GET") {
      return ok(route, { total: pools.length, items: pools });
    }

    if (pathname === "/admin/tenants/" && method === "GET") {
      return ok(route, {
        total: 1,
        items: [{ tenant_id: "tenant-acme", display_name: "Acme" }],
      });
    }

    if (pathname === "/admin/sip/pools" && method === "POST") {
      const body = request.postDataJSON() as { name: string; provider_name: string };
      const created = {
        trunk_pool_id: "pool-us-backup",
        name: body.name,
        provider_name: body.provider_name,
        selection_policy: "first_available",
        is_active: true,
        members: [],
        assignments: [],
      };
      pools = [...pools, created];
      return ok(route, created, 201);
    }

    if (pathname === "/admin/sip/pools/pool-us-backup/members" && method === "POST") {
      const body = request.postDataJSON() as { trunk_id: string };
      pools = pools.map((pool) =>
        pool.trunk_pool_id === "pool-us-backup"
          ? {
              ...pool,
              members: [
                ...pool.members,
                {
                  trunk_id: body.trunk_id,
                  name: trunks.find((trunk) => trunk.trunk_id === body.trunk_id)?.name ?? body.trunk_id,
                  provider_name: "Twilio",
                  priority: 100,
                },
              ],
            }
          : pool
      );
      return ok(route, pools.find((pool) => pool.trunk_pool_id === "pool-us-backup"));
    }

    if (pathname === "/admin/sip/pools/pool-uk-primary" && method === "PATCH") {
      const body = request.postDataJSON() as { name?: string };
      pools = pools.map((pool) =>
        pool.trunk_pool_id === "pool-uk-primary"
          ? { ...pool, name: body.name ?? pool.name }
          : pool
      );
      return ok(route, pools.find((pool) => pool.trunk_pool_id === "pool-uk-primary"));
    }

    if (pathname === "/admin/sip/pools/pool-uk-primary/assign/tenant-acme" && method === "PATCH") {
      const body = request.postDataJSON() as {
        tenant_label?: string;
        is_default?: boolean;
        is_active?: boolean;
        max_channels?: number | null;
        reserved_channels?: number | null;
      };
      pools = pools.map((pool) =>
        pool.trunk_pool_id === "pool-uk-primary"
          ? {
              ...pool,
              assignments: pool.assignments.map((assignment) =>
                assignment.tenant_id === "tenant-acme"
                  ? {
                      ...assignment,
                      tenant_label: body.tenant_label ?? assignment.tenant_label,
                      is_default: body.is_default ?? assignment.is_default,
                      is_active: body.is_active ?? assignment.is_active,
                      max_channels:
                        body.max_channels === undefined ? assignment.max_channels : body.max_channels,
                      reserved_channels:
                        body.reserved_channels === undefined
                          ? assignment.reserved_channels
                          : body.reserved_channels,
                    }
                  : assignment
              ),
            }
          : pool
      );
      return ok(route, pools.find((pool) => pool.trunk_pool_id === "pool-uk-primary"));
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke admin sip page", () => {
  test("renders compact pool list and supports synced trunk, create, and edit modals", async ({ page }) => {
    await installAuthSession(page, { role: "system_admin" });
    await mockAdminSipApi(page);

    await page.goto("/admin/sip");

    await expect(page.getByRole("heading", { name: "SIP Admin" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Synced bridge trunks/i })).toBeVisible();
    await expect(page.getByText("UK Outbound", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Edit pool" }).first()
    ).toBeVisible();

    await page.getByRole("button", { name: /Synced bridge trunks/i }).click();
    await expect(page.getByRole("dialog", { name: "Synced bridge trunks" })).toBeVisible();
    await expect(page.getByText("Twilio UK", { exact: true })).toBeVisible();
    await page.getByLabel("Close synced trunks").click();

    await page.getByRole("button", { name: "Edit pool" }).first().click();
    const editDialog = page.getByRole("dialog", { name: "Edit trunk pool" });
    await expect(editDialog).toBeVisible();
    await expect(editDialog.getByRole("button", { name: "Overview" })).toBeVisible();
    await expect(editDialog.getByRole("button", { name: "Trunks" })).toBeVisible();
    await expect(editDialog.getByRole("button", { name: "Assignments & Quotas" })).toBeVisible();

    await page.getByLabel("Pool name").fill("UK Primary");
    await editDialog.getByRole("button", { name: "Assignments & Quotas" }).click();
    await expect(editDialog.getByText("No channel quota set")).not.toBeVisible();
    await editDialog.getByRole("button", { name: "Edit", exact: true }).click();
    await editDialog.getByLabel("Tenant label").first().fill("Acme Priority");
    await editDialog.getByLabel("Reserved channels").first().fill("8");
    await editDialog.getByRole("button", { name: "Save assignment" }).click();

    await expect(editDialog.getByText("Acme Priority", { exact: true })).toBeVisible();

    await editDialog.getByRole("button", { name: "Overview" }).click();
    await editDialog.getByRole("button", { name: "Save changes" }).click();

    await expect(page.locator("main").getByText("UK Primary", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Create pool" }).click();
    const createDialog = page.getByRole("dialog", { name: "Create trunk pool" });
    await expect(createDialog).toBeVisible();
    await page.getByLabel("Pool name").fill("US Backup");
    await createDialog.getByText("Twilio US", { exact: true }).click();
    await createDialog.getByRole("button", { name: "Create pool" }).click();

    await expect(page.getByText("US Backup", { exact: true })).toBeVisible();
  });
});
