import type {
  AdversarialTechnique,
  ScenarioBranchCase,
  ScenarioBranchConfig,
  ScenarioBranchMode,
  ScenarioPromptContent,
  ScenarioTurnConfig,
  ScenarioTurnExpectation,
} from "@/lib/api";

export type BuilderBlockKind =
  | "harness_prompt"
  | "bot_listen"
  | "hangup"
  | "wait"
  | "time_route";
export type BuilderBranchMode = ScenarioBranchMode;

export interface BuilderPromptContent {
  text?: string;
  audio_file?: string;
  silence_s?: number;
  dtmf?: string;
}

export interface BuilderTimeRouteWindow {
  label?: string;
  start?: string;
  end?: string;
  next?: string;
}

export interface BuilderTurn extends Record<string, unknown> {
  id: string;
  kind: BuilderBlockKind;
  content?: (ScenarioPromptContent & BuilderPromptContent) | BuilderPromptContent;
  listen?: boolean;
  wait_s?: number;
  timezone?: string;
  windows?: BuilderTimeRouteWindow[];
  default?: string;
  next?: string | null;
  branching?: ScenarioBranchConfig | null;
  expect?: ScenarioTurnExpectation | null;
  config?: ScenarioTurnConfig;
  adversarial?: boolean;
  technique?: AdversarialTechnique | null;
  max_visits?: number;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

export function getBuilderTurnKind(turn: BuilderTurn): BuilderBlockKind {
  return turn.kind;
}

export function getBuilderTurnSpeaker(turn: BuilderTurn): "harness" | "bot" {
  return getBuilderTurnKind(turn) === "bot_listen" ? "bot" : "harness";
}

function getBuilderPromptContent(turn: BuilderTurn): BuilderPromptContent {
  const content = asRecord(turn.content);
  return {
    text: typeof content?.text === "string" ? content.text : undefined,
    audio_file: typeof content?.audio_file === "string" ? content.audio_file : undefined,
    silence_s: typeof content?.silence_s === "number" ? content.silence_s : undefined,
    dtmf: typeof content?.dtmf === "string" ? content.dtmf : undefined,
  };
}

export function getBuilderTurnText(turn: BuilderTurn): string {
  return getBuilderPromptContent(turn).text ?? "";
}

export function getBuilderTurnAudioFile(turn: BuilderTurn): string | undefined {
  return getBuilderPromptContent(turn).audio_file;
}

export function getBuilderTurnSilenceS(turn: BuilderTurn): number | undefined {
  return getBuilderPromptContent(turn).silence_s;
}

export function getBuilderTurnDtmf(turn: BuilderTurn): string | undefined {
  return getBuilderPromptContent(turn).dtmf;
}

export function getBuilderTurnListen(turn: BuilderTurn): boolean {
  const kind = getBuilderTurnKind(turn);
  if (kind === "bot_listen") {
    return true;
  }
  if (kind === "hangup" || kind === "wait" || kind === "time_route") {
    return false;
  }
  return turn.listen !== false;
}

export function getBuilderTurnWaitS(turn: BuilderTurn): number | undefined {
  return typeof turn.wait_s === "number" ? turn.wait_s : undefined;
}

export function getBuilderTimeRouteTimezone(turn: BuilderTurn): string | undefined {
  return typeof turn.timezone === "string" ? turn.timezone : undefined;
}

export function getBuilderTimeRouteWindows(turn: BuilderTurn): BuilderTimeRouteWindow[] {
  return Array.isArray(turn.windows)
    ? turn.windows
        .filter((entry): entry is BuilderTimeRouteWindow => Boolean(asRecord(entry)))
        .map((entry) => ({
          label: typeof entry.label === "string" ? entry.label : undefined,
          start: typeof entry.start === "string" ? entry.start : undefined,
          end: typeof entry.end === "string" ? entry.end : undefined,
          next: typeof entry.next === "string" ? entry.next : undefined,
        }))
    : [];
}

export function getBuilderTimeRouteDefault(turn: BuilderTurn): string | undefined {
  return typeof turn.default === "string" ? turn.default : undefined;
}

export function getBuilderTurnBranchMode(turn: BuilderTurn): BuilderBranchMode {
  const mode = turn.branching?.mode;
  if (mode === "keyword" || mode === "regex") {
    return mode;
  }
  return "classifier";
}

export function getBuilderTurnBranchCases(turn: BuilderTurn): ScenarioBranchCase[] {
  return Array.isArray(turn.branching?.cases) ? turn.branching.cases : [];
}

export function toCanonicalBuilderTurn(turn: BuilderTurn): BuilderTurn {
  const kind = getBuilderTurnKind(turn);
  const rest = { ...turn };
  delete rest.content;
  delete rest.listen;

  if (kind === "hangup") {
    return {
      ...rest,
      kind: "hangup",
    };
  }

  if (kind === "wait") {
    return {
      ...rest,
      kind: "wait",
      wait_s: getBuilderTurnWaitS(turn) ?? 1,
    };
  }

  if (kind === "time_route") {
    return {
      ...rest,
      kind: "time_route",
      timezone: getBuilderTimeRouteTimezone(turn) ?? "UTC",
      windows: getBuilderTimeRouteWindows(turn).map((window) => ({
        label: window.label ?? "",
        start: window.start ?? "",
        end: window.end ?? "",
        next: window.next ?? "",
      })),
      default: getBuilderTimeRouteDefault(turn) ?? "",
    };
  }

  if (kind === "bot_listen") {
    return {
      ...rest,
      kind: "bot_listen",
    };
  }

  const content: BuilderPromptContent = {};
  const text = getBuilderTurnText(turn);
  const audioFile = getBuilderTurnAudioFile(turn);
  const silenceS = getBuilderTurnSilenceS(turn);
  const dtmf = getBuilderTurnDtmf(turn);

  if (text) content.text = text;
  if (audioFile) content.audio_file = audioFile;
  if (typeof silenceS === "number") content.silence_s = silenceS;
  if (dtmf) content.dtmf = dtmf;

  return {
    ...rest,
    kind: "harness_prompt",
    content,
    listen: getBuilderTurnListen(turn),
  };
}
