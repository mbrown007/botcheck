"use client";

import { StatusBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { PackRunDetail } from "@/lib/api";

interface PackRunSummaryGridProps {
  detail: PackRunDetail;
  transportProfileLabel?: string | null;
  progressPct: number;
  pendingOrRunning: number;
  passRatePct: number;
  formatTriggerSource: (detail: PackRunDetail) => string;
  formatTs: (value?: string | null) => string;
}

export function PackRunSummaryGrid({
  detail,
  transportProfileLabel,
  progressPct,
  pendingOrRunning,
  passRatePct,
  formatTriggerSource,
  formatTs,
}: PackRunSummaryGridProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <Card>
        <CardHeader>
          <span className="text-xs uppercase tracking-wide text-text-muted">State</span>
        </CardHeader>
        <CardBody className="space-y-2">
          <StatusBadge value={detail.state} label={detail.state} />
          <StatusBadge value={detail.gate_outcome} label={detail.gate_outcome} />
          <p className="font-mono text-xs text-text-muted">{formatTriggerSource(detail)}</p>
          <p className="text-xs text-text-muted">
            transport: {transportProfileLabel ?? detail.transport_profile_id ?? detail.destination_id ?? "—"}
            {detail.dial_target ? ` · target: ${detail.dial_target}` : ""}
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <span className="text-xs uppercase tracking-wide text-text-muted">Progress</span>
        </CardHeader>
        <CardBody>
          <p className="text-lg font-semibold text-text-primary">
            {detail.completed}/{detail.total_scenarios}
          </p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-bg-elevated">
            <div
              className="h-full rounded-full bg-brand transition-all"
              style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-text-muted">{progressPct}% complete</p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <span className="text-xs uppercase tracking-wide text-text-muted">Summary</span>
        </CardHeader>
        <CardBody className="space-y-1 text-xs text-text-secondary">
          <p>pass rate: {passRatePct}%</p>
          <p>blocked: {detail.blocked}</p>
          <p>failed: {detail.failed}</p>
          <p>pending/running: {pendingOrRunning}</p>
        </CardBody>
      </Card>

      {typeof detail.cost_pence === "number" ? (
        <Card>
          <CardHeader>
            <span className="text-xs uppercase tracking-wide text-text-muted">Cost</span>
          </CardHeader>
          <CardBody>
            <p className="text-lg font-semibold text-text-primary">{detail.cost_pence}p</p>
            <p className="mt-1 text-xs text-text-muted">Child-run rollup</p>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <span className="text-xs uppercase tracking-wide text-text-muted">Dispatch</span>
          </CardHeader>
          <CardBody className="space-y-1 text-xs text-text-secondary">
            <p>dispatched: {detail.dispatched}</p>
            <p>updated: {formatTs(detail.updated_at)}</p>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
