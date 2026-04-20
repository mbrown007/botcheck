import assert from "node:assert/strict";
import test from "node:test";

import type { ScenarioSummary } from "../lib/api/types";
import {
  filterGraphScenarios,
  resolveBuilderScenarioAccess,
} from "../lib/builder-scenario-access";

function makeScenario(
  overrides: Partial<ScenarioSummary> & Pick<ScenarioSummary, "id" | "name">
): ScenarioSummary {
  return {
    id: overrides.id,
    name: overrides.name,
    type: overrides.type ?? "reliability",
    scenario_kind: overrides.scenario_kind ?? "graph",
    description: overrides.description ?? "",
    version_hash: overrides.version_hash ?? "abcdef1234567890",
    cache_status: overrides.cache_status ?? "cold",
    cache_updated_at: overrides.cache_updated_at ?? "",
    tags: overrides.tags ?? [],
    turns: overrides.turns ?? 2,
    created_at: overrides.created_at ?? "2026-03-09T12:00:00Z",
  };
}

test("filterGraphScenarios removes ai scenarios from builder-visible lists", () => {
  const scenarios = [
    makeScenario({ id: "graph-1", name: "Graph One", scenario_kind: "graph" }),
    makeScenario({ id: "ai-1", name: "AI One", scenario_kind: "ai" }),
  ];

  assert.deepEqual(
    filterGraphScenarios(scenarios).map((scenario) => scenario.id),
    ["graph-1"]
  );
});

test("resolveBuilderScenarioAccess defers while scenario kind is unresolved", () => {
  const access = resolveBuilderScenarioAccess({
    scenarioId: "maybe-ai",
    scenarios: undefined,
    scenariosResolved: false,
  });

  assert.equal(access.shouldDeferLoad, true);
  assert.equal(access.shouldRedirectToAIScenarios, false);
  assert.equal(access.targetScenario, null);
});

test("resolveBuilderScenarioAccess redirects ai scenarios away from builder", () => {
  const access = resolveBuilderScenarioAccess({
    scenarioId: "ai-backing",
    scenarios: [
      makeScenario({
        id: "ai-backing",
        name: "AI Backing",
        scenario_kind: "ai",
      }),
    ],
    scenariosResolved: true,
  });

  assert.equal(access.shouldDeferLoad, false);
  assert.equal(access.shouldRedirectToAIScenarios, true);
  assert.equal(access.targetScenario?.id, "ai-backing");
});

test("resolveBuilderScenarioAccess allows graph scenarios to load", () => {
  const access = resolveBuilderScenarioAccess({
    scenarioId: "graph-1",
    scenarios: [
      makeScenario({
        id: "graph-1",
        name: "Graph One",
        scenario_kind: "graph",
      }),
    ],
    scenariosResolved: true,
  });

  assert.equal(access.shouldDeferLoad, false);
  assert.equal(access.shouldRedirectToAIScenarios, false);
  assert.equal(access.targetScenario?.id, "graph-1");
});
