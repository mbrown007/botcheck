"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, Info, Siren } from "lucide-react";

import type { DashboardQuotaWarningSummary } from "@/components/dashboard/tenant-dashboard-data";
import { StatusBadge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ProviderQuotaWarningPanel({
  summary,
  testId,
}: {
  summary: DashboardQuotaWarningSummary;
  testId?: string;
}) {
  const Icon =
    summary.tone === "fail"
      ? Siren
      : summary.tone === "warn"
        ? AlertTriangle
        : summary.tone === "info"
          ? Info
          : CheckCircle2;
  const chrome =
    summary.tone === "fail"
      ? "border-fail-border bg-fail-bg/60"
      : summary.tone === "warn"
        ? "border-warn-border bg-warn-bg/60"
        : summary.tone === "info"
          ? "border-info-border bg-info-bg/50"
          : "border-pass-border bg-pass-bg/50";

  const liveRegion = summary.tone === "fail" ? "assertive" : "polite";

  return (
    <div
      role={summary.tone === "pass" ? "status" : "alert"}
      aria-live={liveRegion}
      data-testid={testId}
      className={cn("rounded-2xl border px-4 py-4", chrome)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Icon aria-hidden="true" className="h-4 w-4 text-text-primary" />
            <p className="text-sm font-semibold text-text-primary">{summary.title}</p>
          </div>
          <p className="text-xs leading-5 text-text-secondary">{summary.detail}</p>
        </div>
        <StatusBadge value={summary.tone} label={summary.badgeLabel} />
      </div>
      {summary.items.length > 0 ? (
        <div className="mt-4 space-y-2">
          {summary.items.map((item) => (
            <div
              key={item.key}
              className="rounded-xl border border-border/70 bg-bg-surface/70 px-3 py-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-text-primary">{item.title}</p>
                <StatusBadge value={item.tone} label={item.badgeLabel} />
              </div>
              <p className="mt-1 text-xs text-text-secondary">{item.detail}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
