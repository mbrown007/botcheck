"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { BuilderNode } from "@/lib/flow-translator";

export function HangupNode({ data }: NodeProps<BuilderNode>) {
  return (
    <div className="relative min-w-[220px] rounded-md border border-fail-border bg-fail-bg px-3 py-2 shadow-sm">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border !border-fail-border !bg-bg-elevated"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="rounded border border-fail-border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-fail">
          Hangup
        </span>
        <span className="font-mono text-[11px] text-text-muted">{data.turnId}</span>
      </div>
      <p className="mt-2 text-xs text-text-primary">
        End call and terminate flow.
      </p>
    </div>
  );
}
