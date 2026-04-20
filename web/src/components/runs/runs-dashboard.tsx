"use client";

import { useMemo } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardBody } from "@/components/ui/card";
import type { RunResponse } from "@/lib/api";

// ── Design tokens (hardcoded so they work inside SVG) ────────────────────────
const C = {
  pass: "#34D399",
  fail: "#F87171",
  brand: "#3B82F6",
  warn: "#FBBF24",
  muted: "#475569",
  grid: "#1E3A5F",
  surface: "#141B25",
  text: "#94A3B8",
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function bucketLabel(ts: number, bucketMs: number): string {
  const d = new Date(ts);
  if (bucketMs <= 3_600_000) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (bucketMs <= 86_400_000) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function avgScore(run: RunResponse): number | null {
  const vals = Object.values(run.scores)
    .map((s) => s.score)
    .filter((v): v is number => v != null);
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const idx = Math.max(0, Math.ceil(sorted.length * p) - 1);
  return Math.round((sorted[idx] ?? 0) * 100);
}

function buildBuckets(runs: RunResponse[]) {
  const dated = runs
    .filter((r) => r.created_at)
    .map((r) => ({ ...r, ts: new Date(r.created_at!).getTime() }));

  if (!dated.length) return { buckets: [], bucketMs: 3_600_000 };

  const span = Math.max(...dated.map((r) => r.ts)) - Math.min(...dated.map((r) => r.ts));
  const bucketMs =
    span <= 2 * 3_600_000
      ? 900_000        // 15-min buckets if ≤2 h span
      : span <= 48 * 3_600_000
      ? 3_600_000      // 1-h buckets if ≤48 h
      : span <= 7 * 86_400_000
      ? 4 * 3_600_000  // 4-h buckets if ≤1 week
      : 86_400_000;    // daily otherwise

  const map = new Map<number, { complete: number; failed: number; passed: number; gateFailed: number; scores: number[] }>();

  for (const run of dated) {
    const key = Math.floor(run.ts / bucketMs) * bucketMs;
    if (!map.has(key)) map.set(key, { complete: 0, failed: 0, passed: 0, gateFailed: 0, scores: [] });
    const b = map.get(key)!;
    if (run.state === "complete") {
      b.complete++;
      if (run.gate_result === "passed") b.passed++;
      else b.gateFailed++;
      const s = avgScore(run);
      if (s != null) b.scores.push(s);
    } else if (run.state === "failed" || run.state === "error") {
      b.failed++;
    } else {
      b.complete++; // count running/judging as in-progress complete bucket
    }
  }

  const buckets = Array.from(map.entries())
    .sort(([a], [b]) => a - b)
    .map(([ts, b]) => {
      const sorted = [...b.scores].sort((a, c) => a - c);
      return {
        label: bucketLabel(ts, bucketMs),
        complete: b.complete,
        failed: b.failed,
        passed: b.passed,
        gateFailed: b.gateFailed,
        p50: percentile(sorted, 0.5),
        p90: percentile(sorted, 0.9),
      };
    });

  return { buckets, bucketMs };
}

// ── Stat card ────────────────────────────────────────────────────────────────

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
        <p className="text-xs text-text-muted uppercase tracking-wide">{label}</p>
        <p className={`text-2xl font-semibold mt-1 ${accent ?? "text-text-primary"}`}>{value}</p>
        {sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}
      </CardBody>
    </Card>
  );
}

// ── Shared tooltip style ─────────────────────────────────────────────────────

const tooltipStyle = {
  backgroundColor: "#141B25",
  border: "1px solid #1E3A5F",
  borderRadius: 6,
  fontSize: 11,
  color: "#94A3B8",
};

// ── Dashboard ────────────────────────────────────────────────────────────────

export function RunsDashboard({ runs }: { runs: RunResponse[] }) {
  const stats = useMemo(() => {
    const total = runs.length;
    const active = runs.filter((r) => r.state === "running" || r.state === "judging").length;
    const complete = runs.filter((r) => r.state === "complete");
    const passed = complete.filter((r) => r.gate_result === "passed").length;
    const passRate = complete.length ? Math.round((passed / complete.length) * 100) : null;

    const allScores = complete.flatMap((r) => {
      const s = avgScore(r);
      return s != null ? [s] : [];
    });
    const meanScore =
      allScores.length
        ? Math.round((allScores.reduce((a, b) => a + b, 0) / allScores.length) * 100)
        : null;

    return { total, active, passRate, meanScore, completeCount: complete.length };
  }, [runs]);

  const { buckets } = useMemo(() => buildBuckets(runs), [runs]);

  if (!runs.length) return null;

  return (
    <div className="space-y-4">
      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total runs" value={stats.total} sub="latest 50" />
        <StatCard
          label="Pass rate"
          value={stats.passRate != null ? `${stats.passRate}%` : "—"}
          sub={`${stats.completeCount} complete`}
          accent={stats.passRate != null ? (stats.passRate >= 80 ? "text-pass" : stats.passRate >= 60 ? "text-warn" : "text-fail") : undefined}
        />
        <StatCard
          label="Avg score"
          value={stats.meanScore != null ? `${stats.meanScore}%` : "—"}
          sub="across dimensions"
          accent={stats.meanScore != null ? (stats.meanScore >= 80 ? "text-pass" : stats.meanScore >= 60 ? "text-warn" : "text-fail") : undefined}
        />
        <StatCard
          label="Active"
          value={stats.active}
          sub="running / judging"
          accent={stats.active > 0 ? "text-brand" : "text-text-primary"}
        />
      </div>

      {/* Charts */}
      {buckets.length > 1 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Run status */}
          <Card>
            <CardBody className="pb-2">
              <p className="text-xs font-medium text-text-secondary mb-3">Run Status</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={buckets} barGap={2} barCategoryGap="30%">
                  <XAxis dataKey="label" tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} width={24} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: C.grid, opacity: 0.4 }} />
                  <Legend wrapperStyle={{ fontSize: 10, color: C.text, paddingTop: 6 }} />
                  <Bar dataKey="complete" name="Complete" fill={C.brand} radius={[2, 2, 0, 0]} />
                  <Bar dataKey="failed" name="Failed" fill={C.fail} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>

          {/* Pass / fail over time */}
          <Card>
            <CardBody className="pb-2">
              <p className="text-xs font-medium text-text-secondary mb-3">Gate Results</p>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={buckets}>
                  <XAxis dataKey="label" tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} width={24} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 10, color: C.text, paddingTop: 6 }} />
                  <Line type="monotone" dataKey="passed" name="Pass" stroke={C.pass} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="gateFailed" name="Fail" stroke={C.fail} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>

          {/* Score percentiles */}
          <Card>
            <CardBody className="pb-2">
              <p className="text-xs font-medium text-text-secondary mb-3">Score Percentiles</p>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={buckets}>
                  <XAxis dataKey="label" tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: C.text, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${v}%`} />
                  <Legend wrapperStyle={{ fontSize: 10, color: C.text, paddingTop: 6 }} />
                  <Line type="monotone" dataKey="p50" name="p50" stroke={C.warn} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="p90" name="p90" stroke={C.brand} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
