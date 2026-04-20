function nextCopyValue(
  baseValue: string,
  existingValues: Iterable<string>,
  formatter: (index: number) => string
): string {
  const normalizedExisting = new Set(
    Array.from(existingValues, (value) => value.trim().toLowerCase()).filter(Boolean)
  );
  for (let index = 1; index < 1000; index += 1) {
    const candidate = formatter(index).trim();
    if (!normalizedExisting.has(candidate.toLowerCase())) {
      return candidate;
    }
  }
  return formatter(Date.now());
}

export function nextPersonaCopyDisplayName(
  displayName: string,
  existingDisplayNames: Iterable<string>
): string {
  const base = displayName.trim() || "Persona";
  return nextCopyValue(base, existingDisplayNames, (index) =>
    index === 1 ? `${base} Copy` : `${base} Copy ${index}`
  );
}

export function nextPersonaCopyHandle(
  handle: string,
  existingHandles: Iterable<string>
): string {
  const base = handle.trim() || "persona";
  return nextCopyValue(base, existingHandles, (index) =>
    index === 1 ? `${base}_copy` : `${base}_copy_${index}`
  );
}
