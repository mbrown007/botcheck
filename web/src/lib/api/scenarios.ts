import useSWR from "swr";
import { apiFetch, apiFetchBlob, fetcher } from "./fetcher";
import type {
  ScenarioSummary,
  ScenarioDefinition,
  AIPersonaSummary,
  AIPersonaDetail,
  AIPersonaUpsertRequest,
  AIScenarioSummary,
  AIScenarioDetail,
  AIScenarioRecord,
  AIScenarioRecordUpsertRequest,
  AIScenarioUpsertRequest,
  ScenarioCacheStateResponse,
  ScenarioCacheRebuildResponse,
  ScenarioSourceResponse,
  ScenarioValidationResult,
  GenerateJobResponse,
  GeneratedScenario,
} from "./types";

export function useScenarios() {
  return useSWR<ScenarioSummary[]>("/scenarios/", fetcher);
}

export function useAIPersonas(enabled = true) {
  return useSWR<AIPersonaSummary[]>(
    enabled ? "/scenarios/personas" : null,
    fetcher,
    { refreshInterval: enabled ? 10000 : 0 }
  );
}

export function useAIScenarios(enabled = true) {
  return useSWR<AIScenarioSummary[]>(
    enabled ? "/scenarios/ai-scenarios" : null,
    fetcher,
    { refreshInterval: enabled ? 10000 : 0 }
  );
}

export function useAIScenario(aiScenarioId: string | null, enabled = true) {
  return useSWR<AIScenarioDetail>(
    enabled && aiScenarioId ? `/scenarios/ai-scenarios/${aiScenarioId}` : null,
    fetcher,
    { refreshInterval: enabled && aiScenarioId ? 10000 : 0 }
  );
}

export function useAIScenarioRecords(aiScenarioId: string | null, enabled = true) {
  return useSWR<AIScenarioRecord[]>(
    enabled && aiScenarioId ? `/scenarios/ai-scenarios/${aiScenarioId}/records` : null,
    fetcher,
    { refreshInterval: enabled && aiScenarioId ? 10000 : 0 }
  );
}

export function useScenario(id: string | null) {
  return useSWR<ScenarioDefinition>(id ? `/scenarios/${id}` : null, fetcher);
}

export function useScenarioCacheState(
  scenarioId: string | null,
  enabled: boolean
) {
  return useSWR<ScenarioCacheStateResponse>(
    scenarioId && enabled ? `/scenarios/${scenarioId}/cache/state` : null,
    fetcher,
    {
      refreshInterval: enabled ? 10000 : 0,
    }
  );
}

export function useGenerateJob(jobId: string | null) {
  return useSWR<GenerateJobResponse>(
    jobId ? `/scenarios/generate/${jobId}` : null,
    fetcher,
    {
      refreshInterval: (data) =>
        data?.status === "pending" || data?.status === "running" ? 2000 : 0,
    }
  );
}

export async function uploadScenario(yaml: string): Promise<ScenarioSummary> {
  return apiFetch<ScenarioSummary>("/scenarios/", {
    method: "POST",
    json: { yaml_content: yaml },
    context: "Upload failed",
  });
}

export async function validateScenarioYaml(
  yaml: string
): Promise<ScenarioValidationResult> {
  return apiFetch<ScenarioValidationResult>("/scenarios/validate", {
    method: "POST",
    json: { yaml_content: yaml },
    context: "Validate failed",
  });
}

export async function getScenarioSource(
  scenarioId: string
): Promise<ScenarioSourceResponse> {
  return apiFetch<ScenarioSourceResponse>(`/scenarios/${scenarioId}/source`, {
    context: "Load scenario source failed",
  });
}

export async function updateScenario(
  scenarioId: string,
  yaml: string
): Promise<ScenarioSummary> {
  return apiFetch<ScenarioSummary>(`/scenarios/${scenarioId}`, {
    method: "PUT",
    json: { yaml_content: yaml },
    context: "Update scenario failed",
  });
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  await apiFetch<void>(`/scenarios/${scenarioId}`, {
    method: "DELETE",
    context: "Delete scenario failed",
  });
}

