import { expect, test } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const TENANT_ID = "default-tenant";
const SCENARIO_A = "scenario_alpha";
const SCENARIO_B = "scenario_beta";
const PACK_ID = "pack_smoke";
const DEST_A = "dest_carrier_a";
const DEST_B = "dest_carrier_b";

interface ScheduleState {
  schedules: Array<Record<string, unknown>>;
  lastPatchPayload: Record<string, unknown> | null;
}

function destinationFixtures(): Array<Record<string, unknown>> {
  const now = new Date().toISOString();
  return [
    {
      destination_id: DEST_A,
      transport_profile_id: DEST_A,
      name: "Carrier A",
      protocol: "sip",
      endpoint: "sip:carrier-a@example.com",
      default_dial_target: "sip:carrier-a@example.com",
      is_active: true,
      capacity_scope: "carrier-a",
      effective_channels: 5,
      created_at: now,
      updated_at: now,
    },
    {
      destination_id: DEST_B,
      transport_profile_id: DEST_B,
      name: "Carrier B",
      protocol: "sip",
      endpoint: "sip:carrier-b@example.com",
      default_dial_target: "sip:carrier-b@example.com",
      is_active: true,
      capacity_scope: "carrier-b",
      effective_channels: 7,
      created_at: now,
      updated_at: now,
    },
  ];
}

function scheduleRow(
  scheduleId: string,
  targetType: "scenario" | "pack",
  options: {
  scenarioId?: string | null;
  packId?: string | null;
  destinationId?: string | null;
  extraOverrides?: Record<string, unknown>;
}
): Record<string, unknown> {
  const { scenarioId, packId, destinationId, extraOverrides } = options;
  const overrides: Record<string, unknown> = {
    ...(extraOverrides ?? {}),
  };
  if (destinationId) {
    overrides.transport_profile_id = destinationId;
  }
  return {
    schedule_id: scheduleId,
    target_type: targetType,
    scenario_id: scenarioId ?? null,
    pack_id: packId ?? null,
    cron_expr: "0 9 * * *",
    timezone: "UTC",
    active: true,
    misfire_policy: "skip",
    config_overrides: Object.keys(overrides).length > 0 ? overrides : null,
    last_run_at: null,
    next_run_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    last_status: "dispatched",
  };
}

async function mockSchedulesApi(
  page: import("@playwright/test").Page,
  state: ScheduleState,
  opts: { aiEnabled?: boolean; aiScenarioIds?: string[] } = {}
) {
  const aiEnabled = opts.aiEnabled === true;
  const aiScenarioIds = new Set(opts.aiScenarioIds ?? []);
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
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tts_cache_enabled: true,
          destinations_enabled: true,
          ai_scenarios_enabled: aiEnabled,
        }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: SCENARIO_A,
            name: "Scenario Alpha",
            type: "reliability",
            turns: 2,
            version_hash: "v1",
            cache_status: "cold",
            scenario_kind: aiScenarioIds.has(SCENARIO_A) ? "ai" : "graph",
          },
          {
            id: SCENARIO_B,
            name: "Scenario Beta",
            type: "reliability",
            turns: 2,
            version_hash: "v2",
            cache_status: "cold",
            scenario_kind: "graph",
          },
        ]),
      });
    }

    if (pathname === "/packs/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            pack_id: PACK_ID,
            name: "Pack Smoke",
            description: "Pack regression",
            execution_mode: "parallel",
            scenario_count: 2,
            tags: ["smoke"],
          },
        ]),
      });
    }

    if (pathname === "/scenarios/ai-scenarios" && method === "GET") {
      const now = new Date().toISOString();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          Array.from(aiScenarioIds).map((scenarioId) => ({
            ai_scenario_id: scenarioId,
            name: scenarioId === SCENARIO_A ? "Scenario Alpha" : scenarioId,
            persona_id: "persona_demo",
            scoring_profile: null,
            dataset_source: null,
            record_count: 1,
            created_at: now,
            updated_at: now,
          }))
        ),
      });
    }

    if (pathname === "/destinations/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(destinationFixtures()),
      });
    }

    if (pathname === "/schedules/preview" && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          timezone: "UTC",
          occurrences: [new Date(Date.now() + 60 * 60 * 1000).toISOString()],
        }),
      });
    }

    if (pathname === "/schedules/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.schedules),
      });
    }

    if (pathname.startsWith("/schedules/") && method === "PATCH") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.lastPatchPayload = payload;
      const current = state.schedules[0];
      const next = {
        ...current,
        ...payload,
        config_overrides:
          payload.config_overrides !== undefined
            ? payload.config_overrides
            : current.config_overrides,
      };
      state.schedules = [next];
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(next),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

