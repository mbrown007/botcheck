"use client";

import type { Route } from "next";
import Link from "next/link";
import type { ComponentType } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Clock3,
  FileSearch,
  PhoneCall,
  ShieldCheck,
  Sparkles,
  TestTubeDiagonal,
} from "lucide-react";

import {
  useFeatures,
  useGraiEvalRunHistoryIndex,
  usePlatformHealth,
  useRuns,
  useSchedules,
  useTenant,
  useTenantProviderQuota,
  useTenantProviderUsage,
} from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ProviderQuotaSectionCard } from "@/components/providers/provider-quota-section-card";
import { ProviderQuotaWarningPanel } from "@/components/providers/provider-quota-warning-panel";
import { StatusBadge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  buildPlatformHealthItems,
  buildDashboardQuotaSections,
  buildDashboardQuotaWarningSummary,
  formatDashboardDateTime,
  formatDashboardRelativeTime,
  isScheduledRun,
  summarizeTenantDashboard,
} from "./tenant-dashboard-data";

const WHAT_IS_NEW = [
  {
    title: "Grai Evals landed",
    description: "Run larger HTTP eval suites, reopen older reports, and inspect failure-focused matrices.",
    href: "/grai-evals" as Route,
  },
];

const QUICK_LINKS = [
  {
    label: "Open schedules",
    href: "/schedules" as Route,
    description: "Check unattended automation and fix alerting schedules first.",
  },
  {
    label: "Inspect runs",
    href: "/runs" as Route,
    description: "Jump into failed calls, recordings, and gate outcomes.",
  },
  {
    label: "Review evals",
    href: "/grai-evals" as Route,
    description: "Open the latest eval report and drill into failing prompts.",
  },
  {
    label: "Edit scenarios",
    href: "/scenarios" as Route,
    description: "Adjust graph scenarios, upload YAML, or open the builder.",
  },
];

