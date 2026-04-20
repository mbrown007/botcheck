import type { BuilderEdge } from "@/lib/flow-translator";
import { DECISION_DEFAULT_SLOT, decisionPathSlot } from "@/lib/decision-slots";

import {
  edgeCondition,
  isDefaultCondition,
  normalizeCondition,
} from "./edge-validation";
import type {
  EdgeMutationOutput,
  RemoveEdgeInput,
  UpdateEdgeConditionInput,
} from "./types";

function asDefaultEdge(edge: BuilderEdge): BuilderEdge {
  return {
    ...edge,
    label: DECISION_DEFAULT_SLOT,
    data: {
      ...(edge.data ?? {}),
      condition: DECISION_DEFAULT_SLOT,
      kind: "branch_default",
    },
  };
}

function asCaseEdge(edge: BuilderEdge, condition: string): BuilderEdge {
  return {
    ...edge,
    label: condition,
    data: {
      ...(edge.data ?? {}),
      condition,
      kind: "branch_case",
    },
  };
}

function asLinearEdge(edge: BuilderEdge): BuilderEdge {
  return {
    ...edge,
    label: undefined,
    data: {
      ...(edge.data ?? {}),
      condition: undefined,
      kind: "next",
    },
  };
}

export function updateEdgeCondition({
  edges,
  edgeId,
  condition,
}: UpdateEdgeConditionInput): EdgeMutationOutput {
  const nextCondition = normalizeCondition(condition);
  if (!nextCondition) {
    return {
      edges,
      error: "Condition label cannot be empty.",
    };
  }
  if (isDefaultCondition(nextCondition)) {
    return {
      edges,
      error: "Condition label 'default' is reserved for fallback routing.",
    };
  }

  const edge = edges.find((item) => item.id === edgeId);
  if (!edge) {
    return {
      edges,
      error: "Edge not found.",
    };
  }
  if (isDefaultCondition(edgeCondition(edge))) {
    return {
      edges,
      error: "Default edge label cannot be edited.",
    };
  }

  const sameSource = edges.filter((item) => item.source === edge.source);
  if (sameSource.length <= 1) {
    return {
      edges,
      error:
        "This turn has only one exit; add another connection to enable condition labels.",
    };
  }

  const duplicate = sameSource.some(
    (item) =>
      item.id !== edgeId &&
      edgeCondition(item).toLowerCase() === nextCondition.toLowerCase()
  );
  if (duplicate) {
    return {
      edges,
      error: `Condition "${nextCondition}" already exists on this turn.`,
    };
  }

  return {
    edges: edges.map((item) => {
      if (item.id !== edgeId) {
        return item;
      }
      return asCaseEdge(item, nextCondition);
    }),
  };
}

export function removeEdgeWithRebalance({
  edges,
  edgeId,
}: RemoveEdgeInput): EdgeMutationOutput {
  const edge = edges.find((item) => item.id === edgeId);
  if (!edge) {
    return { edges };
  }

  let remainingEdges = edges.filter((item) => item.id !== edgeId);
  const source = edge.source;
  const sourceEdges = remainingEdges.filter((item) => item.source === source);

  if (sourceEdges.length <= 0) {
    return { edges: remainingEdges };
  }

  if (sourceEdges.length === 1) {
    const sole = sourceEdges[0];
    if (!sole) {
      return { edges: remainingEdges };
    }
    remainingEdges = remainingEdges.map((item) =>
      item.id === sole.id ? asLinearEdge(item) : item
    );
    return { edges: remainingEdges };
  }

  const defaultEdges = sourceEdges.filter((item) =>
    isDefaultCondition(edgeCondition(item))
  );
  if (defaultEdges.length === 0) {
    const promoteTarget = sourceEdges[0];
    if (promoteTarget) {
      remainingEdges = remainingEdges.map((item) =>
        item.id === promoteTarget.id ? asDefaultEdge(item) : item
      );
    }
    return { edges: remainingEdges };
  }

  if (defaultEdges.length > 1) {
    const [firstDefault, ...restDefaults] = defaultEdges;
    const demoted = new Set(restDefaults.map((item) => item.id));
    let autoIdx = 1;
    remainingEdges = remainingEdges.map((item) => {
      if (!demoted.has(item.id)) {
        return item;
      }
      const nextCondition = decisionPathSlot(autoIdx);
      autoIdx += 1;
      return asCaseEdge(item, nextCondition);
    });
    if (firstDefault) {
      remainingEdges = remainingEdges.map((item) =>
        item.id === firstDefault.id ? asDefaultEdge(item) : item
      );
    }
  }

  return { edges: remainingEdges };
}
