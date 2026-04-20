import useSWR from "swr";

import { apiFetch, fetcher } from "./fetcher";
import type {
  AIScenarioSummary,
  PlaygroundExtractedTool,
  PlaygroundPresetDetail,
  PlaygroundPresetPatch,
  PlaygroundPresetSummary,
  PlaygroundPresetWrite,
  RunResponse,
  ScenarioDefinition,
  ScenarioSummary,
} from "./types";

export type { PlaygroundExtractedTool };
import { isPlaygroundCompatibleGraphScenario } from "@/lib/playground";

export interface PlaygroundRunCreateRequest {
  scenario_id?: string;
  ai_scenario_id?: string;
  playground_mode: "mock" | "direct_http";
  transport_profile_id?: string;
  system_prompt?: string;
  tool_stubs?: Record<string, unknown>;
}

async function loadScenarioDefinition(id: string): Promise<ScenarioDefinition> {
  return apiFetch<ScenarioDefinition>(`/scenarios/${id}`, {
    context: "Load scenario failed",
  });
}

export function usePlaygroundGraphScenarios(enabled = true) {
  return useSWR<ScenarioDefinition[]>(
    enabled ? "/playground/graph-scenarios" : null,
    async () => {
      const summaries = await fetcher<ScenarioSummary[]>("/scenarios/");
      const graphSummaries = summaries.filter((row) => row.scenario_kind !== "ai");
      const definitions = await Promise.all(graphSummaries.map((row) => loadScenarioDefinition(row.id)));
      return definitions.filter(isPlaygroundCompatibleGraphScenario);
    },
  );
}

export function usePlaygroundAIScenarios(enabled = true) {
  return useSWR<AIScenarioSummary[]>(
    enabled ? "/scenarios/ai-scenarios" : null,
    fetcher,
  );
}

export function usePlaygroundPresets(enabled = true) {
  return useSWR<PlaygroundPresetSummary[]>(
    enabled ? "/runs/playground/presets" : null,
    fetcher,
  );
}

export async function getPlaygroundPreset(presetId: string): Promise<PlaygroundPresetDetail> {
  return apiFetch<PlaygroundPresetDetail>(`/runs/playground/presets/${encodeURIComponent(presetId)}`, {
    context: "Load playground preset failed",
  });
}

export async function createPlaygroundPreset(
  body: PlaygroundPresetWrite
): Promise<PlaygroundPresetDetail> {
  return apiFetch<PlaygroundPresetDetail>("/runs/playground/presets", {
    method: "POST",
    json: body,
    context: "Create playground preset failed",
  });
}

export async function patchPlaygroundPreset(
  presetId: string,
  body: PlaygroundPresetPatch
): Promise<PlaygroundPresetDetail> {
  return apiFetch<PlaygroundPresetDetail>(`/runs/playground/presets/${encodeURIComponent(presetId)}`, {
    method: "PATCH",
    json: body,
    context: "Update playground preset failed",
  });
}

export async function deletePlaygroundPreset(presetId: string): Promise<void> {
  await apiFetch<void>(`/runs/playground/presets/${encodeURIComponent(presetId)}`, {
    method: "DELETE",
    context: "Delete playground preset failed",
  });
}

export async function extractPlaygroundTools(systemPrompt: string): Promise<PlaygroundExtractedTool[]> {
  return apiFetch<PlaygroundExtractedTool[]>("/runs/playground/extract-tools", {
    method: "POST",
    json: { system_prompt: systemPrompt },
    context: "Extract tools failed",
  });
}

export async function generatePlaygroundStubs(
  tools: PlaygroundExtractedTool[],
  scenarioSummary: string
): Promise<Record<string, Record<string, unknown>>> {
  return apiFetch<Record<string, Record<string, unknown>>>("/runs/playground/generate-stubs", {
    method: "POST",
    json: { tools, scenario_summary: scenarioSummary },
    context: "Generate stubs failed",
  });
}

export async function createPlaygroundRun(
  body: PlaygroundRunCreateRequest
): Promise<RunResponse> {
  return apiFetch<RunResponse>("/runs/playground", {
    method: "POST",
    json: body,
    context: "Create playground run failed",
  });
}
