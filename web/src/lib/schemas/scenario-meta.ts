import { z } from "zod";
import type {
  BotProtocol,
  ScenarioPersona,
  ScenarioType,
  ScoringDimension,
} from "@/lib/api";
import type { FlowMeta } from "@/lib/flow-translator";
import {
  optionalNonNegativeIntegerStringSchema,
  optionalNonNegativeNumberStringSchema,
  optionalPositiveIntegerStringSchema,
  optionalPositiveNumberStringSchema,
} from "@/lib/schemas/numeric-string";

export const SCENARIO_TYPE_OPTIONS = [
  "golden_path",
  "robustness",
  "adversarial",
  "compliance",
  "reliability",
] as const satisfies readonly ScenarioType[];

const scenarioTypeSchema = z.enum(SCENARIO_TYPE_OPTIONS);

export const BOT_PROTOCOL_OPTIONS = [
  "sip",
  "webrtc",
  "mock",
] as const satisfies readonly BotProtocol[];

export const PERSONA_MOOD_OPTIONS = [
  "neutral",
  "happy",
  "angry",
  "frustrated",
  "impatient",
] as const satisfies readonly ScenarioPersona["mood"][];

export const RESPONSE_STYLE_OPTIONS = [
  "formal",
  "casual",
  "curt",
  "verbose",
] as const satisfies readonly ScenarioPersona["response_style"][];

const botProtocolSchema = z.enum(BOT_PROTOCOL_OPTIONS);
const personaMoodSchema = z.enum(PERSONA_MOOD_OPTIONS);
const responseStyleSchema = z.enum(RESPONSE_STYLE_OPTIONS);

export const SCORING_DIMENSION_OPTIONS = [
  "routing",
  "policy",
  "jailbreak",
  "disclosure",
  "pii_handling",
  "reliability",
  "role_integrity",
] as const satisfies readonly ScoringDimension[];

const scoringDimensionSchema = z.enum(SCORING_DIMENSION_OPTIONS);

const scoringRubricEntrySchema = z.object({
  dimension: scoringDimensionSchema,
  threshold: z.number().min(0).max(1),
  weight: z.number().min(0).max(1),
  gate: z.boolean(),
  custom_prompt: z.string(),
});

export type ScoringRubricFormEntry = z.infer<typeof scoringRubricEntrySchema>;

export const scenarioMetaFormSchema = z.object({
  name: z.string(),
  id: z.string(),
  namespace: z.string(),
  type: scenarioTypeSchema,
  description: z.string(),
  version: z.string(),
  tags_csv: z.string(),
  max_total_turns: optionalPositiveIntegerStringSchema,
  turn_timeout_s: optionalPositiveIntegerStringSchema,
  max_duration_s: optionalPositiveNumberStringSchema,
  bot_join_timeout_s: optionalPositiveNumberStringSchema,
  transfer_timeout_s: optionalPositiveNumberStringSchema,
  initial_drain_s: optionalNonNegativeNumberStringSchema,
  inter_turn_pause_s: optionalNonNegativeNumberStringSchema,
  transcript_merge_window_s: optionalPositiveNumberStringSchema,
  pause_threshold_ms: optionalNonNegativeIntegerStringSchema,
  stt_endpointing_ms: optionalNonNegativeIntegerStringSchema,
  language: z.string(),
  stt_provider: z.string(),
  stt_model: z.string(),
  tts_voice: z.string(),
  bot_endpoint: z.string(),
  bot_protocol: botProtocolSchema,
  bot_trunk_id: z.string(),
  bot_caller_id: z.string(),
  bot_headers_text: z.string(),
  persona_mood: personaMoodSchema,
  persona_response_style: responseStyleSchema,
  timing_gate_p95_response_gap_ms: optionalNonNegativeIntegerStringSchema,
  timing_warn_p95_response_gap_ms: optionalNonNegativeIntegerStringSchema,
  timing_gate_interruptions_count: optionalNonNegativeIntegerStringSchema,
  timing_warn_interruptions_count: optionalNonNegativeIntegerStringSchema,
  timing_gate_long_pause_count: optionalNonNegativeIntegerStringSchema,
  timing_warn_long_pause_count: optionalNonNegativeIntegerStringSchema,
  timing_gate_interruption_recovery_pct: optionalNonNegativeNumberStringSchema,
  timing_warn_interruption_recovery_pct: optionalNonNegativeNumberStringSchema,
  timing_gate_turn_taking_efficiency_pct: optionalNonNegativeNumberStringSchema,
  timing_warn_turn_taking_efficiency_pct: optionalNonNegativeNumberStringSchema,
  scoring_overall_gate: z.boolean(),
  scoring_rubric: z.array(scoringRubricEntrySchema),
});

