import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const GRAPH_SCENARIO_ID = "scenario_playground_graph";
const SIP_SCENARIO_ID = "scenario_playground_sip";
const AI_SCENARIO_ID = "ai_playground_demo";
const RUN_ID = "run_playground_demo";
const DESTINATION_ID = "dest_http_playground";
const PRESET_ID = "preset_playground_mock";
const PRESET_COPY_ID = "preset_playground_mock_copy";
const PRESET_HTTP_ID = "preset_playground_http";

interface MockPlaygroundPreset {
  preset_id: string;
  name: string;
  description: string | null;
  playground_mode: "mock" | "direct_http";
  scenario_id: string | null;
  ai_scenario_id: string | null;
  transport_profile_id: string | null;
  system_prompt: string | null;
  tool_stubs: Record<string, unknown> | null;
  has_tool_stubs: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockPlaygroundApi(
  page: Page,
  role: "viewer" | "editor",
  options: { aiEnabled?: boolean } = {}
) {
  const createBodies: Array<Record<string, unknown>> = [];
  const presetBodies: Array<Record<string, unknown>> = [];
  let lastRunMode: "mock" | "direct_http" = "mock";
  let lastRunTransport: "mock" | "http" = "mock";
  const aiEnabled = options.aiEnabled === true;
  let presets: MockPlaygroundPreset[] = [
    {
      preset_id: PRESET_ID,
      name: "Billing smoke preset",
      description: "Shared mock setup",
      playground_mode: "mock",
      scenario_id: GRAPH_SCENARIO_ID,
      ai_scenario_id: null,
      transport_profile_id: null,
      system_prompt: "You are a careful billing bot.",
      tool_stubs: {
        lookup_invoice: { outcome: "found" },
      },
      has_tool_stubs: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      created_by: "user_editor",
      updated_by: "user_editor",
    },
    {
      preset_id: PRESET_HTTP_ID,
      name: "Billing live HTTP preset",
      description: "Shared direct HTTP setup",
      playground_mode: "direct_http",
      scenario_id: GRAPH_SCENARIO_ID,
      ai_scenario_id: null,
      transport_profile_id: DESTINATION_ID,
      system_prompt: null,
      tool_stubs: null,
      has_tool_stubs: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      created_by: "user_editor",
      updated_by: "user_editor",
    },
  ];

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
        ai_scenarios_enabled: aiEnabled,
        destinations_enabled: true,
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
          {
            provider_id: "openai:gpt-4o-mini",
            vendor: "openai",
            model: "gpt-4o-mini",
            capability: "llm",
            runtime_scopes: ["api"],
            credential_source: "env",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
          },
          {
            provider_id: "anthropic:claude-sonnet-4-6",
            vendor: "anthropic",
            model: "claude-sonnet-4-6",
            capability: "judge",
            runtime_scopes: ["judge"],
            credential_source: "db_encrypted",
            configured: true,
            availability_status: "available",
            supports_tenant_credentials: false,
          },
        ],
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return ok(route, [
        {
          id: GRAPH_SCENARIO_ID,
          name: "HTTP Playground Graph",
          scenario_kind: "graph",
          turns: 3,
          tags: [],
          description: "",
          type: "smoke",
          cache_status: "cold",
          version_hash: "v1",
        },
        {
          id: SIP_SCENARIO_ID,
          name: "SIP Only Scenario",
          scenario_kind: "graph",
          turns: 2,
          tags: [],
          description: "",
          type: "smoke",
          cache_status: "cold",
          version_hash: "v2",
        },
      ]);
    }

    if (pathname === `/scenarios/${GRAPH_SCENARIO_ID}` && method === "GET") {
      return ok(route, {
        id: GRAPH_SCENARIO_ID,
        name: "HTTP Playground Graph",
        scenario_kind: "graph",
        version: "1.0",
        type: "smoke",
        description: "",
        tags: [],
        bot: { endpoint: "https://bot.internal/chat", protocol: "http" },
        persona: { role: "customer", style: "neutral" },
        config: {
          max_total_turns: 8,
          turn_timeout_s: 20,
          max_duration_s: 120,
          bot_join_timeout_s: 60,
          transfer_timeout_s: 35,
          initial_drain_s: 2,
          inter_turn_pause_s: 0,
          transcript_merge_window_s: 1.5,
          stt_endpointing_ms: 2000,
          language: "en-US",
          stt_provider: "deepgram",
          stt_model: "nova-2-phonecall",
          tts_voice: "openai:nova",
        },
        scoring: { overall_gate: true, rubric: [] },
        turns: [
          { id: "t1", speaker: "harness", text: "Hello", wait_for_response: true, config: {} },
        ],
      });
    }

    if (pathname === `/scenarios/${GRAPH_SCENARIO_ID}/source` && method === "GET") {
      return ok(route, {
        yaml_content: [
          `scenario_id: ${GRAPH_SCENARIO_ID}`,
          "version: \"1.0\"",
          "name: HTTP Playground Graph",
          "type: smoke",
          "bot:",
          "  protocol: http",
          "  endpoint: https://bot.internal/chat",
          "turns:",
          "  - id: t1",
          "    speaker: harness",
          "    text: Hello",
        ].join("\n"),
      });
    }

    if (pathname === `/scenarios/${SIP_SCENARIO_ID}` && method === "GET") {
      return ok(route, {
        id: SIP_SCENARIO_ID,
        name: "SIP Only Scenario",
        scenario_kind: "graph",
        version: "1.0",
        type: "smoke",
        description: "",
        tags: [],
        bot: { endpoint: "sip:bot@test.example.com", protocol: "sip" },
        persona: { role: "customer", style: "neutral" },
        config: {
          max_total_turns: 8,
          turn_timeout_s: 20,
          max_duration_s: 120,
          bot_join_timeout_s: 60,
          transfer_timeout_s: 35,
          initial_drain_s: 2,
          inter_turn_pause_s: 0,
          transcript_merge_window_s: 1.5,
          stt_endpointing_ms: 2000,
          language: "en-US",
          stt_provider: "deepgram",
          stt_model: "nova-2-phonecall",
          tts_voice: "openai:nova",
        },
        scoring: { overall_gate: true, rubric: [] },
        turns: [
          { id: "t1", speaker: "harness", text: "Hello", wait_for_response: true, config: {} },
        ],
      });
    }

    if (pathname === "/scenarios/validate" && method === "POST") {
      return ok(route, {
        valid: true,
        scenario_id: GRAPH_SCENARIO_ID,
        turns: 1,
        errors: [],
      });
    }

    if (pathname === `/scenarios/${GRAPH_SCENARIO_ID}` && method === "PUT") {
      return ok(route, {
        id: GRAPH_SCENARIO_ID,
        name: "HTTP Playground Graph",
        scenario_kind: "graph",
        turns: 1,
        tags: [],
        description: "",
        type: "smoke",
        cache_status: "cold",
        version_hash: "v2",
      });
    }

    if (pathname === "/destinations/" && method === "GET") {
      return ok(route, [
        {
          destination_id: DESTINATION_ID,
          name: "Direct Bot API",
          protocol: "http",
          endpoint: "https://bot.internal/chat",
          default_dial_target: "https://bot.internal/chat",
          headers: {},
          is_active: true,
          in_use: false,
          active_pack_run_count: 0,
          active_schedule_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]);
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET" && aiEnabled) {
      return ok(route, [
        {
          ai_scenario_id: AI_SCENARIO_ID,
          scenario_id: GRAPH_SCENARIO_ID,
          name: "AI Billing Assistant",
          display_name: "AI Billing Assistant",
          persona_id: "persona_ai_demo",
          persona_name: "Alex",
          opening_strategy: "wait_for_bot_greeting",
          dataset_source: "manual",
          scoring_profile: "default",
          record_count: 0,
          is_active: true,
        },
      ]);
    }

    if (pathname === "/runs/playground/presets" && method === "GET") {
      return ok(route, presets.map((preset) => ({
        preset_id: preset.preset_id,
        name: preset.name,
        description: preset.description,
        playground_mode: preset.playground_mode,
        scenario_id: preset.scenario_id,
        ai_scenario_id: preset.ai_scenario_id,
        transport_profile_id: preset.transport_profile_id,
        has_tool_stubs: preset.has_tool_stubs,
        created_at: preset.created_at,
        updated_at: preset.updated_at,
        created_by: preset.created_by,
        updated_by: preset.updated_by,
      })));
    }

    if (pathname === "/runs/playground/presets" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      presetBodies.push(body);
      // Assign PRESET_ID only when it is not yet taken; use PRESET_COPY_ID otherwise.
      const presetId = presets.some((p) => p.preset_id === PRESET_ID) ? PRESET_COPY_ID : PRESET_ID;
      const previous = presets[presets.length - 1];
      const nextPreset: MockPlaygroundPreset = {
        ...previous,
        ...body,
        preset_id: presetId,
        scenario_id: typeof body.scenario_id === "string" ? body.scenario_id : null,
        ai_scenario_id: typeof body.ai_scenario_id === "string" ? body.ai_scenario_id : null,
        transport_profile_id:
          typeof body.transport_profile_id === "string" ? body.transport_profile_id : null,
        system_prompt: typeof body.system_prompt === "string" ? body.system_prompt : null,
        tool_stubs:
          body.tool_stubs && typeof body.tool_stubs === "object"
            ? (body.tool_stubs as Record<string, unknown>)
            : null,
        has_tool_stubs:
          !!body.tool_stubs && Object.keys(body.tool_stubs as Record<string, unknown>).length > 0,
        updated_at: new Date().toISOString(),
      };
      presets = [...presets, nextPreset];
      return ok(route, nextPreset, 201);
    }

    if (pathname.startsWith("/runs/playground/presets/") && method === "GET") {
      const presetId = pathname.split("/").pop();
      const preset = presets.find((item) => item.preset_id === presetId);
      if (preset) {
        return ok(route, preset);
      }
    }

    if (pathname.startsWith("/runs/playground/presets/") && method === "DELETE") {
      const presetId = pathname.split("/").pop();
      presets = presets.filter((item) => item.preset_id !== presetId);
      return route.fulfill({ status: 204 });
    }

    if (pathname === "/runs/playground" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      createBodies.push(body);
      const playgroundMode =
        body.playground_mode === "direct_http" ? "direct_http" : "mock";
      const transport = playgroundMode === "direct_http" ? "http" : "mock";
      lastRunMode = playgroundMode;
      lastRunTransport = transport;
      return ok(
        route,
        {
          run_id: RUN_ID,
          scenario_id: GRAPH_SCENARIO_ID,
          state: "pending",
          run_type: "playground",
          playground_mode: playgroundMode,
          trigger_source: "manual",
          transport,
          events: [],
          conversation: [],
          created_at: new Date().toISOString(),
        },
        202
      );
    }

    if (pathname === `/runs/${RUN_ID}/stream` && method === "GET") {
      const debugFrames = aiEnabled
        ? [
            "id: 4.1",
            "event: harness.classifier_input",
            `data: ${JSON.stringify({
              run_id: RUN_ID,
              sequence_number: 41,
              event_type: "harness.classifier_input",
              payload: { transcript: "Yes, I can help with billing." },
              created_at: new Date().toISOString(),
            })}`,
            "",
            "id: 4.2",
            "event: harness.classifier_output",
            `data: ${JSON.stringify({
              run_id: RUN_ID,
              sequence_number: 42,
              event_type: "harness.classifier_output",
              payload: { selected_case: "continue", confidence: 0.82 },
              created_at: new Date().toISOString(),
            })}`,
            "",
            "id: 4.3",
            "event: harness.caller_reasoning",
            `data: ${JSON.stringify({
              run_id: RUN_ID,
              sequence_number: 43,
              event_type: "harness.caller_reasoning",
              payload: { summary: "Continue by proposing a concrete appointment time." },
              created_at: new Date().toISOString(),
            })}`,
            "",
          ]
        : [];
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "id: 1",
          "event: turn.start",
          `data: ${JSON.stringify({
            run_id: RUN_ID,
            sequence_number: 1,
            event_type: "turn.start",
            payload: {
              turn_id: "t1",
              speaker: "harness",
              text: "Can you help with billing?",
            },
            created_at: new Date().toISOString(),
          })}`,
          "",
          "id: 2",
          "event: turn.response",
          `data: ${JSON.stringify({
            run_id: RUN_ID,
            sequence_number: 2,
            event_type: "turn.response",
            payload: {
              turn_id: "t1",
              transcript: "Can you help with billing?",
              latency_ms: 1,
            },
            created_at: new Date().toISOString(),
          })}`,
          "",
          "id: 3",
          "event: turn.response",
          `data: ${JSON.stringify({
            run_id: RUN_ID,
            sequence_number: 3,
            event_type: "turn.response",
            payload: {
              turn_id: "t1_bot",
              transcript: "Yes, I can help with billing.",
              latency_ms: 84,
            },
            created_at: new Date().toISOString(),
          })}`,
          "",
          "id: 4",
          "event: turn.expect",
          `data: ${JSON.stringify({
            run_id: RUN_ID,
            sequence_number: 4,
            event_type: "turn.expect",
            payload: {
              assertion: "transferred_to",
              passed: true,
            },
            created_at: new Date().toISOString(),
          })}`,
          "",
          ...debugFrames,
          "id: 5",
          "event: run.complete",
          `data: ${JSON.stringify({
            run_id: RUN_ID,
            sequence_number: 5,
            event_type: "run.complete",
            payload: {
              run_id: RUN_ID,
              summary: "Playground run completed after 2 turns.",
              gate_passed: null,
            },
            created_at: new Date().toISOString(),
          })}`,
          "",
          "",
        ].join("\n"),
      });
    }

    if (pathname === `/runs/${RUN_ID}` && method === "GET") {
      return ok(route, {
        run_id: RUN_ID,
        scenario_id: GRAPH_SCENARIO_ID,
        state: "pending",
        run_type: "playground",
        playground_mode: lastRunMode,
        trigger_source: "manual",
        transport: lastRunTransport,
        events: [],
        conversation: [],
        created_at: new Date().toISOString(),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });

  return { createBodies, presetBodies };
}

