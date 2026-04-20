import type {
  AIScenarioSummary,
  BotDestinationSummary,
  RunResponse,
  ScenarioDefinition,
} from "@/lib/api/types";

export type PlaygroundMode = "mock" | "direct_http";

export const PLAYGROUND_SYSTEM_PROMPT_SOFT_LIMIT = 16000;

export function isPlaygroundCompatibleGraphScenario(
  scenario: ScenarioDefinition
): boolean {
  const kind = String(
    (scenario as unknown as { scenario_kind?: string }).scenario_kind ?? "graph"
  ).toLowerCase();
  if (kind !== "graph") return false;
  const protocol = String(
    (scenario.bot as { protocol?: string } | undefined)?.protocol ?? ""
  ).toLowerCase();
  return protocol === "mock" || protocol === "http";
}

export function isPlaygroundRunActive(run: RunResponse | null | undefined): boolean {
  if (!run) {
    return false;
  }
  return run.state === "pending" || run.state === "running" || run.state === "judging";
}

export function buildPlaygroundGraphOptionLabel(
  scenario: ScenarioDefinition
): string {
  return `${scenario.name} · ${scenario.bot.protocol.toUpperCase()}`;
}

export function buildPlaygroundAIScenarioOptionLabel(
  scenario: AIScenarioSummary
): string {
  return `${scenario.name} · AI`;
}

export function buildHttpTransportOptionLabel(
  destination: BotDestinationSummary
): string {
  const target = destination.default_dial_target ?? destination.endpoint ?? "endpoint";
  return `${destination.name} · ${target}`;
}

export function playgroundPromptSoftLimitWarning(
  prompt: string
): string | null {
  const count = prompt.length;
  if (count <= PLAYGROUND_SYSTEM_PROMPT_SOFT_LIMIT) {
    return null;
  }
  return `System prompt exceeds the ${PLAYGROUND_SYSTEM_PROMPT_SOFT_LIMIT.toLocaleString()} character soft limit.`;
}
