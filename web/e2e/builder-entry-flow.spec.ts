import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthSession, maybeMockIdentityRoute } from "./helpers/auth";

const SCENARIO_ID = "builder-entry-flow";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700").replace(
  /\/$/,
  ""
);

const INITIAL_YAML = `version: "1.0"
id: builder-entry-flow
name: Builder Entry Flow
namespace: support/billing
type: reliability
description: Entry-flow regression coverage
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
tags: [smoke]
turns:
  - id: t1
    speaker: harness
    text: Hello from the entry flow
`;

async function ok(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockBuilderEntryApi(page: Page): Promise<void> {
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
      return ok(route, { tts_cache_enabled: true, ai_scenarios_enabled: true });
    }

    if (pathname === "/scenarios/" && method === "GET") {
      return ok(route, [
        {
          id: SCENARIO_ID,
          name: "Builder Entry Flow",
          description: "Entry-flow regression coverage",
          namespace: "support/billing",
          scenario_kind: "graph",
          turns: 1,
          tags: ["smoke"],
          type: "reliability",
          cache_status: "warm",
          cache_updated_at: null,
          created_at: null,
          version_hash: "ver-entry",
        },
      ]);
    }

    if (pathname === `/scenarios/${SCENARIO_ID}/source` && method === "GET") {
      return ok(route, {
        scenario_id: SCENARIO_ID,
        yaml_content: INITIAL_YAML,
      });
    }

    if (pathname === "/scenarios/validate" && method === "POST") {
      return ok(route, {
        valid: true,
        errors: [],
        scenario_id: SCENARIO_ID,
        turns: 1,
        path_summary: "t1",
      });
    }

    return route.continue();
  });
}

test("dirty workspace can transition to landing via File > New Draft after confirmation", async ({
  page,
}) => {
  await installAuthSession(page, { role: "editor" });
  await mockBuilderEntryApi(page);

  await page.goto(`/builder?id=${SCENARIO_ID}`);
  await expect(page.getByTestId("builder-right-panel")).toBeVisible();

  await page.getByTestId("metadata-name-input").fill("Unsaved Landing Transition");
  await page.getByTestId("metadata-name-input").press("Tab");
  await expect(page.getByTitle("Unsaved changes")).toBeVisible();

  const dialogPromise = page.waitForEvent("dialog");
  await page.getByRole("button", { name: "File" }).click();
  await page.getByRole("menuitem", { name: "New Draft" }).click();
  const dialog = await dialogPromise;
  expect(dialog.message()).toContain("Discard unsaved changes and switch scenario?");
  await dialog.accept();

  await page.waitForURL("**/builder");
  await expect(page.getByTestId("builder-landing-shell")).toBeVisible();
  await expect(page.getByTestId("builder-right-panel")).toHaveCount(0);
});
