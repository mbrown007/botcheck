import type { AIScenarioSummary, ScenarioSummary } from "@/lib/api";

export const UNGROUPED_NAMESPACE_PATH = "__ungrouped__";

interface PackCatalogNamespaceNode {
  path: string;
  label: string;
  depth: number;
  count: number;
}

interface PackCatalogItem {
  key: string;
  id: string;
  name: string;
  namespace: string | null;
  kind: "GRAPH" | "AI";
  tags: string[];
}

interface PackCatalogFilters {
  namespacePath: string | null;
  searchQuery: string;
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

function matchesNamespace(item: PackCatalogItem, namespacePath: string | null): boolean {
  if (!namespacePath) {
    return true;
  }
  if (namespacePath === UNGROUPED_NAMESPACE_PATH) {
    return !normalizeText(item.namespace).length;
  }
  const namespace = normalizeText(item.namespace);
  return namespace === namespacePath || namespace.startsWith(`${namespacePath}/`);
}

export function buildPackCatalogNamespaceTree(
  items: PackCatalogItem[],
): PackCatalogNamespaceNode[] {
  const counts = new Map<string, number>();
  let ungroupedCount = 0;

  for (const item of items) {
    const segments = tokenizeNamespace(item.namespace);
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
      path: UNGROUPED_NAMESPACE_PATH,
      label: "Unscoped",
      depth: 0,
      count: ungroupedCount,
    });
  }

  return nodes;
}

function matchesPackCatalogSearch(item: PackCatalogItem, searchQuery: string): boolean {
  const query = normalizeText(searchQuery);
  if (!query) {
    return true;
  }

  const haystack = [
    item.id,
    item.name,
    item.namespace,
    item.kind,
    ...item.tags,
  ]
    .map((value) => normalizeText(value))
    .filter(Boolean)
    .join("\n");

  return haystack.includes(query);
}

export function filterPackCatalog(
  items: PackCatalogItem[],
  filters: PackCatalogFilters,
): PackCatalogItem[] {
  return items.filter((item) => {
    if (!matchesNamespace(item, filters.namespacePath)) {
      return false;
    }
    if (!matchesPackCatalogSearch(item, filters.searchQuery)) {
      return false;
    }
    return true;
  });
}

export function buildPackCatalogItems(
  graphScenarios: ScenarioSummary[],
  aiScenarios: AIScenarioSummary[],
): PackCatalogItem[] {
  return [
    ...graphScenarios.map((scenario) => ({
      key: `graph:${scenario.id}`,
      id: scenario.id,
      name: scenario.name,
      namespace: scenario.namespace ?? null,
      kind: "GRAPH" as const,
      tags: scenario.tags,
    })),
    ...aiScenarios.map((scenario) => ({
      key: `ai:${scenario.ai_scenario_id}`,
      id: scenario.ai_scenario_id,
      name: scenario.name,
      namespace: scenario.namespace ?? null,
      kind: "AI" as const,
      tags: [],
    })),
  ];
}
