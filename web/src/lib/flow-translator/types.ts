import type { Edge, Node } from "@xyflow/react";
import type { BuilderNodeData } from "@/lib/node-registry";

export interface BuilderEdgeData {
  [key: string]: unknown;
  condition?: string;
  implicit?: boolean;
  kind?: "next" | "branch_case" | "branch_default";
}

export type BuilderNode = Node<BuilderNodeData>;
export type BuilderEdge = Edge<BuilderEdgeData>;

export interface FlowMeta extends Record<string, unknown> {
  __unknownTopLevelKeyOrder?: string[];
}

export interface FlowDocument {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  meta: FlowMeta;
}

export interface FlowToYamlInput {
  nodes: BuilderNode[];
  edges: BuilderEdge[];
  meta: FlowMeta;
}
