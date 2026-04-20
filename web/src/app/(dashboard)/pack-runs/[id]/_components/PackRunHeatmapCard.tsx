"use client";

import Link from "next/link";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

interface HeatmapEntry {
  avg_score?: number | null;
  fail_count: number;
}

interface PackRunHeatmapCardProps {
  rows: Array<[string, HeatmapEntry]>;
  previousPackRunId?: string | null;
  previousHeatmap?: Record<string, HeatmapEntry> | null;
  formatHeatmapTrend: (current?: number | null, previous?: number | null) => {
    label: string;
    toneClass: string;
  };
}

export function PackRunHeatmapCard({
  rows,
  previousPackRunId,
  previousHeatmap,
  formatHeatmapTrend,
}: PackRunHeatmapCardProps) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-text-secondary">Dimension Heatmap</span>
          {previousPackRunId ? (
            <Link
              href={`/pack-runs/${previousPackRunId}`}
              className="text-xs font-mono text-brand hover:text-brand-hover"
            >
              Compare to previous run
            </Link>
          ) : null}
        </div>
      </CardHeader>
      <CardBody className="p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
              <th className="px-5 py-3 text-left font-medium">Dimension</th>
              <th className="px-5 py-3 text-left font-medium">Avg Score</th>
              <th className="px-5 py-3 text-left font-medium">Fail Count</th>
              <th className="px-5 py-3 text-left font-medium">Trend</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([dimension, entry]) => {
              const previousEntry = previousHeatmap?.[dimension];
              const trend = formatHeatmapTrend(entry.avg_score, previousEntry?.avg_score);
              return (
                <tr key={dimension} className="border-b border-border last:border-0">
                  <td className="px-5 py-3 font-mono text-xs text-brand">{dimension}</td>
                  <td className="px-5 py-3 font-mono text-xs text-text-secondary">
                    {typeof entry.avg_score === "number" ? entry.avg_score.toFixed(4) : "—"}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-text-secondary">
                    {entry.fail_count}
                  </td>
                  <td className={`px-5 py-3 font-mono text-xs ${trend.toneClass}`}>
                    {trend.label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
