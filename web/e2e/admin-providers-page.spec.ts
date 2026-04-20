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

function createProviders(): Array<Record<string, any>> {
  return [
    {
      provider_id: "openai:gpt-4o-transcribe",
      vendor: "openai",
      model: "gpt-4o-transcribe",
      capability: "stt",
      runtime_scopes: ["api", "agent"],
      supports_tenant_credentials: false,
      supports_platform_credentials: true,
      credential_source: "env",
      configured: true,
      available: true,
      availability_status: "available",
      tenant_assignment_count: 1,
      assigned_tenant: {
        tenant_id: "tenant-acme",
        tenant_display_name: "Acme Voice",
        enabled: true,
      },
      cost_metadata: {
        cost_per_input_token_microcents: 5000,
        cost_per_output_token_microcents: 7000,
        cost_per_audio_second_microcents: null,
        cost_per_character_microcents: null,
        cost_per_request_microcents: 120,
      },
      platform_credential: {
        credential_source: "env",
        validation_status: "none",
        validated_at: null,
        validation_error: null,
        updated_at: "2026-03-16T09:00:00Z",
        has_stored_secret: false,
      },
    },
    {
      provider_id: "azure:gpt-4o-mini-tts",
      vendor: "azure",
      model: "gpt-4o-mini-tts",
      capability: "tts",
      runtime_scopes: ["agent"],
      supports_tenant_credentials: true,
      supports_platform_credentials: true,
      credential_source: "env",
      configured: false,
      available: false,
      availability_status: "pending_validation",
      tenant_assignment_count: 0,
      assigned_tenant: null,
      cost_metadata: {
        cost_per_input_token_microcents: null,
        cost_per_output_token_microcents: null,
        cost_per_audio_second_microcents: null,
        cost_per_character_microcents: 9400,
        cost_per_request_microcents: null,
      },
      platform_credential: {
        credential_source: "env",
        validation_status: "pending",
        validated_at: null,
        validation_error: null,
        updated_at: "2026-03-16T10:00:00Z",
        has_stored_secret: false,
      },
    },
  ];
}

