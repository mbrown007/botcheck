import assert from "node:assert/strict";
import test from "node:test";

import type { AIScenarioSummary, ScenarioSummary } from "@/lib/api";
import {
  buildPackCatalogItems,
  buildPackCatalogNamespaceTree,
  filterPackCatalog,
} from "@/lib/pack-catalog";

function makeGraphScenario(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: "graph_billing_smoke",
    name: "Billing Smoke",
    description: "Checks the baseline billing path",
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

function makeAIScenario(overrides: Partial<AIScenarioSummary> = {}): AIScenarioSummary {
  return {
    ai_scenario_id: "ai_refunds_probe",
    scenario_id: "ai-backing-refunds-probe",
    name: "Refunds Probe",
    namespace: "support/refunds",
    persona_id: "persona_refunds",
    scenario_brief: "Ask for a refund",
    scenario_facts: {},
    evaluation_objective: "Validate refund policy",
    opening_strategy: "caller_opens",
    is_active: true,
    scoring_profile: null,
    dataset_source: null,
    record_count: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

test("buildPackCatalogItems carries namespace and scenario kind across graph and AI rows", () => {
  const items = buildPackCatalogItems(
    [makeGraphScenario()],
    [makeAIScenario()],
  );

  assert.deepEqual(items, [
    {
      key: "graph:graph_billing_smoke",
      id: "graph_billing_smoke",
      name: "Billing Smoke",
      namespace: "support/billing",
      kind: "GRAPH",
      tags: ["smoke", "http"],
    },
    {
      key: "ai:ai_refunds_probe",
      id: "ai_refunds_probe",
      name: "Refunds Probe",
      namespace: "support/refunds",
      kind: "AI",
      tags: [],
    },
  ]);
});

test("buildPackCatalogNamespaceTree counts shared parents and unscoped items", () => {
  const nodes = buildPackCatalogNamespaceTree(
    buildPackCatalogItems(
      [
        makeGraphScenario({ id: "graph_1", namespace: "support/billing" }),
        makeGraphScenario({ id: "graph_2", namespace: null }),
      ],
      [
        makeAIScenario({ ai_scenario_id: "ai_1", namespace: "support/refunds" }),
        makeAIScenario({ ai_scenario_id: "ai_2", namespace: "sales/inbound" }),
      ],
    ),
  );

  assert.deepEqual(nodes, [
    { path: "sales", label: "sales", depth: 0, count: 1 },
    { path: "sales/inbound", label: "inbound", depth: 1, count: 1 },
    { path: "support", label: "support", depth: 0, count: 2 },
    { path: "support/billing", label: "billing", depth: 1, count: 1 },
    { path: "support/refunds", label: "refunds", depth: 1, count: 1 },
    { path: "__ungrouped__", label: "Unscoped", depth: 0, count: 1 },
  ]);
});

test("filterPackCatalog applies namespace scope and cross-field search", () => {
  const items = buildPackCatalogItems(
    [
      makeGraphScenario({ id: "graph_billing_smoke", namespace: "support/billing", tags: ["smoke", "voice"] }),
      makeGraphScenario({ id: "graph_sales", namespace: "sales/inbound", name: "Sales Inbound" }),
    ],
    [
      makeAIScenario({ ai_scenario_id: "ai_refunds_probe", namespace: "support/refunds", name: "Refunds Probe" }),
    ],
  );

  assert.deepEqual(
    filterPackCatalog(items, {
      namespacePath: "support",
      searchQuery: "",
    }).map((item) => item.id),
    ["graph_billing_smoke", "ai_refunds_probe"],
  );

  assert.deepEqual(
    filterPackCatalog(items, {
      namespacePath: null,
      searchQuery: "voice",
    }).map((item) => item.id),
    ["graph_billing_smoke"],
  );

  assert.deepEqual(
    filterPackCatalog(items, {
      namespacePath: "sales",
      searchQuery: "inbound",
    }).map((item) => item.id),
    ["graph_sales"],
  );
});
