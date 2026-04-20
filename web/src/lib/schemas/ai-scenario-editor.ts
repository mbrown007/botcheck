import { z } from "zod";
import type {
  AIScenarioDetail,
  AIScenarioRecordUpsertRequest,
  AIScenarioSummary,
  AIScenarioUpsertRequest,
} from "@/lib/api";
import { parseAiScenarioFactsText } from "@/lib/ai-scenario-authoring";
import {
  optionalNonNegativeIntegerStringSchema,
  optionalPositiveIntegerStringSchema,
  optionalPositiveNumberStringSchema,
} from "@/lib/schemas/numeric-string";

const aiScenarioOpeningStrategySchema = z.enum([
  "wait_for_bot_greeting",
  "caller_opens",
]);

export const aiScenarioEditorFormSchema = z.object({
  name: z.string().trim().min(1, "Scenario name is required.").max(255),
  publicId: z.string().trim().max(255),
  namespace: z.string().max(255),
  personaId: z.string().trim().min(1, "Persona is required.").max(255),
  scenarioBrief: z.string().trim().min(1, "Scenario brief is required.").max(12000),
  scenarioFactsText: z
    .string()
    .max(12000)
    .superRefine((value, ctx) => {
      if (!value.trim()) {
        return;
      }
      try {
        parseAiScenarioFactsText(value);
      } catch (error) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: error instanceof Error ? error.message : "Scenario facts must be valid JSON.",
        });
      }
    }),
  evaluationObjective: z
    .string()
    .trim()
    .min(1, "Evaluation objective is required.")
    .max(12000),
  openingStrategy: aiScenarioOpeningStrategySchema,
  datasetSource: z.string().max(255),
  scoringProfile: z.string().max(255),
  tts_voice: z.string().max(255),
  stt_provider: z.string().max(255),
  stt_model: z.string().max(255),
  language: z.string().max(64),
  stt_endpointing_ms: optionalNonNegativeIntegerStringSchema,
  transcript_merge_window_s: optionalPositiveNumberStringSchema,
  turn_timeout_s: optionalPositiveNumberStringSchema,
  max_duration_s: optionalPositiveNumberStringSchema,
  max_total_turns: optionalPositiveIntegerStringSchema,
});

export type AIScenarioEditorFormValues = z.infer<typeof aiScenarioEditorFormSchema>;