export type ScenarioMetaFormValues = z.infer<typeof scenarioMetaFormSchema>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readString(meta: FlowMeta, key: keyof FlowMeta): string {
  const value = meta[key];
  return typeof value === "string" ? value : "";
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
  return Math.max(1, Math.trunc(parsed));
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

function parseTagsCsv(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

function formatBotHeaders(headers: unknown): string {
  if (!isRecord(headers)) {
    return "";
  }
  return Object.entries(headers)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}

function parseBotHeadersText(value: string): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const line of value.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const separatorIndex = trimmed.indexOf(":");
    if (separatorIndex <= 0) {
      headers[trimmed] = "";
      continue;
    }
    const key = trimmed.slice(0, separatorIndex).trim();
    const headerValue = trimmed.slice(separatorIndex + 1).trim();
    if (!key) {
      continue;
    }
    headers[key] = headerValue;
  }
  return headers;
}

function readStringFromRecord(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function parseRecordStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function parseScoringRubricRows(value: unknown): ScoringRubricFormEntry[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows: ScoringRubricFormEntry[] = [];
  for (const row of value) {
    const normalizedRow =
      row && typeof row === "object" && !Array.isArray(row)
        ? {
            ...row,
            custom_prompt:
              typeof (row as { custom_prompt?: unknown }).custom_prompt === "string"
                ? (row as { custom_prompt: string }).custom_prompt
                : "",
          }
        : row;
    const parsed = scoringRubricEntrySchema.safeParse(normalizedRow);
    if (!parsed.success) {
      continue;
    }
    rows.push(parsed.data);
  }
  return rows;
}

export function metaToFormValues(meta: FlowMeta): ScenarioMetaFormValues {
  const config = isRecord(meta.config) ? { ...meta.config } : {};
  const scenarioType = readString(meta, "type");
  const tags = parseRecordStringArray(meta.tags);
  const bot = isRecord(meta.bot) ? { ...meta.bot } : {};
  const persona = isRecord(meta.persona) ? { ...meta.persona } : {};
  const scoring = isRecord(meta.scoring) ? { ...meta.scoring } : {};
  const scoringRubric = parseScoringRubricRows(scoring.rubric);
  const botProtocol = readStringFromRecord(bot, "protocol");
  const personaMood = readStringFromRecord(persona, "mood");
  const personaResponseStyle = readStringFromRecord(persona, "response_style");
  const scoringOverallGate = scoring.overall_gate;

  return {
    name: readString(meta, "name"),
    id: readString(meta, "id"),
    namespace: readString(meta, "namespace"),
    type: scenarioTypeSchema.safeParse(scenarioType).success
      ? (scenarioType as ScenarioType)
      : "reliability",
    description: readString(meta, "description"),
    version: readString(meta, "version"),
    tags_csv: tags.join(", "),
    max_total_turns: readConfigInt(config, "max_total_turns"),
    turn_timeout_s: readConfigInt(config, "turn_timeout_s"),
    max_duration_s: readConfigNumber(config, "max_duration_s"),
    bot_join_timeout_s: readConfigNumber(config, "bot_join_timeout_s"),
    transfer_timeout_s: readConfigNumber(config, "transfer_timeout_s"),
    initial_drain_s: readConfigNumber(config, "initial_drain_s"),
    inter_turn_pause_s: readConfigNumber(config, "inter_turn_pause_s"),
    transcript_merge_window_s: readConfigNumber(config, "transcript_merge_window_s"),
    pause_threshold_ms: readConfigInt(config, "pause_threshold_ms"),
    stt_endpointing_ms: readConfigInt(config, "stt_endpointing_ms"),
    language: readStringFromRecord(config, "language"),
    stt_provider: readStringFromRecord(config, "stt_provider"),
    stt_model: readStringFromRecord(config, "stt_model"),
    tts_voice: readStringFromRecord(config, "tts_voice"),
    bot_endpoint: readStringFromRecord(bot, "endpoint"),
    bot_protocol: botProtocolSchema.safeParse(botProtocol).success
      ? (botProtocol as BotProtocol)
      : "sip",
    bot_trunk_id: readStringFromRecord(bot, "trunk_id"),
    bot_caller_id: readStringFromRecord(bot, "caller_id"),
    bot_headers_text: formatBotHeaders(bot.headers),
    persona_mood: personaMoodSchema.safeParse(personaMood).success
      ? (personaMood as ScenarioPersona["mood"])
      : "neutral",
    persona_response_style: responseStyleSchema.safeParse(personaResponseStyle).success
      ? (personaResponseStyle as ScenarioPersona["response_style"])
      : "casual",
    timing_gate_p95_response_gap_ms: readConfigInt(config, "timing_gate_p95_response_gap_ms"),
    timing_warn_p95_response_gap_ms: readConfigInt(config, "timing_warn_p95_response_gap_ms"),
    timing_gate_interruptions_count: readConfigInt(config, "timing_gate_interruptions_count"),
    timing_warn_interruptions_count: readConfigInt(config, "timing_warn_interruptions_count"),
    timing_gate_long_pause_count: readConfigInt(config, "timing_gate_long_pause_count"),
    timing_warn_long_pause_count: readConfigInt(config, "timing_warn_long_pause_count"),
    timing_gate_interruption_recovery_pct: readConfigNumber(
      config,
      "timing_gate_interruption_recovery_pct"
    ),
    timing_warn_interruption_recovery_pct: readConfigNumber(
      config,
      "timing_warn_interruption_recovery_pct"
    ),
    timing_gate_turn_taking_efficiency_pct: readConfigNumber(
      config,
      "timing_gate_turn_taking_efficiency_pct"
    ),
    timing_warn_turn_taking_efficiency_pct: readConfigNumber(
      config,
      "timing_warn_turn_taking_efficiency_pct"
    ),
    scoring_overall_gate:
      typeof scoringOverallGate === "boolean" ? scoringOverallGate : true,
    scoring_rubric: scoringRubric,
  };
}

export function mergeFormValuesIntoMeta(
  meta: FlowMeta,
  values: ScenarioMetaFormValues
): FlowMeta {
  const nextMeta: FlowMeta = {
    ...meta,
    name: values.name,
    id: values.id,
    namespace: undefined,
    type: values.type,
    description: values.description,
    version: values.version,
  };

  const namespace = values.namespace.trim().replace(/^\/+|\/+$/g, "");
  if (namespace) {
    nextMeta.namespace = namespace;
  } else {
    delete nextMeta.namespace;
  }

  const currentConfig = isRecord(meta.config) ? meta.config : null;
  const nextConfig = currentConfig ? { ...currentConfig } : {};

  const maxTotalTurns = parseOptionalInt(values.max_total_turns);
  if (maxTotalTurns === null) {
    delete nextConfig.max_total_turns;
  } else {
    nextConfig.max_total_turns = maxTotalTurns;
  }

  const turnTimeout = parseOptionalInt(values.turn_timeout_s);
  if (turnTimeout === null) {
    delete nextConfig.turn_timeout_s;
  } else {
    nextConfig.turn_timeout_s = turnTimeout;
  }

  const maxDuration = parseOptionalFloat(values.max_duration_s);
  if (maxDuration === null) {
    delete nextConfig.max_duration_s;
  } else {
    nextConfig.max_duration_s = maxDuration;
  }

  const botJoinTimeout = parseOptionalFloat(values.bot_join_timeout_s);
  if (botJoinTimeout === null) {
    delete nextConfig.bot_join_timeout_s;
  } else {
    nextConfig.bot_join_timeout_s = botJoinTimeout;
  }

  const transferTimeout = parseOptionalFloat(values.transfer_timeout_s);
  if (transferTimeout === null) {
    delete nextConfig.transfer_timeout_s;
  } else {
    nextConfig.transfer_timeout_s = transferTimeout;
  }

  const initialDrain = parseOptionalFloat(values.initial_drain_s);
  if (initialDrain === null) {
    delete nextConfig.initial_drain_s;
  } else {
    nextConfig.initial_drain_s = initialDrain;
  }

  const interTurnPause = parseOptionalFloat(values.inter_turn_pause_s);
  if (interTurnPause === null) {
    delete nextConfig.inter_turn_pause_s;
  } else {
    nextConfig.inter_turn_pause_s = interTurnPause;
  }

  const transcriptMergeWindow = parseOptionalFloat(values.transcript_merge_window_s);
  if (transcriptMergeWindow === null) {
    delete nextConfig.transcript_merge_window_s;
  } else {
    nextConfig.transcript_merge_window_s = transcriptMergeWindow;
  }

  const pauseThresholdMs = parseOptionalInt(values.pause_threshold_ms);
  if (pauseThresholdMs === null) {
    delete nextConfig.pause_threshold_ms;
  } else {
    nextConfig.pause_threshold_ms = pauseThresholdMs;
  }

  const sttEndpointingMs = parseOptionalInt(values.stt_endpointing_ms);
  if (sttEndpointingMs === null) {
    delete nextConfig.stt_endpointing_ms;
  } else {
    nextConfig.stt_endpointing_ms = sttEndpointingMs;
  }

  const timingGateP95ResponseGapMs = parseOptionalInt(values.timing_gate_p95_response_gap_ms);
  if (timingGateP95ResponseGapMs === null) {
    delete nextConfig.timing_gate_p95_response_gap_ms;
  } else {
    nextConfig.timing_gate_p95_response_gap_ms = timingGateP95ResponseGapMs;
  }

  const timingWarnP95ResponseGapMs = parseOptionalInt(values.timing_warn_p95_response_gap_ms);
  if (timingWarnP95ResponseGapMs === null) {
    delete nextConfig.timing_warn_p95_response_gap_ms;
  } else {
    nextConfig.timing_warn_p95_response_gap_ms = timingWarnP95ResponseGapMs;
  }

  const timingGateInterruptionsCount = parseOptionalInt(
    values.timing_gate_interruptions_count
  );
  if (timingGateInterruptionsCount === null) {
    delete nextConfig.timing_gate_interruptions_count;
  } else {
    nextConfig.timing_gate_interruptions_count = timingGateInterruptionsCount;
  }

  const timingWarnInterruptionsCount = parseOptionalInt(
    values.timing_warn_interruptions_count
  );
  if (timingWarnInterruptionsCount === null) {
    delete nextConfig.timing_warn_interruptions_count;
  } else {
    nextConfig.timing_warn_interruptions_count = timingWarnInterruptionsCount;
  }

  const timingGateLongPauseCount = parseOptionalInt(values.timing_gate_long_pause_count);
  if (timingGateLongPauseCount === null) {
    delete nextConfig.timing_gate_long_pause_count;
  } else {
    nextConfig.timing_gate_long_pause_count = timingGateLongPauseCount;
  }

  const timingWarnLongPauseCount = parseOptionalInt(values.timing_warn_long_pause_count);
  if (timingWarnLongPauseCount === null) {
    delete nextConfig.timing_warn_long_pause_count;
  } else {
    nextConfig.timing_warn_long_pause_count = timingWarnLongPauseCount;
  }

  const timingGateInterruptionRecoveryPct = parseOptionalFloat(
    values.timing_gate_interruption_recovery_pct
  );
  if (timingGateInterruptionRecoveryPct === null) {
    delete nextConfig.timing_gate_interruption_recovery_pct;
  } else {
    nextConfig.timing_gate_interruption_recovery_pct = timingGateInterruptionRecoveryPct;
  }

  const timingWarnInterruptionRecoveryPct = parseOptionalFloat(
    values.timing_warn_interruption_recovery_pct
  );
  if (timingWarnInterruptionRecoveryPct === null) {
    delete nextConfig.timing_warn_interruption_recovery_pct;
  } else {
    nextConfig.timing_warn_interruption_recovery_pct = timingWarnInterruptionRecoveryPct;
  }

  const timingGateTurnTakingEfficiencyPct = parseOptionalFloat(
    values.timing_gate_turn_taking_efficiency_pct
  );
  if (timingGateTurnTakingEfficiencyPct === null) {
    delete nextConfig.timing_gate_turn_taking_efficiency_pct;
  } else {
    nextConfig.timing_gate_turn_taking_efficiency_pct = timingGateTurnTakingEfficiencyPct;
  }

  const timingWarnTurnTakingEfficiencyPct = parseOptionalFloat(
    values.timing_warn_turn_taking_efficiency_pct
  );
  if (timingWarnTurnTakingEfficiencyPct === null) {
    delete nextConfig.timing_warn_turn_taking_efficiency_pct;
  } else {
    nextConfig.timing_warn_turn_taking_efficiency_pct = timingWarnTurnTakingEfficiencyPct;
  }

  const language = values.language.trim();
  if (language) {
    nextConfig.language = language;
  } else {
    delete nextConfig.language;
  }

  const sttProvider = values.stt_provider.trim();
  if (sttProvider) {
    nextConfig.stt_provider = sttProvider;
  } else {
    delete nextConfig.stt_provider;
  }

  const sttModel = values.stt_model.trim();
  if (sttModel) {
    nextConfig.stt_model = sttModel;
  } else {
    delete nextConfig.stt_model;
  }

  const ttsVoice = values.tts_voice.trim();
  if (ttsVoice) {
    nextConfig.tts_voice = ttsVoice;
  } else {
    delete nextConfig.tts_voice;
  }

  if (Object.keys(nextConfig).length > 0) {
    nextMeta.config = nextConfig;
  } else {
    delete nextMeta.config;
  }

  const tags = parseTagsCsv(values.tags_csv);
  if (tags.length > 0) {
    nextMeta.tags = tags;
  } else {
    delete nextMeta.tags;
  }

  const currentBot = isRecord(meta.bot) ? meta.bot : null;
  const nextBot = currentBot ? { ...currentBot } : {};
  const botEndpoint = values.bot_endpoint.trim();
  const botTrunkId = values.bot_trunk_id.trim();
  const botCallerId = values.bot_caller_id.trim();
  const botHeaders = parseBotHeadersText(values.bot_headers_text);
  const shouldPersistBot =
    currentBot !== null ||
    botEndpoint.length > 0 ||
    botTrunkId.length > 0 ||
    botCallerId.length > 0 ||
    Object.keys(botHeaders).length > 0 ||
    values.bot_protocol !== "sip";
  if (shouldPersistBot) {
    nextBot.protocol = values.bot_protocol;
    nextBot.endpoint = botEndpoint;
    if (botTrunkId) {
      nextBot.trunk_id = botTrunkId;
    } else {
      delete nextBot.trunk_id;
    }
    if (botCallerId) {
      nextBot.caller_id = botCallerId;
    } else {
      delete nextBot.caller_id;
    }
    if (Object.keys(botHeaders).length > 0) {
      nextBot.headers = botHeaders;
    } else {
      delete nextBot.headers;
    }
    nextMeta.bot = nextBot;
  } else {
    delete nextMeta.bot;
  }

  const currentPersona = isRecord(meta.persona) ? meta.persona : null;
  const nextPersona = currentPersona ? { ...currentPersona } : {};
  const shouldPersistPersona =
    currentPersona !== null ||
    values.persona_mood !== "neutral" ||
    values.persona_response_style !== "casual";
  if (shouldPersistPersona) {
    nextPersona.mood = values.persona_mood;
    nextPersona.response_style = values.persona_response_style;
    nextMeta.persona = nextPersona;
  } else {
    delete nextMeta.persona;
  }

  const currentScoring = isRecord(meta.scoring) ? meta.scoring : null;
  const nextScoring = currentScoring ? { ...currentScoring } : {};
  const shouldPersistScoring =
    currentScoring !== null ||
    values.scoring_overall_gate !== true ||
    values.scoring_rubric.length > 0;
  if (shouldPersistScoring) {
    nextScoring.overall_gate = values.scoring_overall_gate;
    if (values.scoring_rubric.length > 0) {
      nextScoring.rubric = values.scoring_rubric.map((row) => {
        const customPrompt = row.custom_prompt.trim();
        return customPrompt
          ? { ...row, custom_prompt: customPrompt }
          : {
              dimension: row.dimension,
              threshold: row.threshold,
              weight: row.weight,
              gate: row.gate,
            };
      });
    } else {
      delete nextScoring.rubric;
    }
    nextMeta.scoring = nextScoring;
  } else {
    delete nextMeta.scoring;
  }

  return nextMeta;
}

export function areMetaFormValuesEqual(
  left: ScenarioMetaFormValues,
  right: ScenarioMetaFormValues
): boolean {
  const scoringRubricEqual =
    left.scoring_rubric.length === right.scoring_rubric.length &&
    left.scoring_rubric.every((row, index) => {
      const match = right.scoring_rubric[index];
      return (
        match !== undefined &&
        row.dimension === match.dimension &&
        row.threshold === match.threshold &&
        row.weight === match.weight &&
        row.gate === match.gate &&
        row.custom_prompt === match.custom_prompt
      );
    });

  return (
    left.name === right.name &&
    left.id === right.id &&
    left.namespace === right.namespace &&
    left.type === right.type &&
    left.description === right.description &&
    left.version === right.version &&
    left.tags_csv === right.tags_csv &&
    left.max_total_turns === right.max_total_turns &&
    left.turn_timeout_s === right.turn_timeout_s &&
    left.max_duration_s === right.max_duration_s &&
    left.bot_join_timeout_s === right.bot_join_timeout_s &&
    left.transfer_timeout_s === right.transfer_timeout_s &&
    left.initial_drain_s === right.initial_drain_s &&
    left.inter_turn_pause_s === right.inter_turn_pause_s &&
    left.transcript_merge_window_s === right.transcript_merge_window_s &&
    left.pause_threshold_ms === right.pause_threshold_ms &&
    left.stt_endpointing_ms === right.stt_endpointing_ms &&
    left.language === right.language &&
    left.stt_provider === right.stt_provider &&
    left.stt_model === right.stt_model &&
    left.tts_voice === right.tts_voice &&
    left.bot_endpoint === right.bot_endpoint &&
    left.bot_protocol === right.bot_protocol &&
    left.bot_trunk_id === right.bot_trunk_id &&
    left.bot_caller_id === right.bot_caller_id &&
    left.bot_headers_text === right.bot_headers_text &&
    left.persona_mood === right.persona_mood &&
    left.persona_response_style === right.persona_response_style &&
    left.timing_gate_p95_response_gap_ms === right.timing_gate_p95_response_gap_ms &&
    left.timing_warn_p95_response_gap_ms === right.timing_warn_p95_response_gap_ms &&
    left.timing_gate_interruptions_count === right.timing_gate_interruptions_count &&
    left.timing_warn_interruptions_count === right.timing_warn_interruptions_count &&
    left.timing_gate_long_pause_count === right.timing_gate_long_pause_count &&
    left.timing_warn_long_pause_count === right.timing_warn_long_pause_count &&
    left.timing_gate_interruption_recovery_pct ===
      right.timing_gate_interruption_recovery_pct &&
    left.timing_warn_interruption_recovery_pct ===
      right.timing_warn_interruption_recovery_pct &&
    left.timing_gate_turn_taking_efficiency_pct ===
      right.timing_gate_turn_taking_efficiency_pct &&
    left.timing_warn_turn_taking_efficiency_pct ===
      right.timing_warn_turn_taking_efficiency_pct &&
    left.scoring_overall_gate === right.scoring_overall_gate &&
    scoringRubricEqual
  );
}
