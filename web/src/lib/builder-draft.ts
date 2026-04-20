import YAML from "yaml";

const COPY_SUFFIX = "-copy";

function normalizeCopyBaseId(sourceId: string): string {
  const trimmed = sourceId.trim();
  if (!trimmed) {
    return "scenario";
  }
  return trimmed.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/-+/g, "-");
}

export function nextCopyScenarioId(
  sourceId: string,
  existingIds: Iterable<string>
): string {
  const taken = new Set(Array.from(existingIds));
  const base = `${normalizeCopyBaseId(sourceId)}${COPY_SUFFIX}`;
  if (!taken.has(base)) {
    return base;
  }
  let index = 2;
  while (taken.has(`${base}-${index}`)) {
    index += 1;
  }
  return `${base}-${index}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Scenario YAML must be a top-level mapping.");
  }
  return value as Record<string, unknown>;
}

export function createCopiedScenarioYaml(
  sourceYaml: string,
  existingIds: Iterable<string>
): { yaml: string; copiedId: string } {
  const parsed = asRecord(YAML.parse(sourceYaml));
  const sourceId =
    typeof parsed.id === "string" && parsed.id.trim() ? parsed.id.trim() : "scenario";
  const copiedId = nextCopyScenarioId(sourceId, existingIds);

  parsed.id = copiedId;
  if (typeof parsed.name === "string" && parsed.name.trim()) {
    parsed.name = `${parsed.name.trim()} (copy)`;
  } else {
    parsed.name = copiedId;
  }

  return {
    yaml: YAML.stringify(parsed, { lineWidth: 0 }),
    copiedId,
  };
}