test.describe("@smoke playground page", () => {
  test("viewer is blocked from the route", async ({ page }) => {
    await installAuthSession(page, { role: "viewer" });
    await mockPlaygroundApi(page, "viewer");

    await page.goto("/playground");

    await expect(page.getByText("Playground access is restricted to editor role or above.")).toBeVisible();
  });

  test("editor can launch a mock playground run and gets run_id in the URL", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    const state = await mockPlaygroundApi(page, "editor");

    await page.goto("/playground");

    await expect(page.getByRole("heading", { name: "Playground", exact: true })).toBeVisible();
    await expect(page.getByTestId("playground-provider-access-card")).toContainText(
      "anthropic:claude-sonnet-4-6"
    );
    await expect(page.getByTestId("playground-scenario-select")).toContainText("HTTP Playground Graph");
    await expect(page.getByTestId("playground-scenario-select")).not.toContainText("SIP Only Scenario");

    await page.getByTestId("playground-system-prompt").fill("You are a calm support bot.");
    await page.getByTestId("playground-run-button").click();

    await expect(page).toHaveURL(new RegExp(`run_id=${RUN_ID}$`));
    await expect(page.getByText("Playground run created.", { exact: true })).toBeVisible();
    await expect(page.getByTestId("playground-activity-feed")).toContainText("Can you help with billing?");
    await expect(page.getByTestId("playground-activity-feed")).toContainText("Yes, I can help with billing.");
    await expect(page.getByTestId("playground-progress-pane")).toContainText("t1");
    await expect(page.getByTestId("playground-progress-pane")).toContainText("Passed");
    await expect(page.getByTestId("playground-summary-bar")).toContainText(
      "Playground run completed after 2 turns."
    );

    expect(state.createBodies).toEqual([
      {
        scenario_id: GRAPH_SCENARIO_ID,
        playground_mode: "mock",
        system_prompt: "You are a calm support bot.",
      },
    ]);
    await expect(page.getByTestId("playground-debug-panel")).toHaveCount(0);
  });

  test("ai playground run shows the harness reasoning panel", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    const state = await mockPlaygroundApi(page, "editor", { aiEnabled: true });

    await page.goto("/playground");
    await page.getByTestId("playground-scenario-select").selectOption(`ai:${AI_SCENARIO_ID}`);
    await page.getByTestId("playground-system-prompt").fill("You are a calm support bot.");
    await page.getByTestId("playground-launch-controls-toggle").click();
    await expect(page.getByTestId("playground-launch-controls-card")).toHaveCount(0);
    await page.getByTestId("playground-run-button").click();

    await expect(page.getByTestId("playground-debug-panel")).toBeVisible();
    await page.getByTestId("playground-debug-toggle").click();
    await expect(page.getByTestId("playground-debug-panel")).toContainText("Caller reasoning");
    await expect(page.getByTestId("playground-debug-panel")).toContainText(
      "Continue by proposing a concrete appointment time."
    );
    await expect(page.getByTestId("playground-debug-panel")).toContainText("Classifier output");
    await expect(page.getByTestId("playground-debug-panel")).toContainText("continue");

    expect(state.createBodies).toEqual([
      {
        ai_scenario_id: AI_SCENARIO_ID,
        playground_mode: "mock",
        system_prompt: "You are a calm support bot.",
      },
    ]);
  });

  test("graph scenario yaml can be opened from the top action bar", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    await mockPlaygroundApi(page, "editor");

    await page.goto("/playground");

    await expect(page.getByTestId("playground-edit-yaml-button")).toBeVisible();
    await page.getByTestId("playground-edit-yaml-button").click();

    await expect(page.getByRole("dialog", { name: "Edit Scenario" })).toBeVisible();
    await expect(page.getByPlaceholder("Edit YAML...")).toContainText(`scenario_id: ${GRAPH_SCENARIO_ID}`);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Scenario YAML updated.", { exact: true })).toBeVisible();
  });

  test("editor can save and load a preset without recreating the setup", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    const state = await mockPlaygroundApi(page, "editor");

    await page.goto("/playground");

    await page.getByTestId("playground-preset-name").fill("Billing smoke preset");
    await page.getByTestId("playground-preset-description").fill("Shared mock setup");
    await page.getByTestId("playground-system-prompt").fill("You are a careful billing bot.");
    await page.getByTestId("playground-stub-card-lookup_invoice").waitFor({ state: "detached" }).catch(() => {});
    await page.getByRole("button", { name: "Save as New", exact: true }).click();

    await expect(page.getByText('Saved preset "Billing smoke preset".')).toBeVisible();
    expect(state.presetBodies).toEqual([
      {
        name: "Billing smoke preset",
        description: "Shared mock setup",
        playground_mode: "mock",
        scenario_id: GRAPH_SCENARIO_ID,
        system_prompt: "You are a careful billing bot.",
      },
    ]);

    await page.getByTestId("playground-system-prompt").fill("temporary change");
    await page.getByTestId("playground-preset-select").selectOption(PRESET_ID);
    await page.getByRole("button", { name: "Load Setup", exact: true }).click();

    await expect(page.getByText('Loaded preset "Billing smoke preset".')).toBeVisible();
    await expect(page.getByTestId("playground-system-prompt")).toHaveValue(
      "You are a careful billing bot."
    );
    await expect(page.getByTestId("playground-preset-description")).toHaveValue("Shared mock setup");
    await expect(page.getByTestId("playground-relaunch-note")).toContainText(
      "current visible setup"
    );
    await expect(page.getByTestId("playground-run-button")).toContainText("Relaunch Current Setup");

    await page.getByTestId("playground-run-button").click();
    expect(state.createBodies.at(-1)).toEqual({
      scenario_id: GRAPH_SCENARIO_ID,
      playground_mode: "mock",
      system_prompt: "You are a careful billing bot.",
      tool_stubs: {
        lookup_invoice: { outcome: "found" },
      },
    });
  });

  test("editor can duplicate a preset and relaunch from the current hydrated setup", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    const state = await mockPlaygroundApi(page, "editor");

    await page.goto("/playground");
    await page.getByTestId("playground-preset-select").selectOption(PRESET_ID);
    await page.getByRole("button", { name: "Load Setup", exact: true }).click();

    await page.getByRole("button", { name: "Duplicate as New", exact: true }).click();

    await expect(page.getByText('Saved copy "Billing smoke preset Copy".')).toBeVisible();
    await expect(page.getByTestId("playground-preset-name")).toHaveValue(
      "Billing smoke preset Copy"
    );
    await expect(page.getByTestId("playground-preset-select")).toHaveValue(PRESET_COPY_ID);
    expect(state.presetBodies.at(-1)).toEqual({
      name: "Billing smoke preset Copy",
      description: "Shared mock setup",
      playground_mode: "mock",
      scenario_id: GRAPH_SCENARIO_ID,
      system_prompt: "You are a careful billing bot.",
      tool_stubs: {
        lookup_invoice: { outcome: "found" },
      },
    });

    await page.getByTestId("playground-run-button").click();
    expect(state.createBodies.at(-1)).toEqual({
      scenario_id: GRAPH_SCENARIO_ID,
      playground_mode: "mock",
      system_prompt: "You are a careful billing bot.",
      tool_stubs: {
        lookup_invoice: { outcome: "found" },
      },
    });
  });

  test("editor can launch a direct HTTP preset without mock-only fields", async ({ page }) => {
    await installAuthSession(page, { role: "editor" });
    const state = await mockPlaygroundApi(page, "editor");

    await page.goto("/playground");
    await page.getByTestId("playground-preset-select").selectOption(PRESET_HTTP_ID);
    await page.getByRole("button", { name: "Load Setup", exact: true }).click();

    await expect(page.getByText('Loaded preset "Billing live HTTP preset".')).toBeVisible();
    await expect(page.getByTestId("playground-http-profile-select")).toHaveValue(DESTINATION_ID);
    await expect(page.getByTestId("playground-run-button")).toContainText("Relaunch Current Setup");

    await page.getByTestId("playground-run-button").click();
    expect(state.createBodies.at(-1)).toEqual({
      scenario_id: GRAPH_SCENARIO_ID,
      playground_mode: "direct_http",
      transport_profile_id: DESTINATION_ID,
    });
  });

});
