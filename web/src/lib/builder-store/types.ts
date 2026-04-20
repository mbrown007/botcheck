import type { StoreApi } from "zustand";
import type { BuilderTurn } from "@/lib/builder-types";
import type { BuilderNodePositionMap } from "@/lib/flow-layout-storage";
import type { BuilderNode, BuilderEdge, FlowMeta } from "@/lib/flow-translator";

export type SyncSource = "yaml" | "canvas";

export interface BuilderSnapshot {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  meta: FlowMeta;
  yamlCanonical: string;
  yamlDraft: string;
  persistedYaml: string;
  isDirty: boolean;
  syncSource: SyncSource;
}

export interface BuilderHistoryState {
  historyPast: BuilderSnapshot[];
  historyFuture: BuilderSnapshot[];
  canUndo: boolean;
  canRedo: boolean;
}

export interface BuilderState extends BuilderSnapshot, BuilderHistoryState {
  parseError: string | null;
  statusMessage: string | null;
  setStatusMessage: (message: string | null) => void;
  setYamlDraft: (yaml: string) => void;
  hydrateFromYaml: (yaml: string, savedPositions?: BuilderNodePositionMap) => void;
  applyYamlDraft: (savedPositions?: BuilderNodePositionMap) => boolean;
  updateNodesFromCanvas: (nodes: BuilderNode[]) => void;
  updateEdgesFromCanvas: (edges: BuilderEdge[]) => void;
  updateNodeTurn: (nodeId: string, nextTurn: BuilderTurn) => void;
  updateMeta: (nextMeta: FlowMeta) => void;
  setCanvasCanonicalYaml: (yaml: string) => void;
  markSaved: () => void;
  checkpoint: () => void;
  undo: () => void;
  redo: () => void;
  reset: () => void;
}

export type BuilderStoreSet = StoreApi<BuilderState>["setState"];
export type BuilderStoreGet = StoreApi<BuilderState>["getState"];
