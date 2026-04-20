"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useScheduleRuns, useSchedules } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { GateBadge } from "@/components/runs/gate-badge";
import { TableState } from "@/components/ui/table-state";

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <Card>
      <CardBody className="py-3">
        <p className="text-xs uppercase tracking-wide text-text-muted">{label}</p>
        <p className={`mt-1 text-2xl font-semibold ${accent ?? "text-text-primary"}`}>{value}</p>
        {sub ? <p className="mt-0.5 text-xs text-text-muted">{sub}</p> : null}
      </CardBody>
    </Card>
  );
}

export default function ScheduleHistoryPage() {
  const { id } = useParams<{ id: string }>();
  const { data: runs, error: runsError } = useScheduleRuns(id ?? null);
  const { data: schedules } = useSchedules();

  const schedule = useMemo(
    () => schedules?.find((s) => s.schedule_id === id) ?? null,
    [schedules, id],
  );

  const stats = useMemo(() => {
    if (!runs?.length) return null;
    const total = runs.length;
    const complete = runs.filter((r) => r.state === "complete");
    const passed = complete.filter((r) => r.gate_result === "passed").length;
    const failed = runs.filter((r) => r.state === "failed" || r.state === "error").length;
    // Pass rate over all terminal runs — not just complete — so failures count against it.
    const terminal = complete.length + failed;
    const passRate = terminal ? Math.round((passed / terminal) * 100) : null;
    const lastRun = runs[0];
    return { total, complete: complete.length, passed, failed, passRate, lastRun };
  }, [runs]);

  const targetLabel = schedule
    ? (schedule.scenario_id ?? schedule.ai_scenario_id ?? schedule.pack_id ?? schedule.schedule_id)
    : id;
  const scheduleLabel = schedule?.name?.trim() || targetLabel;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/schedules"
          className="inline-flex items-center gap-1.5 text-xs text-text-muted transition-colors hover:text-text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Schedules
        </Link>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-text-primary">{scheduleLabel}</h1>
        <p className="mt-0.5 font-mono text-xs text-text-muted">{id}</p>
        {schedule && (
          <p className="mt-1 text-sm text-text-secondary">
            {targetLabel}
            {schedule.cron_expr ? (
              <span className="ml-2 font-mono text-xs text-text-muted">{schedule.cron_expr}</span>
            ) : null}
          </p>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Total Runs" value={stats.total} sub="for this schedule" />
          <StatCard
            label="Pass Rate"
            value={stats.passRate != null ? `${stats.passRate}%` : "—"}
            sub={`${stats.passed} of ${stats.complete + stats.failed} terminal`}
            accent={
              stats.passRate != null
                ? stats.passRate >= 80
                  ? "text-pass"
                  : stats.passRate >= 60
                    ? "text-warn"
                    : "text-fail"
                : undefined
            }
          />
          <StatCard
            label="Failures"
            value={stats.failed}
            sub="failed or error"
            accent={stats.failed > 0 ? "text-fail" : "text-pass"}
          />
          <StatCard
            label="Last Gate"
            value={stats.lastRun?.gate_result?.toUpperCase() ?? "—"}
            sub={
              stats.lastRun?.created_at
                ? new Date(stats.lastRun.created_at).toLocaleString()
                : "no runs yet"
            }
            accent={
              stats.lastRun?.gate_result === "passed"
                ? "text-pass"
                : stats.lastRun?.gate_result === "blocked"
                  ? "text-fail"
                  : "text-text-primary"
            }
          />
        </div>
      )}

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">
            {runs?.length ?? 0} run{runs?.length === 1 ? "" : "s"} (latest 100)
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {runsError && (
            <TableState
              kind="error"
              title="Failed to load runs"
              message={runsError.message}
              columns={5}
            />
          )}
          {!runs && !runsError && (
            <TableState kind="loading" message="Loading runs…" columns={5} rows={6} />
          )}
          {runs?.length === 0 && (
            <TableState
              kind="empty"
              title="No runs yet"
              message="This schedule has not produced any runs yet."
              columns={5}
            />
          )}
          {runs && runs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-3 text-left font-medium">Run ID</th>
                  <th className="px-5 py-3 text-left font-medium">State</th>
                  <th className="px-5 py-3 text-left font-medium hidden md:table-cell">Gate</th>
                  <th className="px-5 py-3 text-left font-medium hidden md:table-cell">
                    Triggered by
                  </th>
                  <th className="px-5 py-3 text-left font-medium hidden lg:table-cell">Created</th>
                  <th className="px-5 py-3 text-right font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="border-b border-border last:border-0 transition-colors hover:bg-bg-elevated"
                  >
                    <td className="px-5 py-3 font-mono text-xs text-text-muted">{run.run_id}</td>
                    <td className="px-5 py-3">
                      <StatusBadge value={run.state} />
                    </td>
                    <td className="hidden px-5 py-3 md:table-cell">
                      <GateBadge result={run.gate_result} />
                    </td>
                    <td className="hidden px-5 py-3 text-xs text-text-muted md:table-cell">
                      {run.triggered_by ?? run.trigger_source ?? "—"}
                    </td>
                    <td className="hidden px-5 py-3 text-xs text-text-muted lg:table-cell">
                      {run.created_at ? new Date(run.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link
                        href={`/runs/${run.run_id}`}
                        className="text-xs text-brand transition-colors hover:text-brand-hover"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
