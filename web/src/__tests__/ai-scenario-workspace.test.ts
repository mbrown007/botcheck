import assert from "node:assert/strict";
import test from "node:test";
import type { AIPersonaSummary, AIScenarioSummary } from "@/lib/api/types";
import {
  buildAIScenarioPersonaNameById,
  countAIScenarioRecords,
  findSelectedAIScenario,
} from "@/lib/ai-scenario-workspace";

const PERSONAS: AIPersonaSummary[] = [
  {
    persona_id: " persona_1 ",
    name: "internal-parent",
    display_name: " Concerned Parent ",
    avatar_url: null,
    backstory_summary: null,
    style: "empathetic",
    voice: "alloy",
    is_active: true,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
  {
    persona_id: "persona_2",
    name: "fallback-name",
    display_name: "   ",
    avatar_url: null,
    backstory_summary: null,
    style: "direct",
    voice: "verse",
    is_active: true,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
  {
    persona_id: "   ",
    name: "ignored",
    display_name: "Ignored",
    avatar_url: null,
    backstory_summary: null,
    style: "calm",
    voice: "nova",
    is_active: true,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
];

const SCENARIOS: AIScenarioSummary[] = [
  {
    ai_scenario_id: "ai_delay",
    scenario_id: "ai-backing-delay",
    name: "Delayed flight",
    persona_id: "persona_1",
    scenario_brief: "Parent asks for help.",
    scenario_facts: {},
    evaluation_objective: "Confirm options.",
    opening_strategy: "wait_for_bot_greeting",
    is_active: true,
    scoring_profile: null,
    dataset_source: null,
    record_count: 2,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
  {
    ai_scenario_id: "ai_refund",
    scenario_id: "ai-backing-refund",
    name: "Refund request",
    persona_id: "persona_2",
    scenario_brief: "Customer wants a refund.",
    scenario_facts: {},
    evaluation_objective: "Explain refund path.",
    opening_strategy: "caller_opens",
    is_active: true,
    scoring_profile: null,
    dataset_source: null,
    record_count: 3,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
];

test("buildAIScenarioPersonaNameById prefers trimmed display_name and falls back to name", () => {
  const names = buildAIScenarioPersonaNameById(PERSONAS);

  assert.equal(names.get("persona_1"), "Concerned Parent");
  assert.equal(names.get("persona_2"), "fallback-name");
  assert.equal(names.has(""), false);
});

test("countAIScenarioRecords sums record counts and defaults undefined to zero", () => {
  assert.equal(countAIScenarioRecords(SCENARIOS), 5);
  assert.equal(countAIScenarioRecords(undefined), 0);
});

test("findSelectedAIScenario returns the selected scenario and handles missing ids", () => {
  assert.equal(findSelectedAIScenario(SCENARIOS, "ai_refund")?.name, "Refund request");
  assert.equal(findSelectedAIScenario(SCENARIOS, "missing"), undefined);
  assert.equal(findSelectedAIScenario(SCENARIOS, null), undefined);
});
