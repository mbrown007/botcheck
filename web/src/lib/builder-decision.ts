import { BRANCH_CASE_COUNT_DEFAULT, clampBranchCaseCount } from "@/lib/builder-blocks";
import {
  DECISION_DEFAULT_SLOT,
  decisionPathSlotIndex,
  decisionHandleId as decisionHandleIdFromContract,
  decisionOutputSlotsFromCount,
  isPathDecisionSlot,
  parseDecisionHandleSlot as parseDecisionHandleSlotFromContract,
} from "@/lib/decision-slots";
import type { BuilderEdge } from "@/lib/flow-translator";
import { edgeCondition } from "@/lib/builder-edges";

export { DECISION_OUTPUT_HANDLE_PREFIX } from "@/lib/decision-slots";

export function decisionOutputSlots(outputCountRaw: number | undefined): string[] {
  const outputCount = clampBranchCaseCount(outputCountRaw ?? BRANCH_CASE_COUNT_DEFAULT);
  return decisionOutputSlotsFromCount(outputCount);
}

export function decisionHandleId(slot: string): string {
  return decisionHandleIdFromContract(slot);
}

export function parseDecisionHandleSlot(handleId: string | null | undefined): string | null {
  return parseDecisionHandleSlotFromContract(handleId);
}

function normalizeCondition(condition: string): string {
  return condition.trim().toLowerCase();
}

export function inferDecisionSlotFromEdge(edge: BuilderEdge): string | null {
  const fromHandle = parseDecisionHandleSlot(edge.sourceHandle);
  if (fromHandle) {
    return fromHandle;
  }

  const condition = normalizeCondition(edgeCondition(edge));
  if (!condition) {
    return null;
  }
  if (condition === DECISION_DEFAULT_SLOT) {
    return DECISION_DEFAULT_SLOT;
  }
  if (isPathDecisionSlot(condition)) {
    return condition;
  }
  return null;
}

export function decisionSlotLabel(slot: string): string {
  if (slot === DECISION_DEFAULT_SLOT) {
    return DECISION_DEFAULT_SLOT;
  }
  const index = decisionPathSlotIndex(slot);
  if (index === null) {
    return slot;
  }
  return `option ${index}`;
}

export function decisionConditionForSlot(
  slot: string,
  decisionOutputLabels: Record<string, string> | null | undefined
): string {
  if (slot === DECISION_DEFAULT_SLOT) {
    return DECISION_DEFAULT_SLOT;
  }
  const rawLabel = decisionOutputLabels?.[slot];
  const normalizedLabel = typeof rawLabel === "string" ? rawLabel.trim() : "";
  return normalizedLabel || slot;
}