async function mockAdminProvidersApi(page: Page, role: MockAppRole): Promise<void> {
  let providers: Array<Record<string, any>> = createProviders();
  const windowStart = "2026-03-16T12:00:00Z";
  const windowEnd = "2026-03-17T12:00:00Z";
  let assignments = {
    "openai:gpt-4o-transcribe": [
      {
        tenant_id: "tenant-acme",
        provider_id: "openai:gpt-4o-transcribe",
        tenant_display_name: "Acme Voice",
        enabled: true,
        is_default: true,
        effective_credential_source: "env",
        updated_at: "2026-03-16T11:00:00Z",
      },
    ],
    "azure:gpt-4o-mini-tts": [],
  } as Record<string, Array<Record<string, unknown>>>;
  let quotaPolicies = {
    "openai:gpt-4o-transcribe": [],
    "azure:gpt-4o-mini-tts": [],
  } as Record<string, Array<Record<string, unknown>>>;
  let usageSummaryByProvider = {
    "openai:gpt-4o-transcribe": {
      window_start: windowStart,
      window_end: windowEnd,
      item: {
        provider_id: "openai:gpt-4o-transcribe",
        vendor: "openai",
        model: "gpt-4o-transcribe",
        capability: "stt",
        runtime_scopes: ["api", "agent"],
        last_recorded_at: "2026-03-17T11:45:00Z",
        input_tokens_24h: 0,
        output_tokens_24h: 0,
        audio_seconds_24h: 184.3,
        characters_24h: 0,
        sip_minutes_24h: 0,
        request_count_24h: 12,
        calculated_cost_microcents_24h: 640,
      },
    },
    "azure:gpt-4o-mini-tts": {
      window_start: windowStart,
      window_end: windowEnd,
      item: {
        provider_id: "azure:gpt-4o-mini-tts",
        vendor: "azure",
        model: "gpt-4o-mini-tts",
        capability: "tts",
        runtime_scopes: ["agent"],
        last_recorded_at: null,
        input_tokens_24h: 0,
        output_tokens_24h: 0,
        audio_seconds_24h: 0,
        characters_24h: 0,
        sip_minutes_24h: 0,
        request_count_24h: 0,
        calculated_cost_microcents_24h: null,
      },
    },
  } as Record<string, Record<string, any>>;
  let quotaSummaryByProvider = {} as Record<string, Record<string, any>>;

  function usageValueForMetric(providerId: string, metric: string): number {
    const item = usageSummaryByProvider[providerId]?.item;
    if (!item) return 0;
    if (metric === "audio_seconds") return item.audio_seconds_24h ?? 0;
    if (metric === "characters") return item.characters_24h ?? 0;
    if (metric === "input_tokens") return item.input_tokens_24h ?? 0;
    if (metric === "output_tokens") return item.output_tokens_24h ?? 0;
    if (metric === "sip_minutes") return item.sip_minutes_24h ?? 0;
    if (metric === "requests") return item.request_count_24h ?? 0;
    return 0;
  }

  function rebuildQuotaSummary(providerId: string): void {
    const provider = providers.find((item) => item.provider_id === providerId);
    if (!provider) return;
    quotaSummaryByProvider = {
      ...quotaSummaryByProvider,
      [providerId]: {
        window_start: windowStart,
        window_end: windowEnd,
        item: {
          provider_id: provider.provider_id,
          vendor: provider.vendor,
          model: provider.model,
          capability: provider.capability,
          metrics: (quotaPolicies[providerId] ?? []).map((policy) => {
            const used = usageValueForMetric(providerId, String(policy.metric));
            const limit = Number(policy.limit_per_day);
            const percentUsed = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
            const hardLimitReached = limit <= 0 ? used > 0 : used >= limit;
            const softLimitReached = percentUsed >= Number(policy.soft_limit_pct);
            return {
              metric: policy.metric,
              limit_per_day: limit,
              used_24h: used,
              remaining_24h: Math.max(limit - used, 0),
              soft_limit_pct: policy.soft_limit_pct,
              percent_used: percentUsed,
              status: hardLimitReached ? "exceeded" : softLimitReached ? "watch" : "healthy",
              soft_limit_reached: softLimitReached,
              hard_limit_reached: hardLimitReached,
            };
          }),
        },
      },
    };
  }

  rebuildQuotaSummary("openai:gpt-4o-transcribe");
  rebuildQuotaSummary("azure:gpt-4o-mini-tts");

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

    if (pathname === "/admin/providers/" && method === "GET") {
      return ok(route, { total: providers.length, items: providers });
    }

    if (pathname.startsWith("/admin/providers/") && method === "PATCH") {
      const encodedProviderId = pathname.replace("/admin/providers/", "");
      if (encodedProviderId.includes("/")) return;
      const providerId = decodeURIComponent(encodedProviderId);
      const body = request.postDataJSON() as { label?: string | null };
      providers = providers.map((provider) =>
        provider.provider_id === providerId
          ? {
              ...provider,
              label: body.label ?? null,
            }
          : provider
      );
      return ok(route, providers.find((provider) => provider.provider_id === providerId));
    }

    if (pathname === "/admin/providers/import-env-credentials" && method === "POST") {
      return ok(route, {
        imported_count: 0,
        skipped_count: providers.length,
        items: providers.map((provider) => ({
          provider_id: provider.provider_id,
          status: "skipped",
          detail: "No legacy env credential configured",
        })),
      });
    }

    if (pathname === "/admin/tenants/" && method === "GET") {
      return ok(route, {
        total: 2,
        items: [
          { tenant_id: "tenant-acme", display_name: "Acme Voice" },
          { tenant_id: "tenant-bravo", display_name: "Bravo Care" },
        ],
      });
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/quota-policies") && method === "GET") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/quota-policies", "");
      const providerId = decodeURIComponent(encodedProviderId);
      return ok(route, {
        total: quotaPolicies[providerId]?.length ?? 0,
        items: quotaPolicies[providerId] ?? [],
      });
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/usage") && method === "GET") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/usage", "");
      const providerId = decodeURIComponent(encodedProviderId);
      const data = usageSummaryByProvider[providerId];
      if (!data) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Provider assignment not found" }) });
      return ok(route, data);
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/quota") && method === "GET") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/quota", "");
      const providerId = decodeURIComponent(encodedProviderId);
      const data = quotaSummaryByProvider[providerId];
      if (!data) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Provider assignment not found" }) });
      return ok(route, data);
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/credentials") && method === "POST") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/credentials", "");
      const providerId = decodeURIComponent(encodedProviderId);
      providers = providers.map((provider) =>
        provider.provider_id === providerId
          ? {
              ...provider,
              credential_source: "db_encrypted",
              configured: true,
              available: true,
              availability_status: "available",
              platform_credential: {
                credential_source: "db_encrypted",
                validation_status: "pending",
                validated_at: null,
                validation_error: null,
                updated_at: "2026-03-17T09:00:00Z",
                has_stored_secret: true,
              },
            }
          : provider
      );
      return ok(
        route,
        {
          provider_id: providerId,
          credential_source: "db_encrypted",
          validation_status: "pending",
          validated_at: null,
          validation_error: null,
          updated_at: "2026-03-17T09:00:00Z",
        },
        202
      );
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/credentials") && method === "DELETE") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/credentials", "");
      const providerId = decodeURIComponent(encodedProviderId);
      providers = providers.map((provider) =>
        provider.provider_id === providerId
          ? {
              ...provider,
              credential_source: "env",
              available: provider.provider_id === "openai:gpt-4o-transcribe",
              availability_status:
                provider.provider_id === "openai:gpt-4o-transcribe" ? "available" : "unconfigured",
              platform_credential: {
                credential_source: "env",
                validation_status: "none",
                validated_at: null,
                validation_error: null,
                updated_at: "2026-03-17T09:05:00Z",
                has_stored_secret: false,
              },
            }
          : provider
      );
      return ok(route, {
        provider_id: providerId,
        credential_source: "env",
        validation_status: "none",
        validated_at: null,
        validation_error: null,
        updated_at: "2026-03-17T09:05:00Z",
      });
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/quota-policies") && method === "POST") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/quota-policies", "");
      const providerId = decodeURIComponent(encodedProviderId);
      const body = request.postDataJSON() as {
        tenant_id: string;
        metric: string;
        limit_per_day: number;
        soft_limit_pct: number;
      };
      const tenantDisplayName = body.tenant_id === "tenant-bravo" ? "Bravo Care" : "Acme Voice";
      const existing = quotaPolicies[providerId] ?? [];
      const nextItem = {
        quota_policy_id: `provquota_${providerId}_${body.tenant_id}_${body.metric}`.replaceAll(":", "_"),
        tenant_id: body.tenant_id,
        provider_id: providerId,
        tenant_display_name: tenantDisplayName,
        metric: body.metric,
        limit_per_day: body.limit_per_day,
        soft_limit_pct: body.soft_limit_pct,
        updated_at: "2026-03-17T09:15:00Z",
      };
      quotaPolicies = {
        ...quotaPolicies,
        [providerId]: [
          ...existing.filter(
            (item) => !(item.tenant_id === body.tenant_id && item.metric === body.metric)
          ),
          nextItem,
        ],
      };
      rebuildQuotaSummary(providerId);
      return ok(route, nextItem);
    }

    if (pathname.includes("/quota-policies/") && method === "DELETE") {
      const match = pathname.match(/^\/admin\/providers\/(.+)\/quota-policies\/([^/]+)\/([^/]+)$/);
      const providerPart = match?.[1] ?? "";
      const tenantId = match?.[2] ?? "";
      const metric = match?.[3] ?? "";
      const providerId = decodeURIComponent(providerPart);
      const decodedTenantId = decodeURIComponent(tenantId);
      const decodedMetric = decodeURIComponent(metric);
      quotaPolicies = {
        ...quotaPolicies,
        [providerId]: (quotaPolicies[providerId] ?? []).filter(
          (item) => !(item.tenant_id === decodedTenantId && item.metric === decodedMetric)
        ),
      };
      rebuildQuotaSummary(providerId);
      return ok(route, {
        provider_id: providerId,
        tenant_id: decodedTenantId,
        metric: decodedMetric,
        applied: true,
      });
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/assign") && method === "POST") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/assign", "");
      const providerId = decodeURIComponent(encodedProviderId);
      const body = request.postDataJSON() as { tenant_id: string };
      const tenantName = body.tenant_id === "tenant-bravo" ? "Bravo Care" : "Acme Voice";
      assignments = {
        ...assignments,
        [providerId]: [
          {
            tenant_id: body.tenant_id,
            provider_id: providerId,
            tenant_display_name: tenantName,
            enabled: true,
            is_default: false,
            effective_credential_source: "db_encrypted",
            updated_at: "2026-03-17T09:10:00Z",
          },
        ],
      };
      providers = providers.map((provider) =>
        provider.provider_id === providerId
          ? {
              ...provider,
              tenant_assignment_count: 1,
              assigned_tenant: {
                tenant_id: body.tenant_id,
                tenant_display_name: tenantName,
                enabled: true,
              },
            }
          : provider
      );
      rebuildQuotaSummary(providerId);
      return ok(route, providers.find((provider) => provider.provider_id === providerId));
    }

    if (pathname.startsWith("/admin/providers/") && pathname.endsWith("/assign") && method === "DELETE") {
      const encodedProviderId = pathname.replace("/admin/providers/", "").replace("/assign", "");
      const providerId = decodeURIComponent(encodedProviderId);
      assignments = {
        ...assignments,
        [providerId]: [],
      };
      providers = providers.map((provider) =>
        provider.provider_id === providerId
          ? {
              ...provider,
              tenant_assignment_count: 0,
              assigned_tenant: null,
            }
          : provider
      );
      rebuildQuotaSummary(providerId);
      return ok(route, providers.find((provider) => provider.provider_id === providerId));
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname}${search} not mocked` }),
    });
  });
}

test.describe("@smoke admin providers page", () => {
  test("system admin sees assigned and available providers and can assign/manage them", async ({ page }) => {
    await installAuthSession(page, { role: "system_admin" });
    await mockAdminProvidersApi(page, "system_admin");
    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/admin/providers");

    await expect(page.getByRole("heading", { name: "Provider Admin" })).toBeVisible();
    await expect(page.getByText("Provider Access Plane")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Assigned Providers" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Available Providers" })).toBeVisible();
    await expect(page.getByText("Acme Voice", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("No tenant assigned")).toBeVisible();

    await page.getByRole("button", { name: "Assign azure:gpt-4o-mini-tts" }).click();
    await expect(page.getByRole("heading", { name: "Assign Provider" })).toBeVisible();
    await page.getByLabel("Assign to tenant").selectOption("tenant-bravo");
    await page.getByRole("button", { name: "Assign Provider" }).click();

    await expect(
      page.getByText("Assigned azure:gpt-4o-mini-tts to Bravo Care.")
    ).toBeVisible();
    await expect(page.getByText("Bravo Care", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Bravo Care 1 provider assigned" }).click();
    await page.getByRole("button", { name: "Manage azure:gpt-4o-mini-tts" }).click();
    await expect(page.getByRole("heading", { name: "Manage Provider" })).toBeVisible();
    await expect(page.getByRole("button", { name: "overview", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "credential", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "quotas", exact: true })).toBeVisible();
    await expect(page.getByText("Estimated cost")).toBeVisible();

    await page.getByRole("button", { name: "Rename azure:gpt-4o-mini-tts" }).click();
    await page.getByLabel("Provider label").fill("Bravo speech");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(
      page.getByText("Updated provider name for azure:gpt-4o-mini-tts.")
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Bravo speech" })).toBeVisible();

    await page.getByRole("button", { name: "credential", exact: true }).click();
    await expect(
      page.getByText("Azure credentials require an API key plus either region or endpoint.")
    ).toBeVisible();

    await page.getByLabel("API key").fill("azure-secret");
    await page.getByLabel("Region").fill("uksouth");
    await page.getByRole("button", { name: "Store credential" }).click();
    await expect(
      page.getByText("Stored credential updated for azure:gpt-4o-mini-tts.")
    ).toBeVisible();

    await page.getByRole("button", { name: "quotas", exact: true }).click();
    await expect(page.getByText("Daily limits for Bravo Care")).toBeVisible();
    await page.getByLabel("Limit per day").first().fill("5000");
    await page.getByLabel("Soft limit %").first().fill("85");
    await page.getByRole("button", { name: "Save quotas" }).click();
    await expect(page.getByText("Saved quotas for azure:gpt-4o-mini-tts.").first()).toBeVisible();

    await page.getByRole("button", { name: "Unassign" }).click();
    await expect(page.getByText("Unassigned azure:gpt-4o-mini-tts.")).toBeVisible();
    await expect(page.getByText("No tenant assigned").first()).toBeVisible();
  });

  test("tenant admin is blocked from provider admin", async ({ page }) => {
    await installAuthSession(page, { role: "admin" });
    await mockAdminProvidersApi(page, "admin");

    await page.goto("/admin/providers");

    await expect(
      page.getByText("Provider administration is restricted to system_admin.")
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Back to dashboard" })).toBeVisible();
  });
});
