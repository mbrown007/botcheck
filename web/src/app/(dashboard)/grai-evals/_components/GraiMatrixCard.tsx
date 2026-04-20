"use client";

import { AlertCircle, Clock3, FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import { cn } from "@/lib/utils";
import type {
  GraiEvalMatrixCell,
  GraiEvalMatrixCellStatus,
  GraiEvalMatrixResponse,
} from "@/lib/api";

function percent(value: number): string {
  return `${Math.floor(value * 100)}%`;
}

function matrixBadgeValue(status: GraiEvalMatrixCellStatus): string {
  if (status === "error") {
    return "warn";
  }
  return status;
}

function matrixCellClass(status: GraiEvalMatrixCellStatus): string {
  if (status === "passed") {
    return "border-pass-border/60 bg-pass-bg/40";
  }
  if (status === "failed") {
    return "border-fail-border/60 bg-fail-bg/40";
  }
  if (status === "error") {
    return "border-warn-border/60 bg-warn-bg/30";
  }
  return "border-border bg-bg-elevated/40";
}

function summaryTone(passRate: number): "pass" | "warn" | "fail" {
  if (passRate >= 0.9) {
    return "pass";
  }
  if (passRate >= 0.7) {
    return "warn";
  }
  return "fail";
}

function cellDetail(cell: GraiEvalMatrixCell): string {
  // For failed/error cells prefer the failure reason so the triage summary is immediately useful.
  // Snippet (once populated in a future slice) is shown for passed cells only.
  if (cell.status === "failed" || cell.status === "error") {
    const firstFailure = cell.assertion_results.find((item) => !item.passed)?.failure_reason;
    if (firstFailure) return firstFailure;
  }
  if (cell.response_snippet) {
    return cell.response_snippet;
  }
  if (cell.status === "pending") {
    return "Awaiting dispatch for this destination.";
  }
  if (cell.status === "passed") {
    return "Assertions passed. Artifact drilldown remains available from the stored result.";
  }
  return "No response snippet captured for this cell yet.";
}

export function GraiMatrixCard({
  matrix,
  loading,
  error,
  onOpenArtifact,
}: {
  matrix: GraiEvalMatrixResponse | null;
  loading: boolean;
  error: string | null;
  onOpenArtifact: (evalResultId: string) => void;
}) {
  return (
    <div className="space-y-4" data-testid="grai-matrix-card">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-text-secondary">Comparison Matrix</p>
          <p className="mt-1 text-xs text-text-muted">
            Compare prompt and case outcomes side-by-side across destinations. Pending cells stay
            visible while the run is still dispatching.
          </p>
        </div>
        {matrix ? (
          <div className="flex flex-wrap gap-2 text-xs text-text-muted">
            <span>{matrix.destinations.length} destinations</span>
            <span>{matrix.total_pairs} total pairs</span>
          </div>
        ) : null}
      </div>

      {error ? (
        <TableState kind="error" message={error} columns={1} />
      ) : loading ? (
        <TableState kind="loading" message="Building comparison matrix…" columns={1} rows={4} />
      ) : !matrix ? (
        <TableState kind="empty" title="No matrix data yet" message="Launch or reopen a run to compare destinations." columns={1} />
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {matrix.destinations.map((destination) => (
              <div
                key={destination.destination_index}
                className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3"
                data-testid={`grai-matrix-summary-${destination.destination_index}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{destination.label}</p>
                    <p className="mt-1 text-xs text-text-muted">{destination.transport_profile_id}</p>
                  </div>
                  <StatusBadge
                    value={summaryTone(destination.pass_rate)}
                    label={percent(destination.pass_rate)}
                  />
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
                  <span>{destination.protocol}</span>
                  <span>{destination.passed} passed</span>
                  <span>{destination.failed} failed</span>
                  <span>{destination.errors} errors</span>
                  <span>
                    avg latency {destination.avg_latency_ms !== null && destination.avg_latency_ms !== undefined
                      ? `${Math.round(destination.avg_latency_ms)} ms`
                      : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded-2xl border border-border bg-bg-surface">
            <table className="min-w-full border-collapse text-left">
              <caption className="sr-only">
                Comparison matrix: prompt and case outcomes across {matrix.destinations.length} destination
                {matrix.destinations.length === 1 ? "" : "s"}
              </caption>
              <thead>
                <tr className="border-b border-border bg-bg-elevated/80 align-bottom">
                  <th
                    scope="col"
                    className="sticky left-0 z-20 min-w-[18rem] border-r border-border bg-bg-elevated/95 px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-text-muted"
                  >
                    Prompt × Case
                  </th>
                  {matrix.destinations.map((destination) => (
                    <th
                      key={destination.destination_index}
                      scope="col"
                      className="min-w-[19rem] border-l border-border px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-text-muted"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium normal-case tracking-normal text-text-primary">
                            {destination.label}
                          </span>
                          <StatusBadge
                            value={summaryTone(destination.pass_rate)}
                            label={percent(destination.pass_rate)}
                          />
                        </div>
                        <div className="flex flex-wrap gap-2 text-[11px] normal-case tracking-normal text-text-secondary">
                          <span>{destination.protocol}</span>
                          <span>{destination.errors} errors</span>
                          <span>
                            avg {destination.avg_latency_ms !== null && destination.avg_latency_ms !== undefined
                              ? `${Math.round(destination.avg_latency_ms)} ms`
                              : "—"}
                          </span>
                        </div>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              {matrix.prompt_groups.map((group) => (
                <tbody key={group.prompt_id} className="align-top">
                    <tr className="border-b border-border bg-bg-elevated/35">
                      <th
                        scope="rowgroup"
                        colSpan={matrix.destinations.length + 1}
                        className="px-4 py-3 text-left"
                      >
                        <div className="flex flex-col gap-1">
                          <span className="text-sm font-semibold text-text-primary">{group.prompt_label}</span>
                          <span className="text-xs text-text-secondary">{group.prompt_text}</span>
                        </div>
                      </th>
                    </tr>
                    {group.rows.map((row) => (
                      <tr key={`${group.prompt_id}-${row.case_id}`} className="border-b border-border last:border-b-0">
                        <th scope="row" className="sticky left-0 z-10 border-r border-border bg-bg-surface px-4 py-4 align-top">
                          <div className="space-y-2">
                            <p className="text-sm font-medium text-text-primary">
                              {row.case_description || row.case_id}
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {row.tags_json.map((tag) => (
                                <span
                                  key={`${row.case_id}-${tag}`}
                                  className="rounded-full border border-border px-2 py-1 text-[11px] text-text-secondary"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        </th>
                        {row.cells.map((cell) => (
                          <td
                            key={`${row.case_id}-${cell.destination_index}`}
                            className="border-l border-border px-3 py-3 align-top"
                            data-testid={`grai-matrix-cell-${group.prompt_id}-${row.case_id}-${cell.destination_index}`}
                          >
                            <div className={cn("space-y-3 rounded-xl border p-3", matrixCellClass(cell.status))}>
                              <div className="flex items-start justify-between gap-3">
                                <div className="space-y-1">
                                  <StatusBadge
                                    value={matrixBadgeValue(cell.status)}
                                    label={cell.status}
                                  />
                                  <p className="text-xs text-text-secondary">
                                    {cell.latency_ms !== null && cell.latency_ms !== undefined
                                      ? `${cell.latency_ms} ms`
                                      : "latency —"}
                                  </p>
                                </div>
                                {cell.artifact_eval_result_id ? (
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={() => onOpenArtifact(cell.artifact_eval_result_id!)}
                                    data-testid={`grai-matrix-open-${cell.artifact_eval_result_id}`}
                                  >
                                    <FlaskConical className="h-3.5 w-3.5" />
                                    Artifact
                                  </Button>
                                ) : null}
                              </div>
                              <div className="flex items-start gap-2 text-xs text-text-secondary">
                                {cell.status === "error" ? (
                                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                                ) : cell.status === "pending" ? (
                                  <Clock3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" />
                                ) : null}
                                <p className="line-clamp-4">{cellDetail(cell)}</p>
                              </div>
                              <div className="space-y-2">
                                {cell.assertion_results.map((assertion) => (
                                  <div
                                    key={`${cell.destination_index}-${assertion.assertion_index}`}
                                    className="rounded-lg border border-border/60 bg-bg-surface/80 px-2.5 py-2"
                                  >
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="text-xs font-medium text-text-primary">
                                        {assertion.assertion_type}
                                      </span>
                                      <StatusBadge
                                        value={assertion.passed ? "pass" : "fail"}
                                        label={assertion.passed ? "pass" : "fail"}
                                        className="px-1.5 py-0 text-[10px]"
                                      />
                                    </div>
                                    {!assertion.passed && assertion.failure_reason ? (
                                      <p className="mt-1 text-[11px] text-text-secondary">
                                        {assertion.failure_reason}
                                      </p>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        ))}
                      </tr>
                    ))}
                </tbody>
              ))}
            </table>
          </div>
        </>
      )}
    </div>
  );
}
