import type { ScenarioTurn } from "@/lib/api/types";
import type { BuilderPromptContent } from "@/lib/builder-types";

export type ScenarioBlockKind =
  | "harness_prompt"
  | "bot_listen"
  | "hangup"
  | "wait"
  | "time_route";

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function getScenarioPromptContent(turn: ScenarioTurn): BuilderPromptContent {
  if (turn.kind !== "harness_prompt") {
    return {};
  }
  const content = asRecord(turn.content);
  return {
    text: typeof content?.text === "string" ? content.text : undefined,
    audio_file: typeof content?.audio_file === "string" ? content.audio_file : undefined,
    silence_s: typeof content?.silence_s === "number" ? content.silence_s : undefined,
    dtmf: typeof content?.dtmf === "string" ? content.dtmf : undefined,
  };
}

export function getScenarioTurnKind(turn: ScenarioTurn): ScenarioBlockKind {
  return turn.kind;
}

export function getScenarioTurnSpeaker(turn: ScenarioTurn): "harness" | "bot" {
  return getScenarioTurnKind(turn) === "bot_listen" ? "bot" : "harness";
}

export function getScenarioTurnText(turn: ScenarioTurn): string {
  return getScenarioPromptContent(turn).text ?? "";
}

export function getScenarioTurnAudioFile(turn: ScenarioTurn): string | undefined {
  return getScenarioPromptContent(turn).audio_file;
}

export function getScenarioTurnSilenceS(turn: ScenarioTurn): number | undefined {
  return getScenarioPromptContent(turn).silence_s;
}

export function getScenarioTurnDtmf(turn: ScenarioTurn): string | undefined {
  return getScenarioPromptContent(turn).dtmf;
}

export function getScenarioTurnListen(turn: ScenarioTurn): boolean {
  const kind = getScenarioTurnKind(turn);
  if (kind === "bot_listen") {
    return true;
  }
  if (kind === "hangup" || kind === "wait" || kind === "time_route") {
    return false;
  }
  return turn.listen !== false;
}
