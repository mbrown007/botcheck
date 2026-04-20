"use client";

import { useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Button } from "@/components/ui/button";
import { useBuilderStore } from "@/lib/builder-store";
import { getBuilderTurnWaitS, toCanonicalBuilderTurn } from "@/lib/builder-types";
import type { BuilderNode } from "@/lib/flow-translator";

export function WaitNode({ id, data }: NodeProps<BuilderNode>) {
  const updateNodeTurn = useBuilderStore((state) => state.updateNodeTurn);
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(String(getBuilderTurnWaitS(data.turn) ?? 1));
  const [error, setError] = useState<string | null>(null);

  const resetEditor = () => {
    setDraftValue(String(getBuilderTurnWaitS(data.turn) ?? 1));
    setError(null);
    setEditing(false);
  };

  const handleSave = () => {
    const parsed = Number(draftValue.trim());
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError("Use a number greater than 0.");
      return;
    }
    updateNodeTurn(
      id,
      toCanonicalBuilderTurn({
        ...data.turn,
        kind: "wait",
        wait_s: parsed,
      })
    );
    setError(null);
    setEditing(false);
  };

  return (
    <div className="relative min-w-[220px] rounded-md border border-amber-300 bg-amber-50 px-3 py-2 shadow-sm dark:border-amber-800 dark:bg-amber-950/30">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border !border-amber-300 !bg-bg-elevated"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border !border-amber-300 !bg-bg-elevated"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="rounded border border-amber-400 bg-amber-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-950 dark:border-amber-700 dark:bg-amber-900/50 dark:text-amber-200">
          Wait
        </span>
        <span className="font-mono text-[11px] text-text-muted">{data.turnId}</span>
      </div>
      <p className="mt-2 text-xs text-text-primary">
        Pause scenario clock without playing audio.
      </p>
      {editing ? (
        <div className="mt-3 space-y-2">
          <label className="block">
            <span className="mb-1 block text-[11px] text-text-secondary">Wait For (s)</span>
            <input
              value={draftValue}
              onChange={(event) => setDraftValue(event.target.value)}
              className="w-full rounded border border-amber-300 bg-white px-2 py-1 text-xs text-text-primary focus:border-border-focus focus:outline-none dark:border-amber-800 dark:bg-bg-base"
            />
          </label>
          {error ? <p className="text-[10px] text-fail">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              className="h-7 px-2 text-[10px]"
              onClick={resetEditor}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              className="h-7 px-2 text-[10px]"
              onClick={handleSave}
            >
              Save
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-xs text-text-secondary">
            {getBuilderTurnWaitS(data.turn) ?? 1}s
          </span>
          <Button
            variant="secondary"
            size="sm"
            className="h-7 px-2 text-[10px]"
            onClick={() => {
              setDraftValue(String(getBuilderTurnWaitS(data.turn) ?? 1));
              setEditing(true);
            }}
          >
            Edit
          </Button>
        </div>
      )}
    </div>
  );
}
