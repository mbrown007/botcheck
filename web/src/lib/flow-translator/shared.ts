import YAML from "yaml";
import type { BuilderTurn } from "@/lib/builder-types";
import { isDefaultDecisionSlot } from "@/lib/decision-slots";

import { KNOWN_TOP_LEVEL_FIELDS } from "./constants";
import type { BuilderEdge, FlowMeta } from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function cloneObject<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function normalizeTurnId(turn: BuilderTurn, index: number): string {
  if (typeof turn.id === "string" && turn.id.trim()) {
    return turn.id.trim();
  }
  return `turn_${index + 1}`;
}

export function parseScenarioYaml(yaml: string): Record<string, unknown> {
  const parsed = YAML.parse(yaml);
  if (!isRecord(parsed)) {
    throw new Error("Scenario YAML must be a mapping at the top level.");
  }
  return parsed;
}

// Normalize turns that were written before the Phase A block-kind migration.
// The builder-internal path now requires turn.kind; this function promotes
// legacy flat-field turns to canonical { kind, content, listen } shape at
// the YAML parse boundary so nothing downstream needs to handle legacy shapes.
function normalizeLegacyTurn(raw: Record<string, unknown>): Record<string, unknown> {
  if (typeof raw.kind === "string") return raw; // already canonical

  // Legacy hangup marker: { builder_block: "hangup", ... }
  const out = { ...raw };
  if (raw.builder_block === "hangup") {
    delete out.builder_block;
    delete out.speaker;
    delete out.text;
    delete out.audio_file;
    delete out.silence_s;
    delete out.dtmf;
    delete out.wait_for_response;
    out.kind = "hangup";
    return out;
  }

  // Legacy bot turn: { speaker: "bot", ... }
  if (raw.speaker === "bot") {
    delete out.speaker;
    delete out.text;
    delete out.audio_file;
    delete out.silence_s;
    delete out.dtmf;
    delete out.wait_for_response;
    delete out.builder_block;
    out.kind = "bot_listen";
    return out;
  }

  // Legacy harness turn: { speaker: "harness", text: "...", wait_for_response: bool, ... }
  const content: Record<string, unknown> = {};
  if (typeof raw.text === "string" && raw.text) content.text = raw.text;
  if (typeof raw.audio_file === "string" && raw.audio_file) content.audio_file = raw.audio_file;
  if (typeof raw.silence_s === "number") content.silence_s = raw.silence_s;
  if (typeof raw.dtmf === "string" && raw.dtmf) content.dtmf = raw.dtmf;
  delete out.speaker;
  delete out.text;
  delete out.audio_file;
  delete out.silence_s;
  delete out.dtmf;
  delete out.wait_for_response;
  delete out.builder_block;
  out.kind = "harness_prompt";
  out.content = content;
  out.listen = raw.wait_for_response !== false;
  return out;
}

export function parseTurns(value: unknown): BuilderTurn[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((turn): turn is Record<string, unknown> => isRecord(turn))
    .map((turn) => normalizeLegacyTurn({ ...turn }) as BuilderTurn);
}

export function extractMetaFields(scenario: Record<string, unknown>): FlowMeta {
  const meta: FlowMeta = {};
  const unknownOrder: string[] = [];

  for (const [key, value] of Object.entries(scenario)) {
    if (key === "turns") {
      continue;
    }
    meta[key] = cloneObject(value);
    if (!KNOWN_TOP_LEVEL_FIELDS.includes(key as (typeof KNOWN_TOP_LEVEL_FIELDS)[number])) {
      unknownOrder.push(key);
    }
  }

  if (unknownOrder.length > 0) {
    meta.__unknownTopLevelKeyOrder = unknownOrder;
  }

  return meta;
}

export function edgeCondition(edge: BuilderEdge): string | undefined {
  if (typeof edge.data?.condition === "string") {
    return edge.data.condition.trim();
  }
  if (typeof edge.label === "string") {
    return edge.label.trim();
  }
  return undefined;
}

export function isDefaultCondition(condition: string | undefined): boolean {
  return isDefaultDecisionSlot(condition);
}