test.describe("@smoke Schedules target-type switching", () => {
  test("switches scenario target to pack and keeps destination override", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [
        scheduleRow("sched_target_switch_1", "scenario", {
          scenarioId: SCENARIO_A,
          destinationId: DEST_A,
          extraOverrides: { retention_profile: "strict" },
        }),
      ],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state);

    await page.goto("/schedules");
    const scenarioRow = page.getByTestId("schedule-card-sched_target_switch_1");
    await expect(scenarioRow.getByText(`scenario:${SCENARIO_A}`).first()).toBeVisible();
    await expect(scenarioRow.getByText(`transport: Carrier A (${DEST_A})`)).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();
    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "Edit Schedule" }) });

    const targetTypeSelect = modal.getByTestId("edit-schedule-target-type");
    const targetSelect = modal.getByTestId("edit-schedule-target-id");
    const destinationSelect = modal.getByTestId("edit-schedule-destination-id");

    await targetTypeSelect.selectOption("pack");
    await targetSelect.selectOption(PACK_ID);
    await expect(destinationSelect).toHaveValue(DEST_A);

    const patchRequest = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        request.url().includes("/schedules/sched_target_switch_1")
    );
    await modal.getByRole("button", { name: "Save Changes" }).click();
    await patchRequest;

    expect(state.lastPatchPayload).toMatchObject({
      target_type: "pack",
      scenario_id: null,
      pack_id: PACK_ID,
    });
    expect(state.lastPatchPayload?.config_overrides).toBe(undefined);

    const updatedPackRow = page.getByTestId("schedule-card-sched_target_switch_1");
    await expect(updatedPackRow.getByText(`pack:${PACK_ID}`).first()).toBeVisible();
    await expect(updatedPackRow.getByText(`transport: Carrier A (${DEST_A})`)).toBeVisible();
  });

  test("switches pack target to scenario and clears destination override", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [
        scheduleRow("sched_target_switch_2", "pack", {
          packId: PACK_ID,
          destinationId: DEST_B,
          extraOverrides: { retention_profile: "strict" },
        }),
      ],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state);

    await page.goto("/schedules");
    const packRow = page.getByTestId("schedule-card-sched_target_switch_2");
    await expect(packRow.getByText(`pack:${PACK_ID}`).first()).toBeVisible();
    await expect(packRow.getByText(`transport: Carrier B (${DEST_B})`)).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();
    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "Edit Schedule" }) });

    const targetTypeSelect = modal.getByTestId("edit-schedule-target-type");
    const targetSelect = modal.getByTestId("edit-schedule-target-id");
    const destinationSelect = modal.getByTestId("edit-schedule-destination-id");

    await targetTypeSelect.selectOption("scenario");
    await targetSelect.selectOption(SCENARIO_B);
    await destinationSelect.selectOption("");

    const patchRequest = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        request.url().includes("/schedules/sched_target_switch_2")
    );
    await modal.getByRole("button", { name: "Save Changes" }).click();
    await patchRequest;

    expect(state.lastPatchPayload).toMatchObject({
      target_type: "scenario",
      scenario_id: SCENARIO_B,
      pack_id: null,
      config_overrides: {
        retention_profile: "strict",
      },
    });
    expect((state.lastPatchPayload?.config_overrides as Record<string, unknown>).transport_profile_id).toBe(
      undefined
    );

    const updatedScenarioRow = page.getByTestId("schedule-card-sched_target_switch_2");
    await expect(updatedScenarioRow.getByText(`scenario:${SCENARIO_B}`).first()).toBeVisible();
    await expect(updatedScenarioRow.getByText(`transport: Carrier B (${DEST_B})`)).toHaveCount(0);
  });

  test("separates graph and AI scenario selectors", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state, { aiEnabled: true, aiScenarioIds: [SCENARIO_A] });

    await page.goto("/schedules");
    await page.getByRole("button", { name: "New Schedule" }).click();

    const modal = page
      .locator("div.relative.z-50")
      .filter({ has: page.getByRole("heading", { name: "New Schedule" }) });
    const graphSelect = modal.getByTestId("create-schedule-target-id");
    const aiSelect = modal.getByTestId("create-schedule-ai-scenario-id");

    await expect(graphSelect.locator(`option[value="${SCENARIO_A}"]`)).toHaveCount(0);
    await expect(graphSelect.locator(`option[value="${SCENARIO_B}"]`)).toContainText(
      "Scenario Beta"
    );
    await expect(aiSelect.locator(`option[value="${SCENARIO_A}"]`)).toContainText(
      "Scenario Alpha"
    );
  });

  test("shows AI/GRAPH kind in schedule target column", async ({ page }) => {
    const state: ScheduleState = {
      schedules: [
        scheduleRow("sched_kind_ai", "scenario", {
          scenarioId: SCENARIO_A,
        }),
        scheduleRow("sched_kind_graph", "scenario", {
          scenarioId: SCENARIO_B,
        }),
      ],
      lastPatchPayload: null,
    };

    await installAuthSession(page, { role: "editor" });
    await mockSchedulesApi(page, state, { aiEnabled: true, aiScenarioIds: [SCENARIO_A] });

    await page.goto("/schedules");
    const aiRow = page.getByTestId("schedule-card-sched_kind_ai");
    const graphRow = page.getByTestId("schedule-card-sched_kind_graph");
    await expect(aiRow.getByText(`scenario:${SCENARIO_A} · AI`).first()).toBeVisible();
    await expect(graphRow.getByText(`scenario:${SCENARIO_B} · GRAPH`).first()).toBeVisible();
  });
});
