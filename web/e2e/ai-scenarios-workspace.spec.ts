import { expect, test, type Page, type Route } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(/\/$/, "");

type MockPersona = {
  persona_id: string;
  name: string;
  display_name: string;
  style: string | null;
  voice: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type MockAIScenario = {
  ai_scenario_id: string;
  name: string;
  persona_id: string;
  scenario_brief: string;
  scenario_facts: Record<string, unknown>;
  evaluation_objective: string;
  opening_strategy: "wait_for_bot_greeting" | "caller_opens";
  is_active: boolean;
  scoring_profile: string | null;
  dataset_source: string | null;
  record_count: number;
  created_at: string;
  updated_at: string;
};

interface WorkspaceState {
  personas: MockPersona[];
  aiScenarios: MockAIScenario[];
}

function nowIso(): string {
  return new Date().toISOString();
}

function ok(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockWorkspaceApi(
  page: Page,
  state: WorkspaceState,
  opts: { aiEnabled: boolean }
): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const { pathname } = url;

    if (
      await maybeMockIdentityRoute(route, { pathname, method }, { role: "admin" })
    ) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return ok(route, {
        tts_cache_enabled: true,
        ai_scenarios_enabled: opts.aiEnabled,
      });
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

    if (pathname === "/scenarios/personas" && method === "GET") {
      return ok(route, state.personas);
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      return ok(route, state.aiScenarios);
    }

    if (pathname === "/scenarios/" && method === "POST") {
      return ok(
        route,
        {
          id: "ai-runtime-delayed-flight-abc123",
          name: "Delayed flight reassurance",
          type: "adversarial",
          description: "",
          turns: 1,
          tags: [],
          cache_status: "cold",
          version_hash: "v1",
          created_at: nowIso(),
          scenario_kind: "graph",
        },
        201
      );
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const ts = nowIso();
      const row: MockAIScenario = {
        ai_scenario_id: String(body.ai_scenario_id),
        name: String(body.name),
        persona_id: String(body.persona_id),
        scenario_brief: String(body.scenario_brief ?? ""),
        scenario_facts: (body.scenario_facts as Record<string, unknown>) ?? {},
        evaluation_objective: String(body.evaluation_objective ?? ""),
        opening_strategy:
          body.opening_strategy === "caller_opens" ? "caller_opens" : "wait_for_bot_greeting",
        is_active: true,
        scoring_profile: typeof body.scoring_profile === "string" ? body.scoring_profile : null,
        dataset_source: typeof body.dataset_source === "string" ? body.dataset_source : null,
        record_count: 0,
        created_at: ts,
        updated_at: ts,
      };
      state.aiScenarios.push(row);
      return ok(route, { ...row, config: {} }, 201);
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke AI scenarios workspace", () => {
  test("shows disabled message when AI scenarios feature is off", async ({ page }) => {
    const state: WorkspaceState = {
      personas: [],
      aiScenarios: [],
    };

    await installAuthSession(page, { role: "admin" });
    await mockWorkspaceApi(page, state, { aiEnabled: false });

    await page.goto("/ai-scenarios");
    await expect(page.getByText("AI scenarios are currently disabled for this environment.")).toBeVisible();
  });

  test("creates an AI scenario through the step-by-step wizard", async ({ page }) => {
    const state: WorkspaceState = {
      personas: [
        {
          persona_id: "persona_1",
          name: "anxious-parent",
          display_name: "Anxious Parent",
          style: "stressed but polite",
          voice: "warm",
          is_active: true,
          created_at: nowIso(),
          updated_at: nowIso(),
        },
      ],
      aiScenarios: [],
    };

    await installAuthSession(page, { role: "admin" });
    await mockWorkspaceApi(page, state, { aiEnabled: true });

    await page.goto("/ai-scenarios");
    await expect(page.getByRole("heading", { name: "AI Scenarios" })).toBeVisible();

    await page.getByRole("button", { name: "Add AI Scenario" }).click();
    await expect(page.getByRole("heading", { name: "Create AI Scenario" })).toBeVisible();

    await page.getByTestId("ai-scenario-name-input").fill("Delayed flight reassurance");
    await page.getByTestId("ai-scenario-public-id-input").fill("delayed-flight-reassurance");
    await page.getByTestId("ai-scenario-persona-select").selectOption("persona_1");
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await page.getByTestId("ai-scenario-brief-input").fill(
      "You are stuck at the airport with two young children and need a clear update about an eight hour flight delay."
    );
    await page.getByTestId("ai-scenario-facts-input").fill(
      '{\n  "booking_ref": "ABC123",\n  "airline": "Ryanair"\n}'
    );
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await page.getByTestId("ai-scenario-objective-input").fill(
      "The bot should confirm the delay clearly, explain support options, and respond with empathy."
    );
    await page.getByTestId("ai-scenario-opening-strategy").selectOption("wait_for_bot_greeting");
    await page.getByRole("button", { name: "Create AI Scenario" }).click();

    await expect(page.getByText("AI scenario created.")).toBeVisible();
    await expect(page.getByRole("table").getByText("Delayed flight reassurance")).toBeVisible();
    await expect(page.getByRole("table").getByText("Anxious Parent")).toBeVisible();
  });
});
