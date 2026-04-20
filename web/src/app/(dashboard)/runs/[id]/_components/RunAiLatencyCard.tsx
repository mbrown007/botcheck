"use client";

import { Card, CardBody } from "@/components/ui/card";

interface LatencyMetric {
  p95Ms: number | null;
  avgMs: number | null;
  maxMs: number | null;
  samples: number;
}

interface RunAiLatencyBreakdown {
  replyGap: LatencyMetric;
  botTurnDuration: LatencyMetric;
  harnessPlayback: LatencyMetric;
}

interface RunAiLatencyCardProps {
  aiLatency: RunAiLatencyBreakdown | null;
  providerDegraded: boolean;
  degradedAiComponents: string[];
  formatLatencyMs: (value: number | null | undefined) => string;
  title?: string;
}

export function RunAiLatencyCard({
  aiLatency,
  providerDegraded,
  degradedAiComponents,
  formatLatencyMs,
  title = "Voice Runtime Latency",
}: RunAiLatencyCardProps) {
  if (!aiLatency) {
    return null;
  }

  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-text-muted">{title}</p>
            <p className="mt-1 text-xs text-text-secondary">
              Derived from persisted transcript timings for this run.
            </p>
          </div>
          {providerDegraded && degradedAiComponents.length > 0 ? (
            <div className="rounded border border-warn-border bg-warn-bg px-3 py-2 text-xs text-warn">
              Degraded live AI path: {degradedAiComponents.join(", ")}
            </div>
          ) : null}
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <LatencyTile
            label='Bot -> Caller Reply Gap'
            metric={aiLatency.replyGap}
            formatLatencyMs={formatLatencyMs}
          />
          <LatencyTile
            label="Bot Turn Duration"
            metric={aiLatency.botTurnDuration}
            formatLatencyMs={formatLatencyMs}
          />
          <LatencyTile
            label="Caller Playback"
            metric={aiLatency.harnessPlayback}
            formatLatencyMs={formatLatencyMs}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function LatencyTile({
  label,
  metric,
  formatLatencyMs,
}: {
  label: string;
  metric: LatencyMetric;
  formatLatencyMs: (value: number | null | undefined) => string;
}) {
  return (
    <div className="rounded border border-border bg-bg-elevated p-3">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-2 text-lg font-semibold text-text-primary">
        {formatLatencyMs(metric.p95Ms)}
      </p>
      <p className="mt-1 text-xs text-text-secondary">p95 from {metric.samples} samples</p>
      <p className="text-xs text-text-muted">
        avg {formatLatencyMs(metric.avgMs)} · max {formatLatencyMs(metric.maxMs)}
      </p>
    </div>
  );
}
