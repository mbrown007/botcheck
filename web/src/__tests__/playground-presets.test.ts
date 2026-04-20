import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPlaygroundPresetPayload,
  hydratePlaygroundPreset,
  nextPlaygroundPresetCopyName,
  summarizePlaygroundPresetTarget,
} from "@/lib/playground-presets";

test("buildPlaygroundPresetPayload serializes graph mock presets and omits blank fields", () => {
  const payload = buildPlaygroundPresetPayload({
    name: " Billing mock smoke ",
    description: "  ",
    targetChoice: { kind: "graph", id: "scenario_graph_1" },
    mode: "mock",
    systemPrompt: " You are a careful billing bot. ",
    transportProfileId: "",
    parsedStubs: {
      lookup_invoice: { status: "ok" },
    },
  });

  assert.deepEqual(payload, {
    name: "Billing mock smoke",
    playground_mode: "mock",
    scenario_id: "scenario_graph_1",
    system_prompt: "You are a careful billing bot.",
    tool_stubs: {
      lookup_invoice: { status: "ok" },
    },
  });
});

test("buildPlaygroundPresetPayload serializes ai direct_http presets and omits mock-only fields", () => {
  const payload = buildPlaygroundPresetPayload({
    name: "AI http preset",
    description: "Uses the real staging bot",
    targetChoice: { kind: "ai", id: "ai_scenario_1" },
    mode: "direct_http",
    systemPrompt: "ignored in http mode",
    transportProfileId: "dest_http_1",
    parsedStubs: {
      lookup_invoice: { outcome: "found" },
    },
  });

  assert.deepEqual(payload, {
    name: "AI http preset",
    description: "Uses the real staging bot",
    playground_mode: "direct_http",
    ai_scenario_id: "ai_scenario_1",
    transport_profile_id: "dest_http_1",
  });
});

test("hydratePlaygroundPreset restores tool stubs into editable JSON", () => {
  const hydrated = hydratePlaygroundPreset({
    preset_id: "preset_1",
    name: "Billing preset",
    description: null,
    playground_mode: "mock",
    scenario_id: "scenario_graph_1",
    ai_scenario_id: null,
    transport_profile_id: null,
    system_prompt: "You are a careful billing bot.",
    tool_stubs: {
      lookup_invoice: {
        outcome: "found",
        invoice_id: "inv_123",
      },
    },
    has_tool_stubs: true,
    created_at: "2026-03-13T10:00:00Z",
    updated_at: "2026-03-13T10:05:00Z",
    created_by: "user_editor",
    updated_by: "user_editor",
  });

  assert.deepEqual(hydrated.targetChoice, { kind: "graph", id: "scenario_graph_1" });
  assert.equal(hydrated.mode, "mock");
  assert.equal(hydrated.systemPrompt, "You are a careful billing bot.");
  assert.deepEqual(hydrated.extractedTools, [
    {
      name: "lookup_invoice",
      description: "",
      parameters: {},
    },
  ]);
  assert.equal(
    hydrated.stubEditorJson.lookup_invoice,
    JSON.stringify(
      {
        outcome: "found",
        invoice_id: "inv_123",
      },
      null,
      2
    )
  );
});

test("hydratePlaygroundPreset resolves AI-only preset target", () => {
  const hydrated = hydratePlaygroundPreset({
    preset_id: "preset_ai",
    name: "AI preset",
    description: null,
    playground_mode: "mock",
    scenario_id: null,
    ai_scenario_id: "ai_scenario_1",
    transport_profile_id: null,
    system_prompt: "You are a careful billing bot.",
    tool_stubs: null,
    has_tool_stubs: false,
    created_at: "2026-03-13T10:00:00Z",
    updated_at: "2026-03-13T10:05:00Z",
    created_by: "user_editor",
    updated_by: "user_editor",
  });

  assert.deepEqual(hydrated.targetChoice, { kind: "ai", id: "ai_scenario_1" });
  assert.equal(hydrated.mode, "mock");
  assert.deepEqual(hydrated.extractedTools, []);
  assert.deepEqual(hydrated.stubEditorJson, {});
});

test("hydratePlaygroundPreset returns null targetChoice when both scenario fields are null", () => {
  const hydrated = hydratePlaygroundPreset({
    preset_id: "preset_bad",
    name: "Broken preset",
    description: null,
    playground_mode: "mock",
    scenario_id: null,
    ai_scenario_id: null,
    transport_profile_id: null,
    system_prompt: null,
    tool_stubs: null,
    has_tool_stubs: false,
    created_at: "2026-03-13T10:00:00Z",
    updated_at: "2026-03-13T10:05:00Z",
    created_by: "user_editor",
    updated_by: "user_editor",
  });

  assert.equal(hydrated.targetChoice, null);
});

test("summarizePlaygroundPresetTarget returns graph label for graph preset", () => {
  assert.equal(
    summarizePlaygroundPresetTarget({
      preset_id: "preset_1",
      name: "Billing preset",
      description: null,
      playground_mode: "mock",
      scenario_id: "scenario_graph_1",
      ai_scenario_id: null,
      transport_profile_id: null,
      has_tool_stubs: false,
      created_at: "2026-03-13T10:00:00Z",
      updated_at: "2026-03-13T10:05:00Z",
      created_by: "user_editor",
      updated_by: "user_editor",
    }),
    "Graph · scenario_graph_1"
  );
});

test("summarizePlaygroundPresetTarget returns AI label for AI preset", () => {
  assert.equal(
    summarizePlaygroundPresetTarget({
      preset_id: "preset_ai",
      name: "AI preset",
      description: null,
      playground_mode: "mock",
      scenario_id: null,
      ai_scenario_id: "ai_scenario_1",
      transport_profile_id: null,
      has_tool_stubs: false,
      created_at: "2026-03-13T10:00:00Z",
      updated_at: "2026-03-13T10:05:00Z",
      created_by: "user_editor",
      updated_by: "user_editor",
    }),
    "AI · ai_scenario_1"
  );
});

test("nextPlaygroundPresetCopyName creates stable copy labels", () => {
  assert.equal(
    nextPlaygroundPresetCopyName("Billing smoke preset", ["Billing smoke preset"]),
    "Billing smoke preset Copy"
  );
  assert.equal(
    nextPlaygroundPresetCopyName("Billing smoke preset", [
      "Billing smoke preset",
      "Billing smoke preset Copy",
      "billing smoke preset copy 2",
    ]),
    "Billing smoke preset Copy 3"
  );
});

test("nextPlaygroundPresetCopyName trims sourceName and falls back for blank input", () => {
  assert.equal(
    nextPlaygroundPresetCopyName("  Billing  ", []),
    "Billing Copy"
  );
  assert.equal(
    nextPlaygroundPresetCopyName("   ", []),
    "Playground preset Copy"
  );
});
