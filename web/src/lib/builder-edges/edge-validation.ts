import type { BuilderEdge } from "@/lib/flow-translator";
import {
  DECISION_PATH_SLOT_PREFIX,
  decisionPathSlot,
  isDefaultDecisionSlot,
} from "@/lib/decision-slots";

export function edgeCondition(edge: BuilderEdge): string {
  if (typeof edge.data?.condition === "string") {
    return edge.data.condition.trim();
  }
  if (typeof edge.label === "string") {
    return edge.label.trim();
  }
  return "";
}

export function normalizeCondition(raw: string | null | undefined): string {
  return (raw ?? "").trim();
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function ensureUniqueEdgeId(edges: BuilderEdge[], base: string): string {
  if (!edges.some((edge) => edge.id === base)) {
    return base;
  }
  let idx = 2;
  while (edges.some((edge) => edge.id === `${base}-${idx}`)) {
    idx += 1;
  }
  return `${base}-${idx}`;
}

export function isDefaultCondition(condition: string): boolean {
  return isDefaultDecisionSlot(condition);
}

export function nextPathCondition(sourceEdges: BuilderEdge[]): string {
  const taken = new Set(
    sourceEdges
      .map((edge) => edgeCondition(edge).toLowerCase())
      .filter((condition) => condition.startsWith(DECISION_PATH_SLOT_PREFIX))
  );
  let index = 1;
  while (taken.has(decisionPathSlot(index))) {
    index += 1;
  }
  return decisionPathSlot(index);
}

export function shouldPromptForBranchCondition(
  edges: BuilderEdge[],
  source: string
): boolean {
  return edges.some((edge) => edge.source === source);
}
