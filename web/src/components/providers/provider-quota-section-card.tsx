"use client";

import React from "react";
import type { ComponentType } from "react";
import { Activity, PhoneCall, Sparkles } from "lucide-react";

import type { DashboardQuotaSection } from "@/components/dashboard/tenant-dashboard-data";
import { StatusBadge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ProviderQuotaSectionCard({
  section,
}: {
  section: DashboardQuotaSection;
}) {
  const iconBySection: Record<DashboardQuotaSection["key"], ComponentType<{ className?: string }>> = {
    llm: Sparkles,
    speech: Activity,
    sip: PhoneCall,
  };
  const Icon = iconBySection[section.key] ?? Activity;

  return (
    <div className="rounded-2xl border border-border bg-bg-elevated/60 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-brand" />
          <p className="text-sm font-semibold text-text-primary">{section.title}</p>
        </div>
        <StatusBadge value={section.badgeValue} label={section.badgeLabel} />
      </div>
      <p className="mt-3 text-xs leading-5 text-text-secondary">{section.description}</p>
      {section.entries.length > 0 ? (
        <div className="mt-4 space-y-3">
          {section.entries.map((entry) => (
            <div
              key={`${section.key}:${entry.providerId}:${entry.metricLabel}`}
              className="rounded-xl border border-border bg-bg-surface/80 px-3 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-text-primary">{entry.providerLabel}</p>
                    <StatusBadge value={entry.status} label={entry.badgeLabel} />
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">{entry.metricLabel}</p>
                </div>
                <p className="text-sm font-medium text-text-primary">{entry.usageLabel}</p>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-bg-elevated">
                <div
                  className={cn(
                    "h-full rounded-full",
                    entry.status === "fail"
                      ? "bg-gradient-to-r from-fail/80 to-fail"
                      : entry.status === "warn"
                        ? "bg-gradient-to-r from-warn/70 to-warn"
                        : entry.source === "usage"
                          ? "bg-gradient-to-r from-brand/50 to-brand/70"
                          : "bg-gradient-to-r from-pass/70 to-brand/80"
                  )}
                  style={{ width: `${entry.progressPct}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-text-secondary">{entry.detail}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-border bg-bg-surface/70 px-3 py-4">
          <p className="text-sm text-text-secondary">{section.emptyMessage}</p>
        </div>
      )}
    </div>
  );
}