export async function rebuildScenarioCache(
  scenarioId: string
): Promise<ScenarioCacheRebuildResponse> {
  return apiFetch<ScenarioCacheRebuildResponse>(`/scenarios/${scenarioId}/cache/rebuild`, {
    method: "POST",
    context: "Rebuild cache failed",
  });
}

export async function previewScenarioTurnAudio(
  scenarioId: string,
  turnId: string
): Promise<Blob> {
  return apiFetchBlob(`/scenarios/${scenarioId}/turns/${turnId}/audio`, {
    context: "Preview audio failed",
  });
}

export async function generateScenarios(req: {
  target_system_prompt: string;
  steering_prompt?: string;
  user_objective: string;
  count: number;
}): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>("/scenarios/generate", {
    method: "POST",
    json: req,
    context: "Generate failed",
  });
}

export async function createAIPersona(
  payload: AIPersonaUpsertRequest
): Promise<AIPersonaDetail> {
  return apiFetch<AIPersonaDetail>("/scenarios/personas", {
    method: "POST",
    json: payload,
    context: "Create persona failed",
  });
}

export async function getAIPersona(personaId: string): Promise<AIPersonaDetail> {
  return apiFetch<AIPersonaDetail>(`/scenarios/personas/${personaId}`, {
    context: "Load persona failed",
  });
}

export async function updateAIPersona(
  personaId: string,
  payload: AIPersonaUpsertRequest
): Promise<AIPersonaDetail> {
  return apiFetch<AIPersonaDetail>(`/scenarios/personas/${personaId}`, {
    method: "PUT",
    json: payload,
    context: "Update persona failed",
  });
}

export async function deleteAIPersona(personaId: string): Promise<void> {
  await apiFetch<void>(`/scenarios/personas/${personaId}`, {
    method: "DELETE",
    context: "Delete persona failed",
  });
}

export async function createAIScenario(
  payload: AIScenarioUpsertRequest
): Promise<AIScenarioDetail> {
  return apiFetch<AIScenarioDetail>("/scenarios/ai-scenarios", {
    method: "POST",
    json: payload,
    context: "Create AI scenario failed",
  });
}

export async function getAIScenario(aiScenarioId: string): Promise<AIScenarioDetail> {
  return apiFetch<AIScenarioDetail>(`/scenarios/ai-scenarios/${aiScenarioId}`, {
    context: "Load AI scenario failed",
  });
}

export async function updateAIScenario(
  aiScenarioId: string,
  payload: AIScenarioUpsertRequest
): Promise<AIScenarioDetail> {
  return apiFetch<AIScenarioDetail>(`/scenarios/ai-scenarios/${aiScenarioId}`, {
    method: "PUT",
    json: payload,
    context: "Update AI scenario failed",
  });
}

export async function deleteAIScenario(aiScenarioId: string): Promise<void> {
  await apiFetch<void>(`/scenarios/ai-scenarios/${aiScenarioId}`, {
    method: "DELETE",
    context: "Delete AI scenario failed",
  });
}

export async function createAIScenarioRecord(
  aiScenarioId: string,
  payload: AIScenarioRecordUpsertRequest
): Promise<AIScenarioRecord> {
  return apiFetch<AIScenarioRecord>(`/scenarios/ai-scenarios/${aiScenarioId}/records`, {
    method: "POST",
    json: payload,
    context: "Create AI scenario record failed",
  });
}

export async function deleteAIScenarioRecord(
  aiScenarioId: string,
  recordId: string
): Promise<void> {
  await apiFetch<void>(`/scenarios/ai-scenarios/${aiScenarioId}/records/${recordId}`, {
    method: "DELETE",
    context: "Delete AI scenario record failed",
  });
}

// Re-export types used by consumers that import from this module
export type { GeneratedScenario };
