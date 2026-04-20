import YAML from "yaml";

function slugifySegment(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "ai-scenario";
}

export function deriveAiScenarioPublicId(
  name: string,
  explicitId?: string | null
): string {
  const source = (explicitId || "").trim() || name.trim();
  return slugifySegment(source);
}

export function buildAiBackingScenarioId(
  aiScenarioId: string,
  randomSuffix?: string
): string {
  const suffix =
    (randomSuffix || globalThis.crypto?.randomUUID?.() || `${Date.now()}`)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "")
      .slice(0, 10) || "runtime";
  return `ai-runtime-${slugifySegment(aiScenarioId)}-${suffix}`;
}

export function parseAiScenarioFactsText(
  text: string
): Record<string, unknown> {
  const trimmed = text.trim();
  if (!trimmed) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error("Structured facts must be valid JSON.");
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Structured facts must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

export function buildAiBackingScenarioYaml(args: {
  scenarioId: string;
  name: string;
  description?: string | null;
}): string {
  const description =
    args.description?.trim() || "Internal backing scenario for AI runtime dispatch.";
  return YAML.stringify({
    version: "1.0",
    id: args.scenarioId,
    name: `${args.name.trim() || args.scenarioId} (AI Runtime)`,
    type: "golden_path",
    description,
    bot: {
      endpoint: "mock://echo",
      protocol: "mock",
    },
    turns: [
      {
        id: "t1",
        kind: "harness_prompt",
        content: {
          text: "AI runtime placeholder turn.",
        },
        listen: false,
      },
    ],
  });
}
