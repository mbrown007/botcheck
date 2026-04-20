import type {
  PlaygroundExtractedTool,
  PlaygroundMode,
  PlaygroundPresetDetail,
  PlaygroundPresetPatch,
  PlaygroundPresetSummary,
  PlaygroundPresetWrite,
} from "@/lib/api";

export type PlaygroundPresetTargetChoice =
  | { kind: "graph"; id: string }
  | { kind: "ai"; id: string };

export interface PlaygroundPresetFormState {
  targetChoice: PlaygroundPresetTargetChoice | null;
  mode: PlaygroundMode;
  systemPrompt: string;
  transportProfileId: string;
  extractedTools: PlaygroundExtractedTool[];
  stubEditorJson: Record<string, string>;
}

export interface PlaygroundPresetBuildInput {
  name: string;
  description: string;
  targetChoice: PlaygroundPresetTargetChoice | null;
  mode: PlaygroundMode;
  systemPrompt: string;
  transportProfileId: string;
  parsedStubs: Record<string, Record<string, unknown>>;
}

export function buildPlaygroundPresetPayload(
  input: PlaygroundPresetBuildInput
): PlaygroundPresetWrite | null {
  if (!input.targetChoice) {
    return null;
  }
  const toolStubs =
    input.mode === "mock" && Object.keys(input.parsedStubs).length > 0
      ? input.parsedStubs
      : undefined;
  const payload: PlaygroundPresetWrite = {
    name: input.name.trim(),
    playground_mode: input.mode,
  };
  const description = normalizeOptionalString(input.description);
  if (description !== undefined) {
    payload.description = description;
  }
  if (input.targetChoice.kind === "graph") {
    payload.scenario_id = input.targetChoice.id;
  } else {
    payload.ai_scenario_id = input.targetChoice.id;
  }
  const systemPrompt =
    input.mode === "mock" ? normalizeOptionalString(input.systemPrompt) : undefined;
  if (systemPrompt !== undefined) {
    payload.system_prompt = systemPrompt;
  }
  const transportProfileId =
    input.mode === "direct_http" ? normalizeOptionalString(input.transportProfileId) : undefined;
  if (transportProfileId !== undefined) {
    payload.transport_profile_id = transportProfileId;
  }
  if (toolStubs !== undefined) {
    payload.tool_stubs = toolStubs;
  }
  return payload;
}

export function buildPlaygroundPresetPatchPayload(
  input: PlaygroundPresetBuildInput
): PlaygroundPresetPatch | null {
  if (!input.targetChoice) {
    return null;
  }
  // Pre-compute; only assigned to patch.tool_stubs in mock branch — direct_http always sends null.
  const toolStubs = Object.keys(input.parsedStubs).length > 0 ? input.parsedStubs : null;
  const patch: PlaygroundPresetPatch = {
    name: input.name.trim(),
    playground_mode: input.mode,
    description: normalizeOptionalString(input.description) ?? null,
  };
  // Explicitly null out the non-applicable target field so the backend clears stale data.
  if (input.targetChoice.kind === "graph") {
    patch.scenario_id = input.targetChoice.id;
    patch.ai_scenario_id = null;
  } else {
    patch.ai_scenario_id = input.targetChoice.id;
    patch.scenario_id = null;
  }
  // Explicitly null out mode-inapplicable fields so the backend clears stale data.
  if (input.mode === "mock") {
    patch.system_prompt = normalizeOptionalString(input.systemPrompt) ?? null;
    patch.transport_profile_id = null;
    patch.tool_stubs = toolStubs;
  } else {
    patch.system_prompt = null;
    patch.transport_profile_id = normalizeOptionalString(input.transportProfileId) ?? null;
    patch.tool_stubs = null;
  }
  return patch;
}

export function hydratePlaygroundPreset(
  preset: PlaygroundPresetDetail
): PlaygroundPresetFormState {
  const targetChoice: PlaygroundPresetTargetChoice | null =
    preset.scenario_id != null
      ? { kind: "graph", id: preset.scenario_id }
      : preset.ai_scenario_id != null
        ? { kind: "ai", id: preset.ai_scenario_id }
        : null;
  const toolStubs = preset.tool_stubs ?? {};
  return {
    targetChoice,
    mode: preset.playground_mode,
    systemPrompt: preset.system_prompt ?? "",
    transportProfileId: preset.transport_profile_id ?? "",
    extractedTools: Object.keys(toolStubs).map((name) => ({
      name,
      description: "",
      parameters: {},
    })),
    stubEditorJson: Object.fromEntries(
      Object.entries(toolStubs).map(([name, value]) => [name, JSON.stringify(value, null, 2)])
    ),
  };
}

export function summarizePlaygroundPresetTarget(preset: PlaygroundPresetSummary): string {
  if (preset.scenario_id) {
    return `Graph · ${preset.scenario_id}`;
  }
  if (preset.ai_scenario_id) {
    return `AI · ${preset.ai_scenario_id}`;
  }
  return "Target unavailable";
}

export function nextPlaygroundPresetCopyName(
  sourceName: string,
  existingNames: readonly string[]
): string {
  const trimmed = sourceName.trim();
  const base = trimmed.length > 0 ? trimmed : "Playground preset";
  const normalized = new Set(existingNames.map((name) => name.trim().toLowerCase()));
  const firstCandidate = `${base} Copy`;
  if (!normalized.has(firstCandidate.toLowerCase())) {
    return firstCandidate;
  }
  // Sequence starts at 2 (i.e. "Copy", "Copy 2", "Copy 3") — intentional, matching Finder convention.
  let copyNumber = 2;
  while (normalized.has(`${base} Copy ${copyNumber}`.toLowerCase())) {
    copyNumber += 1;
  }
  return `${base} Copy ${copyNumber}`;
}

function normalizeOptionalString(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}
