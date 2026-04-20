import type { BuilderNode, BuilderEdge, FlowMeta } from "@/lib/flow-translator";
import type { BuilderSnapshot } from "./types";

const EMPTY_META: FlowMeta = {};

function cloneNodes(nodes: BuilderNode[]): BuilderNode[] {
  return nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      turn: { ...node.data.turn },
    },
    position: { ...node.position },
  }));
}

function cloneEdges(edges: BuilderEdge[]): BuilderEdge[] {
  return edges.map((edge) => ({
    ...edge,
    data: edge.data ? { ...edge.data } : edge.data,
  }));
}

export function cloneMeta(meta: FlowMeta): FlowMeta {
  return JSON.parse(JSON.stringify(meta)) as FlowMeta;
}

export function createSnapshot(state: BuilderSnapshot): BuilderSnapshot {
  return {
    nodes: cloneNodes(state.nodes),
    edges: cloneEdges(state.edges),
    meta: cloneMeta(state.meta),
    yamlCanonical: state.yamlCanonical,
    yamlDraft: state.yamlDraft,
    persistedYaml: state.persistedYaml,
    isDirty: state.isDirty,
    syncSource: state.syncSource,
  };
}

export function baseSnapshot(): BuilderSnapshot {
  return {
    nodes: [],
    edges: [],
    meta: { ...EMPTY_META },
    yamlCanonical: "",
    yamlDraft: "",
    persistedYaml: "",
    isDirty: false,
    syncSource: "yaml",
  };
}
