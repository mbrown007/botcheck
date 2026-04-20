"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import type { BuilderEdge } from "@/lib/flow-translator";
import { edgeCondition } from "@/lib/builder-edges";
import { isDefaultDecisionSlot } from "@/lib/decision-slots";

interface BranchingEdgeData extends Record<string, unknown> {
  onRequestEdit?: (edgeId: string) => void;
  onRequestDelete?: (edgeId: string) => void;
  sourceEdgeCount?: number;
}

export function BranchingEdge(props: EdgeProps<BuilderEdge>) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
    style,
    data,
  } = props;

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeData = (data ?? {}) as BranchingEdgeData;
  const condition = edgeCondition(props as unknown as BuilderEdge);
  const hasBranching = (edgeData.sourceEdgeCount ?? 0) > 1;
  const editable = hasBranching && !isDefaultDecisionSlot(condition);
  const label = condition || "next";
  const defaultEdge = isDefaultDecisionSlot(condition);
  const edgeStyle = {
    stroke: defaultEdge ? "rgb(var(--flow-edge))" : "rgb(var(--flow-edge-active))",
    strokeWidth: defaultEdge ? 1.6 : 1.9,
    strokeDasharray: defaultEdge ? "5 4" : undefined,
    ...(style ?? {}),
  };

  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={edgeStyle} />
      <EdgeLabelRenderer>
        <div
          className="pointer-events-auto nodrag nopan absolute rounded border border-border bg-bg-surface px-1.5 py-1 shadow-sm"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          <div className="flex items-center gap-1">
            <span
              data-testid={`edge-label-${id}`}
              className="max-w-[120px] truncate text-[10px] text-text-primary"
            >
              {label}
            </span>
            {editable && (
              <button
                type="button"
                data-testid={`edge-edit-btn-${id}`}
                className="rounded border border-border px-1 text-[9px] text-text-secondary hover:text-text-primary"
                onClick={() => edgeData.onRequestEdit?.(id)}
              >
                Edit
              </button>
            )}
            <button
              type="button"
              data-testid={`edge-delete-btn-${id}`}
              className="rounded border border-fail-border px-1 text-[9px] text-fail hover:bg-fail-bg"
              onClick={() => edgeData.onRequestDelete?.(id)}
            >
              Del
            </button>
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
