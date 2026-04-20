import type { Node } from "@xyflow/react";

interface BuilderNodePosition {
  x: number;
  y: number;
}

export type BuilderNodePositionMap = Record<string, BuilderNodePosition>;

const LAYOUT_STORAGE_PREFIX = "botcheck:builder:layout_v1";
export const BUILDER_DRAFT_LAYOUT_SESSION_KEY = "botcheck:builder:draft_layout_session";

interface SessionStorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

interface LayoutKeyParams {
  tenantId: string;
  scenarioId: string | null;
  sessionId?: string;
}

export function buildLayoutStorageKey({
  tenantId,
  scenarioId,
  sessionId,
}: LayoutKeyParams): string {
  if (scenarioId) {
    return `${LAYOUT_STORAGE_PREFIX}:${tenantId}:${scenarioId}`;
  }
  // Draft layouts are intentionally session-scoped to avoid cross-tab collisions.
  const fallbackSessionId = sessionId ?? "draft";
  return `${LAYOUT_STORAGE_PREFIX}:${tenantId}:draft:${fallbackSessionId}`;
}

function generateDraftLayoutSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

export function getOrCreateDraftLayoutSessionId(
  storage: SessionStorageLike | null | undefined =
    typeof window !== "undefined" ? window.sessionStorage : undefined
): string {
  const createId = generateDraftLayoutSessionId;
  if (!storage) {
    return createId();
  }
  try {
    const existing = storage.getItem(BUILDER_DRAFT_LAYOUT_SESSION_KEY);
    if (existing) {
      return existing;
    }
    const generated = createId();
    storage.setItem(BUILDER_DRAFT_LAYOUT_SESSION_KEY, generated);
    return generated;
  } catch {
    return createId();
  }
}

export function readLayoutPositions(
  key: string
): BuilderNodePositionMap | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(raw) as BuilderNodePositionMap;
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

export function writeLayoutPositions(
  key: string,
  nodes: Array<Node<Record<string, unknown>>>
): void {
  if (typeof window === "undefined") {
    return;
  }
  const positionMap: BuilderNodePositionMap = {};
  for (const node of nodes) {
    positionMap[node.id] = {
      x: node.position.x,
      y: node.position.y,
    };
  }
  window.localStorage.setItem(key, JSON.stringify(positionMap));
}
