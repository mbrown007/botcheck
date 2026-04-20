"use client";

import { useMemo, useState } from "react";
import type { RunFinding } from "@/lib/api";

interface FindingsExplorerProps {
  findings: RunFinding[];
}

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"] as const;

export function FindingsExplorer({ findings }: FindingsExplorerProps) {
  const [dimensionFilter, setDimensionFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");

  const dimensionOptions = useMemo(() => {
    return Array.from(new Set(findings.map((item) => item.dimension))).sort();
  }, [findings]);

  const filtered = useMemo(() => {
    return findings.filter((item) => {
      const dimensionMatch = dimensionFilter === "all" || item.dimension === dimensionFilter;
      const severityMatch = severityFilter === "all" || item.severity === severityFilter;
      return dimensionMatch && severityMatch;
    });
  }, [dimensionFilter, severityFilter, findings]);

  if (findings.length === 0) {
    return <p className="text-sm text-text-muted">No findings were emitted for this run.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs text-text-secondary">Dimension</span>
          <select
            value={dimensionFilter}
            onChange={(e) => setDimensionFilter(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          >
            <option value="all">All dimensions</option>
            {dimensionOptions.map((dim) => (
              <option key={dim} value={dim}>
                {dim}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs text-text-secondary">Severity</span>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          >
            <option value="all">All severities</option>
            {SEVERITY_ORDER.map((sev) => (
              <option key={sev} value={sev}>
                {sev}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="text-xs text-text-muted">
        Showing {filtered.length} of {findings.length} findings.
      </p>

      {filtered.length === 0 && (
        <p className="text-sm text-text-muted">No findings match the selected filters.</p>
      )}

      {filtered.map((finding, i) => (
        <details
          key={`${finding.dimension}:${finding.turn_number}:${i}`}
          open={i === 0}
          className="rounded border border-border bg-bg-elevated"
        >
          <summary className="cursor-pointer px-3 py-2 text-xs uppercase tracking-wide text-text-muted">
            {finding.dimension} | {finding.severity} | turn {finding.turn_number} |{" "}
            {finding.speaker}
          </summary>
          <div className="border-t border-border px-3 py-2">
            <p className="text-sm text-text-primary">{finding.finding}</p>
            {finding.quoted_text && (
              <p className="mt-1 text-xs italic text-text-secondary">
                Evidence: &quot;{finding.quoted_text}&quot;
              </p>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}