export function createEmptyAIScenarioEditorValues(): AIScenarioEditorFormValues {
  return {
    name: "",
    publicId: "",
    namespace: "",
    personaId: "",
    scenarioBrief: "",
    scenarioFactsText: "",
    evaluationObjective: "",
    openingStrategy: "wait_for_bot_greeting",
    datasetSource: "",
    scoringProfile: "",
    tts_voice: "",
    stt_provider: "",
    stt_model: "",
    language: "",
    stt_endpointing_ms: "",
    transcript_merge_window_s: "",
    turn_timeout_s: "",
    max_duration_s: "",
    max_total_turns: "",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readConfigInt(config: Record<string, unknown>, key: string): string {
  const value = config[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "";
  }
  return String(Math.trunc(value));
}

function readConfigNumber(config: Record<string, unknown>, key: string): string {
  const value = config[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "";
  }
  return Number.isInteger(value) ? String(Math.trunc(value)) : String(value);
}

function parseOptionalInt(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.trunc(parsed);
}

function parseOptionalFloat(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number.parseFloat(trimmed);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function buildAIScenarioRuntimeConfig(
  values: AIScenarioEditorFormValues
): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  const ttsVoice = values.tts_voice.trim();
  if (ttsVoice) {
    config.tts_voice = ttsVoice;
  }

  const sttProvider = values.stt_provider.trim().toLowerCase();
  if (sttProvider) {
    config.stt_provider = sttProvider;
  }

  const sttModel = values.stt_model.trim();
  if (sttModel) {
    config.stt_model = sttModel;
  }

  const language = values.language.trim();
  if (language) {
    config.language = language;
  }

  const sttEndpointingMs = parseOptionalInt(values.stt_endpointing_ms);
  if (sttEndpointingMs !== null) {
    config.stt_endpointing_ms = sttEndpointingMs;
  }

  const transcriptMergeWindow = parseOptionalFloat(values.transcript_merge_window_s);
  if (transcriptMergeWindow !== null) {
    config.transcript_merge_window_s = transcriptMergeWindow;
  }

  const turnTimeout = parseOptionalFloat(values.turn_timeout_s);
  if (turnTimeout !== null) {
    config.turn_timeout_s = turnTimeout;
  }

  const maxDuration = parseOptionalFloat(values.max_duration_s);
  if (maxDuration !== null) {
    config.max_duration_s = maxDuration;
  }

  const maxTotalTurns = parseOptionalInt(values.max_total_turns);
  if (maxTotalTurns !== null) {
    config.max_total_turns = maxTotalTurns;
  }

  return config;
}

export function aiScenarioFormValuesToPayload(
  values: AIScenarioEditorFormValues
): Omit<AIScenarioUpsertRequest, "scenario_id"> {
  return {
    ai_scenario_id: values.publicId.trim() || undefined,
    namespace: values.namespace.trim().replace(/^\/+|\/+$/g, "") || undefined,
    persona_id: values.personaId.trim(),
    name: values.name.trim(),
    scenario_brief: values.scenarioBrief.trim(),
    scenario_facts: parseAiScenarioFactsText(values.scenarioFactsText),
    evaluation_objective: values.evaluationObjective.trim(),
    opening_strategy: values.openingStrategy,
    is_active: true,
    dataset_source: values.datasetSource.trim() || undefined,
    scoring_profile: values.scoringProfile.trim() || undefined,
    config: buildAIScenarioRuntimeConfig(values),
  };
}

export function aiScenarioToFormValues(
  scenario: Pick<
    AIScenarioSummary,
    | "ai_scenario_id"
    | "name"
    | "namespace"
    | "persona_id"
    | "scenario_brief"
    | "scenario_facts"
    | "evaluation_objective"
    | "opening_strategy"
    | "dataset_source"
    | "scoring_profile"
  > &
    Pick<Partial<AIScenarioDetail>, "config">
): AIScenarioEditorFormValues {
  const config = isRecord(scenario.config) ? scenario.config : {};
  return {
    name: scenario.name ?? "",
    publicId: scenario.ai_scenario_id ?? "",
    namespace: scenario.namespace ?? "",
    personaId: scenario.persona_id ?? "",
    scenarioBrief: scenario.scenario_brief ?? "",
    scenarioFactsText:
      scenario.scenario_facts && Object.keys(scenario.scenario_facts).length > 0
        ? JSON.stringify(scenario.scenario_facts, null, 2)
        : "",
    evaluationObjective: scenario.evaluation_objective ?? "",
    openingStrategy: scenario.opening_strategy ?? "wait_for_bot_greeting",
    datasetSource: scenario.dataset_source ?? "",
    scoringProfile: scenario.scoring_profile ?? "",
    tts_voice: typeof config.tts_voice === "string" ? config.tts_voice : "",
    stt_provider: typeof config.stt_provider === "string" ? config.stt_provider : "",
    stt_model: typeof config.stt_model === "string" ? config.stt_model : "",
    language: typeof config.language === "string" ? config.language : "",
    stt_endpointing_ms: readConfigInt(config, "stt_endpointing_ms"),
    transcript_merge_window_s: readConfigNumber(config, "transcript_merge_window_s"),
    turn_timeout_s: readConfigNumber(config, "turn_timeout_s"),
    max_duration_s: readConfigNumber(config, "max_duration_s"),
    max_total_turns: readConfigInt(config, "max_total_turns"),
  };
}

export const aiScenarioRecordEditorFormSchema = z.object({
  orderIndex: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || (/^\d+$/.test(value) && Number(value) >= 1),
      "Order index must be a positive integer."
    ),
  inputText: z.string().trim().min(1, "Record input is required.").max(12000),
  expectedOutput: z.string().trim().min(1, "Expected output is required.").max(12000),
});

export type AIScenarioRecordEditorFormValues = z.infer<typeof aiScenarioRecordEditorFormSchema>;

export function createEmptyAIScenarioRecordEditorValues(): AIScenarioRecordEditorFormValues {
  return {
    orderIndex: "",
    inputText: "",
    expectedOutput: "",
  };
}

export function aiScenarioRecordFormValuesToPayload(
  values: AIScenarioRecordEditorFormValues
): AIScenarioRecordUpsertRequest {
  const orderIndex = values.orderIndex.trim();
  return {
    order_index: orderIndex ? Number(orderIndex) : undefined,
    input_text: values.inputText.trim(),
    expected_output: values.expectedOutput.trim(),
    metadata: {},
    is_active: true,
  };
}
