import type { BuilderEdge } from "@/lib/flow-translator";

export interface ConnectInput {
  edges: BuilderEdge[];
  source: string;
  target: string;
  condition?: string | null;
  sourceHandle?: string | null;
  allowDefaultCondition?: boolean;
}

export interface ConnectOutput {
  edges: BuilderEdge[];
  error?: string;
}

export interface UpdateEdgeConditionInput {
  edges: BuilderEdge[];
  edgeId: string;
  condition: string | null | undefined;
}

export interface RemoveEdgeInput {
  edges: BuilderEdge[];
  edgeId: string;
}

export interface EdgeMutationOutput {
  edges: BuilderEdge[];
  error?: string;
}
