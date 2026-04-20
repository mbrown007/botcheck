"use client";

import { AttributionBadge } from "@/components/runs/attribution-badge";
import { GateBadge } from "@/components/runs/gate-badge";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface RunDetailHeaderProps {
  runId: string;
  scenarioId: string;
  scenarioKindLabel: "AI" | "GRAPH";
  state: string;
  triggerSource?: string | null;
  scheduleId?: string | null;
  gateResult?: string | null;
  canOperatorAct: boolean;
  actionLoading: "stop" | "fail" | null;
  onStop: () => void;
  onMarkFailed: () => void;
}

export function RunDetailHeader({
  runId,
  scenarioId,
  scenarioKindLabel,
  state,
  triggerSource,
  scheduleId,
  gateResult,
  canOperatorAct,
  actionLoading,
  onStop,
  onMarkFailed,
}: RunDetailHeaderProps) {
  const isComplete = state === "complete" || state === "failed" || state === "error";

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="rounded border border-border bg-bg-elevated px-2.5 py-1 font-mono text-xs text-text-muted">
        {runId}
      </span>
      <span className="text-sm text-text-secondary">{scenarioId}</span>
      <span className="rounded border border-border bg-bg-elevated px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-text-muted">
        {scenarioKindLabel}
      </span>
      <StatusBadge value={state} />
      <AttributionBadge triggerSource={triggerSource} scheduleId={scheduleId} />
      {isComplete && <GateBadge result={gateResult} />}
      {canOperatorAct ? (
        <>
          <Button
            variant="destructive"
            size="sm"
            onClick={onStop}
            disabled={actionLoading !== null}
          >
            {actionLoading === "stop" ? "Stopping…" : "Stop"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={onMarkFailed}
            disabled={actionLoading !== null}
          >
            {actionLoading === "fail" ? "Marking…" : "Mark Failed"}
          </Button>
        </>
      ) : null}
    </div>
  );
}