export function TenantDashboard() {
  const { canViewProviderQuota } = useDashboardAccess();
  const tenantResponse = useTenant();
  const runsResponse = useRuns(50, 0);
  const schedulesResponse = useSchedules();
  const featuresResponse = useFeatures();
  const healthResponse = usePlatformHealth();
  const evalRunsResponse = useGraiEvalRunHistoryIndex();
  const providerUsageResponse = useTenantProviderUsage(canViewProviderQuota);
  const providerQuotaResponse = useTenantProviderQuota(canViewProviderQuota);

  const summary = summarizeTenantDashboard({
    runs: runsResponse.data ?? [],
    schedules: schedulesResponse.data ?? [],
    evalRuns: evalRunsResponse.data ?? [],
  });
  const activityPeak = Math.max(
    1,
    ...summary.activity.map((item) => item.totalRuns)
  );
  const healthItems = buildPlatformHealthItems({
    health: healthResponse.data,
    features: featuresResponse.data,
  });
  const quotaLoading =
    canViewProviderQuota &&
    (providerUsageResponse.isLoading || providerQuotaResponse.isLoading);
  const quotaSections = buildDashboardQuotaSections({
    usage: providerUsageResponse.data,
    quota: providerQuotaResponse.data,
  });
  const quotaWarningSummary = buildDashboardQuotaWarningSummary(quotaSections);
  const scheduleNameById = Object.fromEntries(
    (schedulesResponse.data ?? []).map((schedule) => [
      schedule.schedule_id,
      schedule.name?.trim() || schedule.schedule_id,
    ])
  );
  const apiErrors = [
    runsResponse.error?.message,
    schedulesResponse.error?.message,
    evalRunsResponse.error?.message,
    healthResponse.error?.message,
    featuresResponse.error?.message,
    providerUsageResponse.error?.message,
    providerQuotaResponse.error?.message,
  ].filter((value): value is string => Boolean(value));

  const pulseMetrics = [
    {
      label: "Scheduled runs",
      value: summary.scheduledRuns24h,
      detail: "Last 24 hours",
      tone: "text-brand",
    },
    {
      label: "Alerting schedules",
      value: summary.alertingSchedules.length,
      detail: "Retry enabled and 2+ consecutive failures",
      tone: summary.alertingSchedules.length > 0 ? "text-fail" : "text-pass",
    },
    {
      label: "Scheduled failures",
      value: summary.recentScheduledFailures24h,
      detail: "All failed scheduled runs in the last 24h",
      tone: summary.recentScheduledFailures24h > 0 ? "text-warn" : "text-pass",
    },
    {
      label: "Failed runs",
      value: summary.failedRuns24h,
      detail: `${summary.totalRuns24h} total runs in the same window`,
      tone: summary.failedRuns24h > 0 ? "text-fail" : "text-pass",
    },
  ];

  return (
    <div className="space-y-6 pb-8">
      {/* ── Hero ──────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[28px] border border-border bg-gradient-to-br from-brand/10 via-bg-surface to-bg-elevated">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-12 top-0 h-48 w-48 rounded-full bg-brand/10 blur-3xl" />
          <div className="absolute bottom-0 left-0 h-44 w-44 rounded-full bg-pass/10 blur-3xl" />
          <div className="absolute left-1/3 top-1/2 h-32 w-32 rounded-full bg-warn/10 blur-3xl" />
        </div>
        <div className="relative space-y-5 px-6 py-6 lg:px-8 lg:py-7">
          {/* Title row + What's new */}
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="min-w-0 space-y-1.5">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-surface/80 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-text-secondary">
                <Sparkles className="h-3.5 w-3.5 text-brand" />
                Tenant dashboard
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary sm:text-3xl">
                Keep unattended automation visible.
              </h1>
            </div>
            {/* What's new — compact inline card */}
            <div className="w-72 shrink-0 rounded-2xl border border-border bg-bg-surface/80 px-4 py-3 shadow-sm backdrop-blur">
              <div className="mb-2 flex items-center gap-1.5">
                <Sparkles className="h-3 w-3 text-brand" />
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">What&apos;s new</p>
              </div>
              <div className="space-y-2.5">
                {WHAT_IS_NEW.map((item) => (
                  <Link key={item.title} href={item.href} className="block group">
                    <p className="text-sm font-semibold text-text-primary transition-colors group-hover:text-brand">{item.title}</p>
                    <p className="mt-0.5 text-xs leading-5 text-text-secondary">{item.description}</p>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          {/* Full-width 4-panel metric row */}
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            {pulseMetrics.map((metric) => (
              <div
                key={metric.label}
                className="flex min-h-[110px] flex-col justify-between rounded-2xl border border-border bg-bg-surface/80 px-4 py-4 shadow-sm backdrop-blur"
              >
                <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                  {metric.label}
                </p>
                <p className={cn("text-3xl font-semibold", metric.tone)}>{metric.value}</p>
                <p className="text-xs leading-5 text-text-secondary">{metric.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 24h activity + Needs attention ────────────────────────── */}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.95fr]">
        <Card className="border-border/80 bg-bg-surface/80 shadow-sm">
          <CardHeader className="border-border/80">
            <div>
              <p className="text-sm font-semibold text-text-primary">24h activity</p>
              <p className="text-xs text-text-secondary">
                Scheduled volume versus failures across the current window.
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs text-text-secondary">
              <LegendSwatch label="Scheduled" tone="bg-brand" />
              <LegendSwatch label="Failed" tone="bg-fail" />
            </div>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="grid h-36 grid-cols-12 items-end gap-2">
              {summary.activity.map((bucket) => {
                const scheduledHeight = bucket.scheduledRuns
                  ? `${Math.max(14, Math.round((bucket.scheduledRuns / activityPeak) * 100))}%`
                  : "0%";
                const failedHeight = bucket.failedRuns
                  ? `${Math.max(14, Math.round((bucket.failedRuns / activityPeak) * 100))}%`
                  : "0%";
                return (
                  <div key={bucket.label} className="flex h-full flex-col items-center gap-2">
                    <div className="flex h-full w-full items-end gap-1 rounded-2xl border border-border/80 bg-bg-elevated/70 px-1.5 py-2">
                      <div
                        className="w-full rounded-full bg-brand/80"
                        style={{ height: scheduledHeight }}
                        title={`${bucket.scheduledRuns} scheduled runs`}
                      />
                      <div
                        className="w-full rounded-full bg-fail/85"
                        style={{ height: failedHeight }}
                        title={`${bucket.failedRuns} failed runs`}
                      />
                    </div>
                    <p className="text-[11px] text-text-muted">{bucket.label}</p>
                  </div>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-text-secondary">
              <MetricPill icon={CalendarClock} label={`${summary.scheduledRuns24h} scheduled`} />
              <MetricPill icon={AlertTriangle} label={`${summary.recentScheduledFailures24h} scheduled failures`} />
              <MetricPill icon={Activity} label={`${summary.totalRuns24h} total runs`} />
            </div>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card className="border-border/80 bg-bg-surface/90 shadow-sm">
            <CardHeader className="border-border/80">
              <div>
                <p className="text-sm font-semibold text-text-primary">Needs attention</p>
                <p className="text-xs text-text-secondary">
                  Schedules with the strongest unattended risk signal.
                </p>
              </div>
              <Link
                href="/schedules"
                className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-hover"
              >
                Open schedules
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </CardHeader>
            <CardBody className="space-y-3">
              {summary.alertingSchedules.length > 0 ? (
                summary.alertingSchedules.slice(0, 4).map((schedule) => (
                  <Link
                    key={schedule.schedule_id}
                    href="/schedules"
                    className="block rounded-2xl border border-fail-border bg-fail-bg/80 px-4 py-3 transition hover:border-fail"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">
                          {schedule.name?.trim() || schedule.schedule_id}
                        </p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {schedule.consecutive_failures ?? 0} consecutive failures with retry alerting enabled.
                        </p>
                      </div>
                      <StatusBadge value="fail" label="alerting" />
                    </div>
                  </Link>
                ))
              ) : (
                <div className="rounded-2xl border border-pass-border bg-pass-bg/80 px-4 py-4">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-pass" />
                    <p className="text-sm font-semibold text-text-primary">
                      No retry-alerting schedules are currently tripped.
                    </p>
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    Recent schedule failures still appear below, but no schedule is currently in the
                    2+ consecutive failure state.
                  </p>
                </div>
              )}

              <div className="rounded-2xl border border-border bg-bg-elevated/70 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">Last failed scheduled run</p>
                    <p className="text-xs text-text-secondary">
                      Most recent scheduled failure in the current 24-hour window.
                    </p>
                  </div>
                  <Clock3 className="h-4 w-4 text-text-muted" />
                </div>
                {summary.lastFailedScheduledRun ? (
                  <Link
                    href={`/runs/${summary.lastFailedScheduledRun.run_id}` as Route}
                    className="mt-3 block rounded-xl border border-border bg-bg-surface px-3 py-3 transition hover:border-border-focus"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-text-primary">
                          {scheduleNameById[summary.lastFailedScheduledRun.schedule_id ?? ""] ??
                            summary.lastFailedScheduledRun.run_id}
                        </p>
                          <p className="mt-1 text-xs text-text-secondary">
                            {formatDashboardDateTime(summary.lastFailedScheduledRun.created_at)}
                          </p>
                        </div>
                        <StatusBadge value={summary.lastFailedScheduledRun.state} />
                      </div>
                    </Link>
                  ) : (
                    <p className="mt-3 text-sm text-text-secondary">
                      No failed scheduled runs in the last 24 hours.
                    </p>
                  )}
                </div>
              </CardBody>
            </Card>

            {apiErrors.length > 0 ? (
              <Card className="border-warn-border bg-warn-bg/80">
                <CardBody className="space-y-1">
                  <p className="text-sm font-semibold text-text-primary">Some dashboard data is partial</p>
                  {apiErrors.slice(0, 2).map((message, i) => (
                    <p key={i} className="text-xs text-text-secondary">
                      {message}
                    </p>
                  ))}
                </CardBody>
              </Card>
            ) : null}
          </div>
        </div>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.95fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div>
                <p className="text-sm font-semibold text-text-primary">Run and eval pulse</p>
                <p className="text-xs text-text-secondary">
                  Core execution volume, failures, and the latest eval checkpoint.
                </p>
              </div>
            </CardHeader>
            <CardBody className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <MetricBlock
                icon={TestTubeDiagonal}
                label="Total runs"
                value={summary.totalRuns24h}
                subtext="Runs created in the last 24 hours"
              />
              <MetricBlock
                icon={AlertTriangle}
                label="Failed runs"
                value={summary.failedRuns24h}
                subtext="Failed or errored runs in the same window"
                tone={summary.failedRuns24h > 0 ? "text-fail" : "text-pass"}
              />
              <MetricBlock
                icon={FileSearch}
                label="Eval runs"
                value={summary.evalRuns24h}
                subtext={`${summary.failedEvalRuns24h} failed eval runs in the last 24 hours`}
                tone={summary.failedEvalRuns24h > 0 ? "text-warn" : "text-brand"}
              />
              <div className="rounded-2xl border border-border bg-bg-elevated/60 p-4 md:col-span-2 xl:col-span-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">Last eval run</p>
                    <p className="text-xs text-text-secondary">
                      Most recent suite run pulled into the dashboard index.
                    </p>
                  </div>
                  <Link
                    href={
                      summary.lastEvalRun
                        ? (`/grai-evals?suite=${summary.lastEvalRun.suite_id}&run=${summary.lastEvalRun.eval_run_id}` as Route)
                        : ("/grai-evals" as Route)
                    }
                    className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-hover"
                  >
                    Open evals
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
                {summary.lastEvalRun ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <StatusBadge value={summary.lastEvalRun.status} />
                    <span className="text-sm text-text-primary">{summary.lastEvalRun.suite_id}</span>
                    <span className="text-xs text-text-secondary">
                      {formatDashboardRelativeTime(summary.lastEvalRun.created_at)}
                    </span>
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-text-secondary">No eval run history is available yet.</p>
                )}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <p className="text-sm font-semibold text-text-primary">Last 5 failed runs</p>
                <p className="text-xs text-text-secondary">
                  Scheduled failures are highlighted because they happen while nobody is watching.
                </p>
              </div>
              <Link
                href="/runs"
                className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-hover"
              >
                Open runs
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </CardHeader>
            <CardBody className="space-y-3">
              {summary.recentFailedRuns.length > 0 ? (
                summary.recentFailedRuns.map((run) => {
                  const scheduled = isScheduledRun(run);
                  return (
                    <Link
                      key={run.run_id}
                      href={`/runs/${run.run_id}` as Route}
                      className={cn(
                        "block rounded-2xl border px-4 py-3 transition hover:border-border-focus",
                        scheduled
                          ? "border-warn-border bg-warn-bg/70"
                          : "border-border bg-bg-elevated/60"
                      )}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-text-primary">{run.run_id}</p>
                            <StatusBadge value={run.state} />
                            {scheduled ? <StatusBadge value="warn" label="scheduled" /> : null}
                          </div>
                          <p className="text-xs text-text-secondary">
                            {formatDashboardDateTime(run.created_at)}
                            {run.schedule_id ? ` · ${scheduleNameById[run.schedule_id] ?? run.schedule_id}` : ""}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">
                            Trigger
                          </p>
                          <p className="mt-1 text-sm text-text-primary">{run.trigger_source}</p>
                        </div>
                      </div>
                    </Link>
                  );
                })
              ) : (
                <p className="text-sm text-text-secondary">No failed runs are currently available.</p>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          {canViewProviderQuota ? (
            <Card>
              <CardHeader>
                <div>
                  <p className="text-sm font-semibold text-text-primary">Quota and usage</p>
                  <p className="text-xs text-text-secondary">
                    Real provider headroom where quotas exist, and usage-only partial states where policy is not configured yet.
                  </p>
                </div>
              </CardHeader>
              <CardBody className="space-y-3">
                {quotaLoading ? (
                  <div className="animate-pulse space-y-3">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="h-16 rounded-lg bg-bg-surface-raised" />
                    ))}
                  </div>
                ) : (
                  <>
                    <ProviderQuotaWarningPanel summary={quotaWarningSummary} />
                    {quotaSections.map((section) => (
                      <ProviderQuotaSectionCard key={section.key} section={section} />
                    ))}
                  </>
                )}
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <div>
                <p className="text-sm font-semibold text-text-primary">Platform health</p>
                <p className="text-xs text-text-secondary">
                  Compact reassurance for tenant-visible platform readiness.
                </p>
              </div>
            </CardHeader>
            <CardBody className="space-y-3">
              {healthItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-bg-elevated/60 px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{item.label}</p>
                    <p className="text-xs text-text-secondary">{item.detail}</p>
                  </div>
                  <StatusBadge value={item.tone} label={item.status} />
                </div>
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <p className="text-sm font-semibold text-text-primary">Quick actions</p>
                <p className="text-xs text-text-secondary">
                  Jump straight to the surfaces most likely to need attention next.
                </p>
              </div>
            </CardHeader>
            <CardBody className="space-y-2">
              {QUICK_LINKS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-start justify-between gap-3 rounded-2xl border border-border bg-bg-elevated/60 px-4 py-3 transition hover:border-border-focus"
                >
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{item.label}</p>
                    <p className="mt-1 text-xs leading-5 text-text-secondary">{item.description}</p>
                  </div>
                  <ArrowRight className="mt-0.5 h-4 w-4 text-text-muted" />
                </Link>
              ))}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function LegendSwatch({ label, tone }: { label: string; tone: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn("h-2.5 w-2.5 rounded-full", tone)} />
      <span>{label}</span>
    </span>
  );
}

function MetricPill({
  icon: Icon,
  label,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-surface px-3 py-1.5">
      <Icon className="h-3.5 w-3.5 text-brand" />
      <span>{label}</span>
    </span>
  );
}

function MetricBlock({
  icon: Icon,
  label,
  value,
  subtext,
  tone,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  subtext: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-bg-elevated/60 p-4">
      <div className="flex items-center gap-2 text-text-secondary">
        <Icon className="h-4 w-4 text-brand" />
        <p className="text-xs uppercase tracking-[0.16em]">{label}</p>
      </div>
      <p className={cn("mt-3 text-3xl font-semibold text-text-primary", tone)}>{value}</p>
      <p className="mt-1 text-xs leading-5 text-text-secondary">{subtext}</p>
    </div>
  );
}
