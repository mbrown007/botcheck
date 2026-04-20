import assert from "node:assert/strict";
import test from "node:test";

import type { ScenarioSummary } from "@/lib/api";
import {
  buildScenarioNamespaceTree,
  collectScenarioTags,
  filterScenarioCatalog,
  matchesScenarioSearch,
} from "@/lib/scenario-catalog";

function makeScenario(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: "scenario_1",
    name: "Billing Happy Path",
    description: "Validates the core support flow",
    turns: 4,
    type: "smoke",
    tags: ["smoke", "http"],
    scenario_kind: "graph",
    cache_status: "cold",
    cache_updated_at: null,
    created_at: null,
    version_hash: "abc123",
    namespace: "support/billing",
    ...overrides,
  };
}

test("buildScenarioNamespaceTree counts parents and unscoped scenarios", () => {
  const nodes = buildScenarioNamespaceTree([
    makeScenario({ id: "s1", namespace: "support/billing" }),
    makeScenario({ id: "s2", namespace: "support/refunds" }),
    makeScenario({ id: "s3", namespace: "sales/inbound" }),
    makeScenario({ id: "s4", namespace: null }),
  ]);

  assert.deepEqual(nodes, [
    { path: "sales", label: "sales", depth: 0, count: 1 },
    { path: "sales/inbound", label: "inbound", depth: 1, count: 1 },
    { path: "support", label: "support", depth: 0, count: 2 },
    { path: "support/billing", label: "billing", depth: 1, count: 1 },
    { path: "support/refunds", label: "refunds", depth: 1, count: 1 },
    { path: "__ungrouped__", label: "Unscoped", depth: 0, count: 1 },
  ]);
});

test("matchesScenarioSearch covers id name description namespace and tags", () => {
  const scenario = makeScenario({
    id: "billing_jailbreak_probe",
    description: "Try to push the bot off task",
    namespace: "support/escalations",
    tags: ["adversarial", "http"],
  });

  assert.equal(matchesScenarioSearch(scenario, "jailbreak"), true);
  assert.equal(matchesScenarioSearch(scenario, "off task"), true);
  assert.equal(matchesScenarioSearch(scenario, "escalations"), true);
  assert.equal(matchesScenarioSearch(scenario, "adversarial"), true);
  assert.equal(matchesScenarioSearch(scenario, "nonexistent"), false);
});

test("filterScenarioCatalog applies namespace prefix search and tag intersection", () => {
  const scenarios = [
    makeScenario({ id: "billing-smoke", namespace: "support/billing", tags: ["smoke", "http"] }),
    makeScenario({ id: "billing-adversarial", namespace: "support/billing", tags: ["adversarial", "http"] }),
    makeScenario({ id: "refunds-smoke", namespace: "support/refunds", tags: ["smoke", "voice"] }),
    makeScenario({ id: "ungrouped", namespace: null, tags: ["smoke"] }),
  ];

  const supportSmoke = filterScenarioCatalog(scenarios, {
    namespacePath: "support",
    searchQuery: "billing",
    selectedTags: ["http"],
  });
  assert.deepEqual(
    supportSmoke.map((scenario) => scenario.id),
    ["billing-smoke", "billing-adversarial"],
  );

  const supportBillingAdversarial = filterScenarioCatalog(scenarios, {
    namespacePath: "support/billing",
    searchQuery: "",
    selectedTags: ["adversarial", "http"],
  });
  assert.deepEqual(
    supportBillingAdversarial.map((scenario) => scenario.id),
    ["billing-adversarial"],
  );

  const unscoped = filterScenarioCatalog(scenarios, {
    namespacePath: "__ungrouped__",
    searchQuery: "",
    selectedTags: [],
  });
  assert.deepEqual(
    unscoped.map((scenario) => scenario.id),
    ["ungrouped"],
  );
});

test("collectScenarioTags returns unique normalized tags in stable order", () => {
  const tags = collectScenarioTags([
    makeScenario({ tags: ["Smoke", "http"] }),
    makeScenario({ id: "s2", tags: ["adversarial", " smoke "] }),
  ]);

  assert.deepEqual(tags, ["adversarial", "http", "Smoke"]);
});

test("catalog helpers tolerate summaries without tags", () => {
  // tags is non-optional in the type but may arrive as undefined from older API responses
  const partial = makeScenario({ tags: undefined as never });

  assert.equal(matchesScenarioSearch(partial, "billing"), true);
  assert.deepEqual(
    filterScenarioCatalog([partial], {
      namespacePath: null,
      searchQuery: "",
      selectedTags: [],
    }).map((scenario) => scenario.id),
    [partial.id],
  );
  assert.deepEqual(collectScenarioTags([partial]), []);
});
