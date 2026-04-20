import { expect, test, type Page } from "@playwright/test";
import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const SCENARIO_ID = "builder-e2e";
const TENANT_ID = "default-tenant";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const INITIAL_YAML = `version: "1.0"
id: builder-e2e
name: Builder E2E
type: reliability
description: Browser save and reload flow
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
tags: [e2e]
turns:
  - id: t1
    speaker: harness
    text: Route request
    branching:
      cases:
        - condition: billing support
          next: t2
      default: t3
  - id: t2
    speaker: harness
    text: Billing branch
  - id: t3
    speaker: harness
    text: Default branch
`;

interface BuilderMockState {
  storedYaml: string;
  putCount: number;
}

interface BuilderMockOptions {
  validateResponse?: {
    valid: boolean;
    errors?: Array<{ field: string; message: string }>;
  };
}

async function mockBuilderApi(
  page: Page,
  state: BuilderMockState,
  options?: BuilderMockOptions
): Promise<void> {
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
        body: JSON.stringify({ tts_cache_enabled: true }),
      });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: SCENARIO_ID,
            name: "Builder E2E",
            type: "reliability",
            turns: 3,
            version_hash: "v1",
            cache_status: "cold",
          },
        ]),
      });
    }

    if (pathname === `/scenarios/${SCENARIO_ID}/source` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          scenario_id: SCENARIO_ID,
          yaml_content: state.storedYaml,
        }),
      });
    }

    if (pathname === "/scenarios/validate" && method === "POST") {
      const validateResponse = options?.validateResponse ?? {
        valid: true,
        errors: [],
      };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...validateResponse,
          scenario_id: SCENARIO_ID,
          turns: 3,
          path_summary: "t1 -> t2/t3",
        }),
      });
    }

    if (pathname === `/scenarios/${SCENARIO_ID}` && method === "PUT") {
      state.putCount += 1;
      const body = request.postDataJSON() as { yaml_content?: string };
      if (typeof body?.yaml_content === "string") {
        state.storedYaml = body.yaml_content;
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: SCENARIO_ID,
          name: "Builder E2E",
          type: "reliability",
          turns: 3,
          version_hash: "v2",
          cache_status: "cold",
        }),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `${method} ${pathname} not mocked` }),
    });
  });
}

async function openBuilder(page: Page): Promise<void> {
  await page.goto(`/builder?id=${SCENARIO_ID}`);
  await expect(page.getByRole("heading", { name: "Scenario Builder" })).toBeVisible();
}

