import dagre from "dagre";

import type { BuilderNodePositionMap } from "@/lib/flow-layout-storage";

import { DEFAULT_NODE_HEIGHT, DEFAULT_NODE_WIDTH } from "./constants";
import type { BuilderEdge, BuilderNode } from "./types";

export function applyDagreLayout(nodes: BuilderNode[], edges: BuilderEdge[]): BuilderNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: "LR",
    nodesep: 120,
    ranksep: 250,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    graph.setNode(node.id, {
      width: DEFAULT_NODE_WIDTH,
      height: DEFAULT_NODE_HEIGHT,
    });
  }

  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  return nodes.map((node) => {
    const positioned = graph.node(node.id) as { x: number; y: number } | undefined;
    if (!positioned) {
      return node;
    }
    return {
      ...node,
      position: {
        x: positioned.x - DEFAULT_NODE_WIDTH / 2,
        y: positioned.y - DEFAULT_NODE_HEIGHT / 2,
      },
    };
  });
}

export function mergeSavedPositions(
  nodes: BuilderNode[],
  savedPositions?: BuilderNodePositionMap
): BuilderNode[] {
  if (!savedPositions || Object.keys(savedPositions).length === 0) {
    return nodes;
  }
  return nodes.map((node) => {
    const saved = savedPositions[node.id];
    if (!saved) {
      return node;
    }
    return {
      ...node,
      position: {
        x: saved.x,
        y: saved.y,
      },
    };
  });
}
