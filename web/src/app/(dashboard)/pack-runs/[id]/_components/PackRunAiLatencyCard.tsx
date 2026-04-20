"use client";

import type { PackAiLatencySummary } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

interface PackRunAiLatencyCardProps {
  summary?: PackAiLatencySummary | null;
  providerDegraded: boolean;
  degradedAiComponents: string[];
  formatLatencyMs: (value: number | null | undefined) => string;
}

export function PackRunAiLatencyCard({
  summary,
  providerDegraded,
  degradedAiComponents,
  formatLatencyMs,
}: PackRunAiLatencyCardProps) {
  if (!summary) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm font-medium text-text-secondary">AI Runtime Latency</span>
          {providerDegraded && degradedAiComponents.length > 0 ? (
            <div className="rounded border border-warn-border bg-warn-bg px-3 py-2 text-xs text-warn">
              Degraded live AI path: {degradedAiComponents.join(", ")}
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-xs text-text-secondary">
          Transcript-derived p95 timings across {summary.ai_runs} AI child{" "}
          {summary.ai_runs === 1 ? "run" : "runs"} in the current result set.
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          <LatencyTile
            label='Bot -> Caller Reply Gap'
            value={summary.reply_gap_p95_ms}
            formatLatencyMs={formatLatencyMs}
          />
          <LatencyTile
            label="Bot Turn Duration"
            value={summary.bot_turn_duration_p95_ms}
            formatLatencyMs={formatLatencyMs}
          />
          <LatencyTile
            label="Caller Playback"
            value={summary.harness_playback_p95_ms}
            formatLatencyMs={formatLatencyMs}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function LatencyTile({
  label,
  value,
  formatLatencyMs,
}: {
  label: string;
  value?: number | null;
  formatLatencyMs: (value: number | null | undefined) => string;
}) {
  return (
    <div className="rounded border border-border bg-bg-elevated p-3">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-2 text-lg font-semibold text-text-primary">{formatLatencyMs(value)}</p>
    </div>
  );
}
