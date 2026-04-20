interface NamespaceStats {
  distinctScopedNamespaces: number;
  unscopedCount: number;
}

export function normalizeNamespace(value: string | null | undefined): string | null {
  const normalized = (value ?? "")
    .split("/")
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0)
    .join("/");
  return normalized.length > 0 ? normalized : null;
}

export function namespaceSegments(value: string | null | undefined): string[] {
  return (normalizeNamespace(value) ?? "").split("/").filter(Boolean);
}

export function summarizeNamespaces(
  namespaces: Array<string | null | undefined>,
): NamespaceStats {
  const distinctScoped = new Set<string>();
  let unscopedCount = 0;

  for (const value of namespaces) {
    const normalized = normalizeNamespace(value);
    if (!normalized) {
      unscopedCount += 1;
      continue;
    }
    distinctScoped.add(normalized);
  }

  return {
    distinctScopedNamespaces: distinctScoped.size,
    unscopedCount,
  };
}
