import scenarioDefinitionSchema from "@/lib/generated-schemas/scenario-definition.json";

type JsonSchemaNode = {
  $ref?: string;
  properties?: Record<string, JsonSchemaNode>;
  required?: string[];
  anyOf?: JsonSchemaNode[];
  type?: string;
  default?: unknown;
  enum?: unknown[];
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
};

const ROOT_SCHEMA = scenarioDefinitionSchema as JsonSchemaNode & {
  $defs?: Record<string, JsonSchemaNode>;
};

function resolveSchemaNode(node: JsonSchemaNode | null | undefined): JsonSchemaNode | null {
  if (!node) {
    return null;
  }
  if (!node.$ref) {
    return node;
  }
  const prefix = "#/$defs/";
  if (!node.$ref.startsWith(prefix)) {
    return node;
  }
  return ROOT_SCHEMA.$defs?.[node.$ref.slice(prefix.length)] ?? null;
}

function getSchemaNode(path: string[]): { parent: JsonSchemaNode | null; node: JsonSchemaNode | null } {
  let parent: JsonSchemaNode | null = null;
  let current: JsonSchemaNode | null = ROOT_SCHEMA;
  for (const segment of path) {
    const resolved = resolveSchemaNode(current);
    parent = resolved;
    current = resolved?.properties?.[segment] ?? null;
  }
  return { parent, node: resolveSchemaNode(current) };
}

function extractType(node: JsonSchemaNode | null): string | null {
  if (!node) {
    return null;
  }
  if (typeof node.type === "string") {
    return node.type;
  }
  if (node.anyOf?.length) {
    const types = node.anyOf
      .map((option) => resolveSchemaNode(option))
      .flatMap((option) => (typeof option?.type === "string" && option.type !== "null" ? [option.type] : []));
    return types.length > 0 ? types.join(" | ") : null;
  }
  if (node.enum?.length) {
    return "enum";
  }
  return null;
}

function formatDefault(value: unknown): string | null {
  if (value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return value === "" ? '""' : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function extractEnumValues(node: JsonSchemaNode | null): string[] {
  if (!node?.enum) {
    return [];
  }
  return node.enum.filter((value): value is string => typeof value === "string").slice(0, 5);
}

function extractRange(node: JsonSchemaNode | null): string | null {
  if (!node) {
    return null;
  }
  if (typeof node.minimum === "number") {
    return `>= ${node.minimum}`;
  }
  if (typeof node.exclusiveMinimum === "number") {
    return `> ${node.exclusiveMinimum}`;
  }
  if (typeof node.maximum === "number") {
    return `<= ${node.maximum}`;
  }
  if (typeof node.exclusiveMaximum === "number") {
    return `< ${node.exclusiveMaximum}`;
  }
  return null;
}

export function getScenarioSchemaHint(path: string[]): string | null {
  const { parent, node } = getSchemaNode(path);
  if (!node) {
    return null;
  }

  const parts: string[] = [];
  const leaf = path[path.length - 1];
  if (leaf && parent?.required?.includes(leaf)) {
    parts.push("required");
  }

  const type = extractType(node);
  if (type) {
    parts.push(type);
  }

  const range = extractRange(node);
  if (range) {
    parts.push(range);
  }

  const enumValues = extractEnumValues(node);
  if (enumValues.length > 0) {
    parts.push(`one of: ${enumValues.join(", ")}`);
  }

  const defaultValue = formatDefault(node.default);
  if (defaultValue !== null) {
    parts.push(`default ${defaultValue}`);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}
