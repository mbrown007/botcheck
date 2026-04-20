import type { ScenarioSummary } from "@/lib/api";

interface ScenarioNamespaceNode {
  path: string;
  label: string;
  depth: number;
  count: number;
}

interface ScenarioCatalogFilters {
  namespacePath: string | null;
  searchQuery: string;
  selectedTags: string[];
}

export function scenarioTags(scenario: ScenarioSummary): string[] {
  return Array.isArray(scenario.tags) ? scenario.tags : [];
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function tokenizeNamespace(namespace: string | null | undefined): string[] {
  return (namespace ?? "")
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function matchesNamespace(
  scenario: ScenarioSummary,
  namespacePath: string | null,
): boolean {
  if (!namespacePath) {
    return true;
  }
  if (namespacePath === "__ungrouped__") {
    return !normalizeText(scenario.namespace).length;
  }
  const namespace = normalizeText(scenario.namespace);
  return namespace === namespacePath || namespace.startsWith(`${namespacePath}/`);
}

export function buildScenarioNamespaceTree(
  scenarios: ScenarioSummary[],
): ScenarioNamespaceNode[] {
  const counts = new Map<string, number>();
  let ungroupedCount = 0;

  for (const scenario of scenarios) {
    const segments = tokenizeNamespace(scenario.namespace);
    if (segments.length === 0) {
      ungroupedCount += 1;
      continue;
    }
    let currentPath = "";
    for (const segment of segments) {
      currentPath = currentPath ? `${currentPath}/${segment}` : segment;
      counts.set(currentPath, (counts.get(currentPath) ?? 0) + 1);
    }
  }

  const nodes = Array.from(counts.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([path, count]) => {
      const segments = path.split("/");
      return {
        path,
        label: segments.at(-1) ?? path,
        depth: segments.length - 1,
        count,
      };
    });

  if (ungroupedCount > 0) {
    nodes.push({
      path: "__ungrouped__",
      label: "Unscoped",
      depth: 0,
      count: ungroupedCount,
    });
  }

  return nodes;
}

export function matchesScenarioSearch(
  scenario: ScenarioSummary,
  searchQuery: string,
): boolean {
  const query = normalizeText(searchQuery);
  if (!query) {
    return true;
  }

  const haystack = [
    scenario.id,
    scenario.name,
    scenario.description,
    scenario.type,
    scenario.namespace,
    scenario.scenario_kind,
    ...scenarioTags(scenario),
  ]
    .map((value) => normalizeText(value))
    .filter(Boolean)
    .join("\n");

  return haystack.includes(query);
}

export function filterScenarioCatalog(
  scenarios: ScenarioSummary[],
  filters: ScenarioCatalogFilters,
): ScenarioSummary[] {
  const selectedTags = filters.selectedTags.map((tag) => normalizeText(tag)).filter(Boolean);

  return scenarios.filter((scenario) => {
    if (!matchesNamespace(scenario, filters.namespacePath)) {
      return false;
    }
    if (!matchesScenarioSearch(scenario, filters.searchQuery)) {
      return false;
    }
    if (
      selectedTags.length > 0 &&
      !selectedTags.every((tag) =>
        scenarioTags(scenario).some((scenarioTag) => normalizeText(scenarioTag) === tag),
      )
    ) {
      return false;
    }
    return true;
  });
}

export function collectScenarioTags(scenarios: ScenarioSummary[]): string[] {
  const tags = new Map<string, string>();
  for (const scenario of scenarios) {
    for (const tag of scenarioTags(scenario)) {
      const normalized = normalizeText(tag);
      if (!normalized) {
        continue;
      }
      if (!tags.has(normalized)) {
        tags.set(normalized, tag.trim());
      }
    }
  }
  return Array.from(tags.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, display]) => display);
}
