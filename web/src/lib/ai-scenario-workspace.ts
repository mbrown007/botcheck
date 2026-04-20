import type { AIPersonaSummary, AIScenarioSummary } from "@/lib/api/types";

export function buildAIScenarioPersonaNameById(
  personas: AIPersonaSummary[] | undefined
): Map<string, string> {
  const map = new Map<string, string>();
  for (const persona of personas ?? []) {
    const key = persona.persona_id.trim();
    if (!key) {
      continue;
    }
    map.set(key, persona.display_name.trim() || persona.name.trim() || key);
  }
  return map;
}

export function countAIScenarioRecords(scenarios: AIScenarioSummary[] | undefined): number {
  return (scenarios ?? []).reduce((acc, row) => acc + (row.record_count || 0), 0);
}

export function findSelectedAIScenario(
  scenarios: AIScenarioSummary[] | undefined,
  selectedAIScenarioId: string | null
): AIScenarioSummary | undefined {
  if (!selectedAIScenarioId) {
    return undefined;
  }
  return (scenarios ?? []).find((row) => row.ai_scenario_id === selectedAIScenarioId);
}
