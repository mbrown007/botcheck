import type { Page, Route } from "@playwright/test";

export type MockAppRole =
  | "viewer"
  | "operator"
  | "editor"
  | "admin"
  | "system_admin";

export interface PanelPrefsSeed {
  panelOpen: boolean;
  libraryOpen: boolean;
  metadataOpen: boolean;
  yamlOpen: boolean;
  panelWidth: number;
}

interface InstallAuthSessionOptions {
  seedPanelPrefs?: PanelPrefsSeed | null;
  role?: MockAppRole;
  userId?: string;
  tenantId?: string;
  tenantName?: string;
}

export async function installAuthSession(
  page: Page,
  options?: InstallAuthSessionOptions
): Promise<void> {
  await page.addInitScript(
    ({ seedPanelPrefs, role, userId, tenantId, tenantName }) => {
      const payload = btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 2 * 60 * 60 })
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/g, "");
      const token = `header.${payload}.sig`;
      window.localStorage.setItem(
        "botcheck_auth_session_v1",
        JSON.stringify({
          token,
          tenantId,
          tenantName,
          role,
          userId,
        })
      );
      if (seedPanelPrefs) {
        window.localStorage.setItem(
          "botcheck:builder:panel_v1",
          JSON.stringify(seedPanelPrefs)
        );
      }
    },
    {
      seedPanelPrefs: options?.seedPanelPrefs ?? null,
      role: options?.role ?? "system_admin",
      userId: options?.userId ?? "user_e2e",
      tenantId: options?.tenantId ?? "default-tenant",
      tenantName: options?.tenantName ?? "Default Tenant",
    }
  );
}

interface MockIdentityRouteOptions {
  role?: MockAppRole;
  userId?: string;
  tenantId?: string;
  tenantName?: string;
  amr?: string[];
  tenantResponse?: Record<string, unknown>;
}

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function maybeMockIdentityRoute(
  route: Route,
  {
    pathname,
    method,
  }: {
    pathname: string;
    method: string;
  },
  options?: MockIdentityRouteOptions
): Promise<boolean> {
  const role = options?.role ?? "system_admin";
  const userId = options?.userId ?? "user_e2e";
  const tenantId = options?.tenantId ?? "default-tenant";
  const tenantName = options?.tenantName ?? "Default Tenant";
  const amr = options?.amr ?? ["pwd"];

  if (pathname === "/auth/me" && method === "GET") {
    await fulfillJson(route, {
      sub: userId,
      tenant_id: tenantId,
      role,
      amr,
    });
    return true;
  }

  if (pathname === "/tenants/me" && method === "GET") {
    await fulfillJson(route, {
      tenant_id: tenantId,
      tenant_name: tenantName,
      name: tenantName,
      instance_timezone: "UTC",
      environment: "dev",
      auth_mode: "local",
      role,
      redaction_enabled: true,
      ...options?.tenantResponse,
    });
    return true;
  }

  return false;
}
