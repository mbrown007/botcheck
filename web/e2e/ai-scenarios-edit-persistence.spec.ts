import { expect, test, type Page, type Route } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const AI_SCENARIO_ID = "delayed-flight";

type ScenarioState = {
  summary: Record<string, unknown>;
  detail: Record<string, unknown>;
  lastPatchBody: Record<string, unknown> | null;
};

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockAIScenariosApi(page: Page, state: ScenarioState): Promise<void> {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (await maybeMockIdentityRoute(route, { pathname, method }, { role: "admin" })) {
      return;
    }

    if (pathname === "/features" && method === "GET") {
      return ok(route, {
        tts_cache_enabled: true,
        ai_scenarios_enabled: true,
        speech_capabilities: {
          tts: [
            { id: "openai", label: "OpenAI", enabled: true, voice_mode: "static_select" },
          ],
          stt: [{ id: "azure", label: "Azure", enabled: true, voice_mode: "freeform_id" }],
        },
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
            provider_id: "azure:azure-speech",
            vendor: "azure",
            model: "azure-speech",
            capability: "stt",
            runtime_scopes: ["api", "agent"],
            credential_source: "env",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: true,
          },
        ],
      });
    }

    if (pathname === "/scenarios/personas" && method === "GET") {
      return ok(route, [
        {
          persona_id: "persona_1",
          name: "anxious-parent",
          display_name: "Anxious Parent",
          style: "stressed but polite",
          voice: "warm",
          is_active: true,
          created_at: "2026-03-11T10:00:00Z",
          updated_at: "2026-03-11T10:00:00Z",
        },
      ]);
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      return ok(route, [state.summary]);
    }

    if (pathname === `/scenarios/ai-scenarios/${AI_SCENARIO_ID}` && method === "GET") {
      return ok(route, state.detail);
    }

    if (pathname === `/scenarios/ai-scenarios/${AI_SCENARIO_ID}` && method === "PUT") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.lastPatchBody = body;
      state.summary = {
        ...state.summary,
        ...body,
        updated_at: "2026-03-11T11:00:00Z",
      };
      state.detail = {
        ...state.detail,
        ...body,
        config: {
          ...(state.detail.config as Record<string, unknown>),
          ...(body.config as Record<string, unknown>),
        },
        updated_at: "2026-03-11T11:00:00Z",
      };
      return ok(route, state.detail);
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke AI scenario edit persistence", () => {
  test("edit wizard rehydrates stored speech/runtime config and persists updates", async ({ page }) => {
    const state: ScenarioState = {
      summary: {
        ai_scenario_id: AI_SCENARIO_ID,
        name: "Delayed flight reassurance",
        persona_id: "persona_1",
        scenario_brief: "Original brief",
        scenario_facts: {},
        evaluation_objective: "Original objective",
        opening_strategy: "wait_for_bot_greeting",
        is_active: true,
        scoring_profile: null,
        dataset_source: null,
        record_count: 0,
        created_at: "2026-03-11T10:00:00Z",
        updated_at: "2026-03-11T10:00:00Z",
      },
      detail: {
        ai_scenario_id: AI_SCENARIO_ID,
        scenario_id: "ai-runtime-delayed-flight",
        name: "Delayed flight reassurance",
        persona_id: "persona_1",
        scenario_brief: "Original brief",
        scenario_facts: {},
        evaluation_objective: "Original objective",
        opening_strategy: "wait_for_bot_greeting",
        is_active: true,
        scoring_profile: null,
        dataset_source: null,
        record_count: 0,
        created_at: "2026-03-11T10:00:00Z",
        updated_at: "2026-03-11T10:00:00Z",
        config: {
          tts_voice: "openai:alloy",
          stt_provider: "azure",
          stt_model: "azure-base",
          max_total_turns: 9,
        },
      },
      lastPatchBody: null,
    };

    await installAuthSession(page, { role: "admin" });
    await mockAIScenariosApi(page, state);

    await page.goto("/ai-scenarios");
    await page.getByTestId(`ai-scenario-edit-${AI_SCENARIO_ID}`).click();
    await expect(page.getByRole("heading", { name: "Edit AI Scenario" })).toBeVisible();

    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await expect(page.getByTestId("ai-scenario-tts-provider-select")).toHaveValue("openai");
    await expect(page.getByTestId("ai-scenario-stt-provider-select")).toHaveValue("azure");
    await expect(page.getByTestId("ai-scenario-stt-model-input")).toHaveValue("azure-base");
    await expect(page.getByTestId("ai-scenario-runtime-max-total-turns-input")).toHaveValue("9");

    await page.getByTestId("ai-scenario-stt-model-input").fill("azure-updated");
    await page.getByTestId("ai-scenario-runtime-max-total-turns-input").fill("12");
    const patchResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        response.url().includes(`/scenarios/ai-scenarios/${AI_SCENARIO_ID}`)
    );
    await page.getByRole("button", { name: "Save Changes" }).click();
    await patchResponse;

    expect(state.lastPatchBody).toMatchObject({
      ai_scenario_id: AI_SCENARIO_ID,
      config: {
        tts_voice: "openai:alloy",
        stt_provider: "azure",
        stt_model: "azure-updated",
        max_total_turns: 12,
      },
    });

    await expect(page.getByText("AI scenario updated.")).toBeVisible();

    await page.getByTestId(`ai-scenario-edit-${AI_SCENARIO_ID}`).click();
    await expect(page.getByRole("heading", { name: "Edit AI Scenario" })).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByTestId("ai-scenario-stt-model-input")).toHaveValue("azure-updated");
    await expect(page.getByTestId("ai-scenario-runtime-max-total-turns-input")).toHaveValue(
      "12"
    );
  });
});
