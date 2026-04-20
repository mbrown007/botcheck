"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { getBuilderTurnListen } from "@/lib/builder-types";
import type { BuilderNode } from "@/lib/flow-translator";

export function BotNode({ data }: NodeProps<BuilderNode>) {
  const timeoutS =
    typeof data.turn?.config?.timeout_s === "number" ? data.turn.config.timeout_s : null;
  const waitForResponse = data.turn ? getBuilderTurnListen(data.turn) : true;
  const expectCount =
    data.turn?.expect && typeof data.turn.expect === "object"
      ? Object.values(data.turn.expect).filter((value) => value !== null && value !== undefined)
          .length
      : 0;
  const listenForS =
    typeof data.turn?.config?.listen_for_s === "number" ? data.turn.config.listen_for_s : null;
  const botPlaceholder =
    waitForResponse
      ? "Wait for bot greeting or unprompted speech."
      : "Bot turn marker";

  return (
    <div className="relative w-[260px] max-w-[260px] rounded-xl border border-border bg-bg-elevated px-3 py-2 shadow-sm">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border !border-border !bg-bg-surface"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border !border-border !bg-bg-surface"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="rounded bg-bg-base px-2 py-0.5 font-mono text-[11px] text-text-secondary">
          {data.turnId}
        </span>
        <div className="flex items-center gap-1">
          <span className="rounded border border-brand/40 px-1.5 py-0.5 text-[10px] text-brand">
            Listen First
          </span>
          {timeoutS !== null && (
            <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-muted">
              {timeoutS}s
            </span>
          )}
          {listenForS !== null && (
            <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-muted">
              listen {listenForS}s
            </span>
          )}
          {expectCount > 0 && (
            <span className="rounded border border-pass-border px-1.5 py-0.5 text-[10px] text-pass">
              Expect {expectCount}
            </span>
          )}
          <span className="text-[10px] uppercase tracking-wide text-text-muted">Bot</span>
        </div>
      </div>
      <p className="mt-2 max-h-[3.75rem] overflow-hidden whitespace-pre-wrap break-words text-xs leading-5 text-text-secondary [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:3]">
        {data.text || botPlaceholder}
      </p>
    </div>
  );
}
