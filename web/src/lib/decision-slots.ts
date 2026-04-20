export const DECISION_DEFAULT_SLOT = "default";
export const DECISION_PATH_SLOT_PREFIX = "path_";
export const DECISION_OUTPUT_HANDLE_PREFIX = "decision-output:";

const PATH_SLOT_PATTERN = new RegExp(`^${DECISION_PATH_SLOT_PREFIX}(\\d+)$`);

export function decisionPathSlot(indexRaw: number): string {
  const index = Math.max(1, Math.floor(indexRaw));
  return `${DECISION_PATH_SLOT_PREFIX}${index}`;
}

export function decisionOutputSlotsFromCount(outputCountRaw: number): string[] {
  const outputCount = Math.max(1, Math.floor(outputCountRaw));
  const slots: string[] = [DECISION_DEFAULT_SLOT];
  for (let index = 1; index < outputCount; index += 1) {
    slots.push(decisionPathSlot(index));
  }
  return slots;
}

export function decisionHandleId(slot: string): string {
  return `${DECISION_OUTPUT_HANDLE_PREFIX}${slot}`;
}

export function parseDecisionHandleSlot(handleId: string | null | undefined): string | null {
  if (!handleId || !handleId.startsWith(DECISION_OUTPUT_HANDLE_PREFIX)) {
    return null;
  }
  const slot = handleId.slice(DECISION_OUTPUT_HANDLE_PREFIX.length).trim().toLowerCase();
  return slot || null;
}

export function isDefaultDecisionSlot(slot: string | null | undefined): boolean {
  return (slot ?? "").trim().toLowerCase() === DECISION_DEFAULT_SLOT;
}

export function isPathDecisionSlot(slot: string | null | undefined): boolean {
  return PATH_SLOT_PATTERN.test((slot ?? "").trim().toLowerCase());
}

export function decisionPathSlotIndex(slot: string | null | undefined): number | null {
  const normalized = (slot ?? "").trim().toLowerCase();
  const match = normalized.match(PATH_SLOT_PATTERN);
  if (!match) {
    return null;
  }
  const parsed = Number.parseInt(match[1] ?? "", 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}
