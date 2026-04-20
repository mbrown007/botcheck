import type { BuilderEdge } from "@/lib/flow-translator";
import { DECISION_DEFAULT_SLOT } from "@/lib/decision-slots";

import {
  edgeCondition,
  ensureUniqueEdgeId,
  isDefaultCondition,
  nextPathCondition,
  normalizeCondition,
  slugify,
} from "./edge-validation";
import type { ConnectInput, ConnectOutput } from "./types";

export function connectWithBranchingRules({
  edges,
  source,
  target,
  condition,
  sourceHandle,
  allowDefaultCondition,
}: ConnectInput): ConnectOutput {
  const sourceEdges = edges.filter((edge) => edge.source === source);
  const normalizedCondition = normalizeCondition(condition);

  if (sourceEdges.length === 0) {
    if (!normalizedCondition) {
      const baseId = `${source}::next::${target}`;
      const nextEdge: BuilderEdge = {
        id: ensureUniqueEdgeId(edges, baseId),
        source,
        target,
        sourceHandle: sourceHandle ?? undefined,
        data: { kind: "next" },
      };
      return {
        edges: [...edges, nextEdge],
      };
    }

    if (isDefaultCondition(normalizedCondition)) {
      if (!allowDefaultCondition) {
        return {
          edges,
          error: "Condition label 'default' is reserved for fallback routing.",
        };
      }
      const defaultBaseId = `${source}::default`;
      const defaultEdge: BuilderEdge = {
        id: ensureUniqueEdgeId(edges, defaultBaseId),
        source,
        target,
        sourceHandle: sourceHandle ?? undefined,
        label: DECISION_DEFAULT_SLOT,
        data: {
          condition: DECISION_DEFAULT_SLOT,
          kind: "branch_default",
        },
      };
      return {
        edges: [...edges, defaultEdge],
      };
    }

    const caseBaseId = `${source}::case::${slugify(normalizedCondition) || "path"}`;
    const caseEdge: BuilderEdge = {
      id: ensureUniqueEdgeId(edges, caseBaseId),
      source,
      target,
      sourceHandle: sourceHandle ?? undefined,
      label: normalizedCondition,
      data: {
        condition: normalizedCondition,
        kind: "branch_case",
      },
    };
    return {
      edges: [...edges, caseEdge],
    };
  }

  const conditionValue = normalizedCondition || nextPathCondition(sourceEdges);
  if (isDefaultCondition(conditionValue)) {
    if (allowDefaultCondition) {
      const duplicateDefault = sourceEdges.some((edge) =>
        isDefaultCondition(edgeCondition(edge))
      );
      if (duplicateDefault) {
        return {
          edges,
          error: "Default route already exists on this turn.",
        };
      }
      const defaultBaseId = `${source}::default`;
      const defaultEdge: BuilderEdge = {
        id: ensureUniqueEdgeId(edges, defaultBaseId),
        source,
        target,
        sourceHandle: sourceHandle ?? undefined,
        label: DECISION_DEFAULT_SLOT,
        data: {
          condition: DECISION_DEFAULT_SLOT,
          kind: "branch_default",
        },
      };
      return {
        edges: [...edges, defaultEdge],
      };
    }
    return {
      edges,
      error: "Condition label 'default' is reserved for fallback routing.",
    };
  }

  const duplicate = sourceEdges.some(
    (edge) => edgeCondition(edge).toLowerCase() === conditionValue.toLowerCase()
  );
  if (duplicate) {
    return {
      edges,
      error: `Condition "${conditionValue}" already exists on this turn.`,
    };
  }

  const caseBaseId = `${source}::case::${slugify(conditionValue) || "path"}`;
  const caseEdge: BuilderEdge = {
    id: ensureUniqueEdgeId(edges, caseBaseId),
    source,
    target,
    sourceHandle: sourceHandle ?? undefined,
    label: conditionValue,
    data: {
      condition: conditionValue,
      kind: "branch_case",
    },
  };

  const hasDefault = sourceEdges.some((edge) =>
    isDefaultCondition(edgeCondition(edge))
  );

  if (hasDefault) {
    return {
      edges: [...edges, caseEdge],
    };
  }

  const workingEdges = [...edges, caseEdge];
  const firstUnlabeledSourceIndex = workingEdges.findIndex(
    (edge) =>
      edge.source === source &&
      !edgeCondition(edge) &&
      edge.id !== caseEdge.id
  );

  if (firstUnlabeledSourceIndex >= 0) {
    const edgeToPromote = workingEdges[firstUnlabeledSourceIndex];
    if (edgeToPromote) {
      workingEdges[firstUnlabeledSourceIndex] = {
        ...edgeToPromote,
        label: DECISION_DEFAULT_SLOT,
        data: {
          ...(edgeToPromote.data ?? {}),
          condition: DECISION_DEFAULT_SLOT,
          kind: "branch_default",
        },
      };
    }
    return { edges: workingEdges };
  }

  const fallbackTarget = sourceEdges[0]?.target ?? target;
  const defaultBaseId = `${source}::default`;
  const defaultEdge: BuilderEdge = {
    id: ensureUniqueEdgeId(workingEdges, defaultBaseId),
    source,
    target: fallbackTarget,
    label: DECISION_DEFAULT_SLOT,
    data: {
      condition: DECISION_DEFAULT_SLOT,
      kind: "branch_default",
    },
  };

  return {
    edges: [...workingEdges, defaultEdge],
  };
}
