import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const SEEDED_DRAFT_YAML = `version: "1.0"
id: seeded-draft
name: Seeded Draft
type: reliability
description: Seeded builder draft
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 12
scoring:
  overall_gate: false
  rubric: []
tags: [draft]
turns:
  - id: t1
    speaker: harness
    text: Hello from seeded draft
    wait_for_response: true
`;

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockBuilderLandingApi(page: Page): Promise<void> {
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
      return ok(route, { tts_cache_enabled: true });
    }

    if (pathname === "/providers/available" && method === "GET") {
      return ok(route, {
        items: [
          {
            provider_id: "openai:gpt-4o-mini-tts",
            vendor: "openai",
            model: "gpt-4o-mini-tts",
            capability: "tts",
            runtime_scopes: ["api", "agent"],
            credential_source: "env",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
          },
          {
            provider_id: "deepgram:nova-2-general",
            vendor: "deepgram",
            model: "nova-2-general",
            capability: "stt",
            runtime_scopes: ["agent"],
            credential_source: "env",
            configured: false,
            availability_status: "agent_managed",
            supports_tenant_credentials: false,
          },
        ],
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return ok(route, [
        {
          id: "billing-smoke",
          name: "Billing Smoke",
          description: "Happy path billing support",
          namespace: "support/billing",
          scenario_kind: "graph",
          turns: 3,
          tags: ["smoke"],
          type: "smoke",
          cache_status: "warm",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-1",
        },
        {
          id: "refunds-regression",
          name: "Refunds Regression",
          description: "Refund edge cases over chat",
          namespace: "support/refunds",
          scenario_kind: "graph",
          turns: 5,
          tags: ["regression", "http"],
          type: "regression",
          cache_status: "warm",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-3",
        },
        {
          id: "hidden-ai-backing",
          name: "AI Backing Scenario",
          description: "",
          namespace: "support/ai",
          scenario_kind: "ai",
          turns: 2,
          tags: [],
          type: "smoke",
          cache_status: "cold",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-2",
        },
      ]);
    }

    return route.continue();
  });
}

test("bare /builder renders the landing shell", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder");

  await expect(page.getByTestId("builder-landing-shell")).toBeVisible();
  await expect(page.getByTestId("builder-landing-create-panel")).toBeVisible();
  await expect(page.getByTestId("builder-landing-open-panel")).toBeVisible();
  await expect(page.getByTestId("builder-right-panel")).toHaveCount(0);
  await expect(page.getByTestId("builder-landing-open-scenario-billing-smoke")).toBeVisible();
});

test("landing starts a blank seeded draft from scenario name", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder");
  await page.getByTestId("builder-landing-name-input").fill("Billing escalation smoke");
  await page.getByTestId("builder-landing-start-btn").click();

  await page.waitForURL("**/builder?new=1");
  await expect(page.getByTestId("builder-landing-shell")).toHaveCount(0);
  await expect(page.getByTestId("builder-right-panel")).toBeVisible();
  await expect(page.getByTestId("metadata-name-input")).toHaveValue("Billing escalation smoke");
  await expect(page.getByTestId("metadata-id-input")).toHaveValue("billing-escalation-smoke");
});

test("landing template selection seeds optional protocol and type hints", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder");
  await page.getByTestId("builder-landing-name-input").fill("Adversarial prompt guard");
  await page.getByTestId("builder-landing-template-select").selectOption("adversarial_refusal");
  await page.getByTestId("builder-landing-protocol-select").selectOption("mock");
  await page.getByTestId("builder-landing-start-btn").click();

  await page.waitForURL("**/builder?new=1");
  await expect(page.getByTestId("metadata-type-select")).toHaveValue("adversarial");
  await expect(page.getByTestId("metadata-bot-connection-toggle")).toBeVisible();
  await page.getByTestId("metadata-bot-connection-toggle").click();
  await expect(page.getByTestId("metadata-bot-protocol-select")).toHaveValue("mock");
});

test("landing open-existing panel filters and opens a graph scenario", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder");
  await page.getByTestId("builder-landing-open-search-input").fill("refund");
  await expect(page.getByTestId("builder-landing-open-scenario-refunds-regression")).toBeVisible();
  await expect(page.getByTestId("builder-landing-open-scenario-billing-smoke")).toHaveCount(0);

  await page.getByTestId("builder-landing-open-toggle-tags").click();
  await page.getByTestId("builder-landing-open-tag-http").click();
  // billing-smoke has no http tag — must remain absent after combined filter
  await expect(page.getByTestId("builder-landing-open-scenario-billing-smoke")).toHaveCount(0);
  await page.getByTestId("builder-landing-open-scenario-refunds-regression").click();

  await page.waitForURL("**/builder?id=refunds-regression");
  await expect(page.getByTestId("builder-landing-shell")).toHaveCount(0);
  await expect(page.getByTestId("builder-right-panel")).toBeVisible();
});

test("landing open-existing namespace filter narrows the list", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder");
  // Both graph scenarios are visible before filtering
  await expect(page.getByTestId("builder-landing-open-scenario-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("builder-landing-open-scenario-refunds-regression")).toBeVisible();

  // Click the support/billing namespace node (testid uses __ for /)
  await page.getByTestId("builder-landing-open-namespace-support__billing").click();
  await expect(page.getByTestId("builder-landing-open-scenario-billing-smoke")).toBeVisible();
  await expect(page.getByTestId("builder-landing-open-scenario-refunds-regression")).toHaveCount(0);
});

test("/builder?id=<scenarioId> routes directly to workspace", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderLandingApi(page);

  await page.goto("/builder?id=billing-smoke");

  await expect(page.getByTestId("builder-landing-shell")).toHaveCount(0);
  await expect(page.getByTestId("builder-right-panel")).toBeVisible();
});

test("seeded draft still opens the workspace on /builder?new=1", async ({ page }) => {
  await installAuthSession(page, { role: "editor" });
  await page.addInitScript(
    ({ yaml }) => {
      // BUILDER_DRAFT_SEED_KEY from hooks/useBuilderLoad.ts
      window.sessionStorage.setItem("botcheck:builder:seed_yaml", yaml);
      // BUILDER_FOCUS_FIELD_KEY from hooks/useBuilderLoad.ts
      window.sessionStorage.setItem("botcheck:builder:focus_field", "metadata-id");
    },
    { yaml: SEEDED_DRAFT_YAML }
  );
  await mockBuilderLandingApi(page);

  await page.goto("/builder?new=1");

  await expect(page.getByTestId("builder-landing-shell")).toHaveCount(0);
  await expect(page.getByTestId("builder-right-panel")).toBeVisible();
  await expect(page.getByTestId("metadata-id-input")).toBeFocused();
});
