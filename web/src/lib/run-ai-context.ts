import type { RunEvent } from "@/lib/api/types";

interface RunAiContext {
  dataset_input: string;
  expected_output: string;
  persona_id: string;
  persona_name?: string | null;
  scenario_objective?: string | null;
}

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function parseAiContext(value: unknown): RunAiContext | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const datasetInput = asNonEmptyString(raw.dataset_input);
  const expectedOutput = asNonEmptyString(raw.expected_output);
  const personaId = asNonEmptyString(raw.persona_id);
  if (!datasetInput || !expectedOutput || !personaId) {
    return null;
  }
  return {
    dataset_input: datasetInput,
    expected_output: expectedOutput,
    persona_id: personaId,
    persona_name: asNonEmptyString(raw.persona_name),
    scenario_objective: asNonEmptyString(raw.scenario_objective),
  };
}

// Preferred order: run-created snapshot first, judge-enqueue payload second.
export function extractAiContextFromRunEvents(events: RunEvent[] | undefined): RunAiContext | null {
  if (!events || events.length === 0) {
    return null;
  }
  const byType = new Map<string, RunAiContext>();
  for (const event of events) {
    if (!event || typeof event !== "object") {
      continue;
    }
    const eventType = asNonEmptyString(event.type);
    if (!eventType) {
      continue;
    }
    const detail = event.detail;
    if (!detail || typeof detail !== "object") {
      continue;
    }
    const context = parseAiContext((detail as Record<string, unknown>).ai_context);
    if (!context) {
      continue;
    }
    byType.set(eventType, context);
  }
  return byType.get("run_created") ?? byType.get("run_judge_enqueued") ?? null;
}