test.describe("Builder save and reload", () => {
  test("@smoke persists edge label updates after save and page reload", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    await expect(page.locator(".cm-content")).toContainText("billing support");

    await page.getByTestId(/^edge-edit-btn-/).first().click();
    await page.getByPlaceholder("Condition label").fill("account billing");
    await page.getByRole("button", { name: "Save Label" }).click();

    await expect(
      page.getByTestId(/^edge-label-/).filter({ hasText: "account billing" })
    ).toHaveCount(1);

    const saveRequest = page.waitForRequest(
      (request) =>
        request.method() === "PUT" &&
        request.url().includes(`/scenarios/${SCENARIO_ID}`)
    );
    await page.getByRole("button", { name: /^Save$/ }).click();
    await saveRequest;
    expect(state.storedYaml).toContain("condition: account billing");

    await page.reload();
    await expect(
      page.getByTestId(/^edge-label-/).filter({ hasText: "account billing" })
    ).toHaveCount(1);
    await expect(page.locator(".cm-content")).toContainText("account billing");
  });

  test("edge label editor blocks reserved default and accepts valid label", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    await page.getByTestId(/^edge-edit-btn-/).first().click();
    const edgeInput = page.getByTestId("edge-condition-edit-input");
    await expect(edgeInput).toBeVisible();

    await edgeInput.fill("default");
    await page.getByTestId("edge-condition-save-btn").click();
    await expect(page.getByTestId("edge-condition-inline-error")).toHaveText(
      "Condition label 'default' is reserved for fallback routing."
    );

    await edgeInput.fill("account billing");
    await page.getByTestId("edge-condition-save-btn").click();

    await expect(page.getByTestId("edge-condition-edit-input")).toHaveCount(0);
    await expect(
      page.getByTestId(/^edge-label-/).filter({ hasText: "account billing" })
    ).toHaveCount(1);
  });

  test("persists metadata updates and metadata panel collapse across reload", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    const nameInput = page.getByTestId("metadata-name-input");
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Builder E2E Updated");

    const saveRequest = page.waitForRequest(
      (request) =>
        request.method() === "PUT" &&
        request.url().includes(`/scenarios/${SCENARIO_ID}`)
    );
    await page.getByRole("button", { name: /^Save$/ }).click();
    await saveRequest;
    expect(state.storedYaml).toContain("name: Builder E2E Updated");

    await page.getByTestId("metadata-toggle-btn").click();
    await expect(page.getByTestId("metadata-name-input")).toHaveCount(0);

    await page.reload();

    await expect(page.getByTestId("metadata-name-input")).toHaveCount(0);
    await page.getByTestId("metadata-toggle-btn").click();
    await expect(page.getByTestId("metadata-name-input")).toHaveValue(
      "Builder E2E Updated"
    );
    await expect(page.locator(".cm-content")).toContainText("name: Builder E2E Updated");
  });

  test("hydrates persisted right panel width and keeps it across reload", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, {
      role: "editor",
      seedPanelPrefs: {
        panelOpen: true,
        libraryOpen: true,
        metadataOpen: true,
        yamlOpen: true,
        panelWidth: 580,
      },
    });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    const panel = page.getByTestId("builder-right-panel");
    const expectedWidth = 580;
    const initialPanelBox = await panel.boundingBox();
    expect(initialPanelBox).not.toBeNull();
    if (!initialPanelBox) {
      throw new Error("Panel not visible");
    }
    expect(Math.abs(initialPanelBox.width - expectedWidth)).toBeLessThan(12);

    await page.reload();
    const reloadedPanelBox = await panel.boundingBox();
    expect(reloadedPanelBox).not.toBeNull();
    if (!reloadedPanelBox) {
      throw new Error("Reloaded panel not visible");
    }
    expect(Math.abs(reloadedPanelBox.width - expectedWidth)).toBeLessThan(12);
  });

  test("copy opens draft and focuses metadata id input", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    await page.getByTestId(`scenario-library-copy-${SCENARIO_ID}`).click();
    await expect(page).toHaveURL(/\/builder$/);
    await expect(page.getByTestId("metadata-id-input")).toBeFocused();
    await expect(page.getByTestId("metadata-id-input")).toHaveValue("builder-e2e-copy");
  });

  test("persists extended metadata fields after save and reload", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    await page.getByTestId("metadata-runtime-config-toggle").click();
    await page.getByTestId("metadata-description-toggle").click();

    await page.getByTestId("metadata-type-select").selectOption("compliance");
    await page.getByTestId("metadata-version-input").fill("2.1");
    await page.getByTestId("runtime-max-total-turns-input").fill("25");
    await page.getByTestId("runtime-turn-timeout-input").fill("18");
    await page.getByTestId("metadata-description-input").fill(
      "Extended metadata persistence test"
    );

    const saveRequest = page.waitForRequest(
      (request) =>
        request.method() === "PUT" &&
        request.url().includes(`/scenarios/${SCENARIO_ID}`)
    );
    await page.getByRole("button", { name: /^Save$/ }).click();
    await saveRequest;

    expect(state.storedYaml).toContain("type: compliance");
    expect(state.storedYaml).toContain('version: "2.1"');
    expect(state.storedYaml).toContain("description: Extended metadata persistence test");
    expect(state.storedYaml).toContain("max_total_turns: 25");
    expect(state.storedYaml).toContain("turn_timeout_s: 18");

    await page.reload();

    await page.getByTestId("metadata-runtime-config-toggle").click();
    await page.getByTestId("metadata-description-toggle").click();

    await expect(page.getByTestId("metadata-type-select")).toHaveValue("compliance");
    await expect(page.getByTestId("metadata-version-input")).toHaveValue("2.1");
    await expect(page.getByTestId("runtime-max-total-turns-input")).toHaveValue("25");
    await expect(page.getByTestId("runtime-turn-timeout-input")).toHaveValue("18");
    await expect(page.getByTestId("metadata-description-input")).toHaveValue(
      "Extended metadata persistence test"
    );
  });

  test("blocks save when validate returns invalid and does not call update", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state, {
      validateResponse: {
        valid: false,
        errors: [{ field: "turns", message: "mock validation failure" }],
      },
    });
    await openBuilder(page);

    await page.getByTestId("metadata-name-input").fill("Invalid Save Attempt");
    await page.getByRole("button", { name: /^Save$/ }).click();

    await expect(
      page.getByText("Validation failed. Fix scenario errors before saving.").first()
    ).toBeVisible();
    expect(state.putCount).toBe(0);
  });

  test("disables save when YAML parse error is present", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    const editor = page.locator(".cm-content").first();
    await editor.click();
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type("version: \"1.0\"\\nturns: [");
    await page.getByRole("heading", { name: "Scenario Builder" }).click();

    await expect(page.getByText(/YAML parse error:/)).toBeVisible();
    const saveButton = page.getByRole("button", { name: /^Save$/ });
    await expect(saveButton).toBeDisabled();
    expect(state.putCount).toBe(0);
  });

  test("supports undo keyboard shortcut for metadata edits", async ({ page }) => {
    const state: BuilderMockState = {
      storedYaml: INITIAL_YAML,
      putCount: 0,
    };

    await installAuthSession(page, { role: "editor" });
    await mockBuilderApi(page, state);
    await openBuilder(page);

    const nameInput = page.getByTestId("metadata-name-input");
    await nameInput.fill("Shortcut Rename");
    await page.getByRole("heading", { name: "Scenario Builder" }).click();

    await page.evaluate(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "z",
          ctrlKey: true,
          bubbles: true,
        })
      );
    });
    await expect(nameInput).toHaveValue("Builder E2E");

  });
});
