"use client";

import Link from "next/link";
import type { PackRunChildSummary } from "@/lib/api";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import {
  packRunFailureCategoryLabel,
  packRunFailureCategoryTone,
} from "@/lib/pack-run-failure-category";

interface PackRunChildrenTableProps {
  rows: PackRunChildSummary[];
  totalRows: number;
  pageStart: number;
  pageEnd: number;
  page: number;
  totalPages: number;
  sortMode: "failures_first" | "order" | "state" | "gate_result" | "scenario_id";
  sortDir: "asc" | "desc";
  actionError: string;
  loading: boolean;
  onSetSortMode: (
    value: "failures_first" | "order" | "state" | "gate_result" | "scenario_id"
  ) => void;
  onSetSortDir: (value: "asc" | "desc") => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  formatDuration: (value?: number | null) => string;
  childStateValue: (row: { run_state?: string | null; state: string }) => string;
}

export function PackRunChildrenTable({
  rows,
  totalRows,
  pageStart,
  pageEnd,
  page,
  totalPages,
  sortMode,
  sortDir,
  actionError,
  loading,
  onSetSortMode,
  onSetSortDir,
  onPrevPage,
  onNextPage,
  formatDuration,
  childStateValue,
}: PackRunChildrenTableProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm font-medium text-text-secondary">
            Child Runs ({rows.length}/{totalRows})
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-2 text-xs text-text-muted">
              Sort
              <select
                value={sortMode}
                onChange={(event) =>
                  onSetSortMode(
                    event.target.value as
                      | "failures_first"
                      | "order"
                      | "state"
                      | "gate_result"
                      | "scenario_id"
                  )
                }
                className="rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="failures_first">failures first</option>
                <option value="order">order</option>
                <option value="state">state</option>
                <option value="gate_result">gate</option>
                <option value="scenario_id">scenario</option>
              </select>
            </label>
            {sortMode !== "failures_first" ? (
              <label className="inline-flex items-center gap-2 text-xs text-text-muted">
                Direction
                <select
                  value={sortDir}
                  onChange={(event) => onSetSortDir(event.target.value as "asc" | "desc")}
                  className="rounded-md border border-border bg-bg-elevated px-2 py-1 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                >
                  <option value="asc">asc</option>
                  <option value="desc">desc</option>
                </select>
              </label>
            ) : null}
            <span className="text-xs text-text-muted">
              {pageStart}-{pageEnd} of {totalRows}
            </span>
            <Button size="sm" variant="secondary" onClick={onPrevPage} disabled={page <= 1}>
              Prev
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={onNextPage}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardBody className="p-0">
        {loading ? <p className="px-5 py-4 text-sm text-text-muted">Loading…</p> : null}
        {!loading && rows.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-text-muted">No child runs yet.</p>
        ) : null}
        {rows.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                <th className="px-5 py-3 text-left font-medium">Scenario</th>
                <th className="px-5 py-3 text-left font-medium">State</th>
                <th className="px-5 py-3 text-left font-medium">Gate</th>
                <th className="px-5 py-3 text-left font-medium">Duration</th>
                <th className="px-5 py-3 text-left font-medium">Cost</th>
                <th className="px-5 py-3 text-left font-medium">Run</th>
                <th className="px-5 py-3 text-left font-medium">Summary</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.pack_run_item_id} className="border-b border-border last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-mono text-xs text-brand">
                      {row.ai_scenario_id ?? row.scenario_id}
                    </p>
                    <p className="mt-1 text-[10px] uppercase tracking-wide text-text-muted">
                      {row.ai_scenario_id ? "AI" : "GRAPH"}
                    </p>
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge value={childStateValue(row)} label={childStateValue(row)} />
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge value={row.gate_result} label={row.gate_result || "—"} />
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-text-secondary">
                    {formatDuration(row.duration_s)}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-text-secondary">
                    {typeof row.cost_pence === "number" ? `${row.cost_pence}p` : "—"}
                  </td>
                  <td className="px-5 py-3">
                    {row.run_id ? (
                      <Link
                        href={`/runs/${row.run_id}`}
                        className="font-mono text-xs text-brand hover:text-brand-hover"
                      >
                        {row.run_id}
                      </Link>
                    ) : (
                      <span
                        className="text-xs text-text-muted"
                        title={row.error_code || row.error_detail || "Not dispatched"}
                      >
                        Not dispatched
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-text-secondary">
                    <p>{row.summary || row.error_detail || row.error_code || "—"}</p>
                    {row.failure_category ? (
                      <p
                        className={`mt-1 font-mono text-[10px] uppercase tracking-wide ${packRunFailureCategoryTone(
                          row.failure_category
                        )}`}
                      >
                        {packRunFailureCategoryLabel(row.failure_category)}
                      </p>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {actionError ? (
          <p className="border-t border-border px-5 py-4 text-sm text-fail">{actionError}</p>
        ) : null}
      </CardBody>
    </Card>
  );
}
