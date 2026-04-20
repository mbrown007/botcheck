export function parseTagCsv(input: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const raw of input.split(",")) {
    const tag = raw.trim();
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

export function addScenarioId(selected: string[], scenarioId: string): string[] {
  const normalized = scenarioId.trim();
  if (!normalized || selected.includes(normalized)) {
    return selected;
  }
  return [...selected, normalized];
}

export function removeScenarioId(selected: string[], scenarioId: string): string[] {
  return selected.filter((value) => value !== scenarioId);
}

export function moveScenarioId(selected: string[], scenarioId: string, delta: number): string[] {
  const currentIndex = selected.indexOf(scenarioId);
  if (currentIndex === -1) {
    return selected;
  }
  const targetIndex = currentIndex + delta;
  if (targetIndex < 0 || targetIndex >= selected.length) {
    return selected;
  }
  const next = [...selected];
  next.splice(currentIndex, 1);
  next.splice(targetIndex, 0, scenarioId);
  return next;
}
