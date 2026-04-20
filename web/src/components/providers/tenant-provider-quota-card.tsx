"use client";

import React from "react";
import { Boxes, ShieldCheck, TimerReset } from "lucide-react";

import {
  buildDashboardQuotaSections,
  buildDashboardQuotaWarningSummary,
  formatDashboardDateTime,
} from "@/components/dashboard/tenant-dashboard-data";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import type {
  ProviderAvailabilitySummaryResponse,
  TenantProviderQuotaListResponse,
  TenantProviderUsageListResponse,
} from "@/lib/api";
import { ProviderQuotaSectionCard } from "./provider-quota-section-card";
import { ProviderQuotaWarningPanel } from "./provider-quota-warning-panel";

function formatWindowLabel(
  quota?: TenantProviderQuotaListResponse,
  usage?: TenantProviderUsageListResponse
): string {
  const start = quota?.window_start ?? usage?.window_start;
  const end = quota?.window_end ?? usage?.window_end;
  if (!start || !end) {
    return "Rolling 24-hour window";
  }
  return `${formatDashboardDateTime(start)} to ${formatDashboardDateTime(end)}`;
}

function countUsageWithoutQuota(
  quota?: TenantProviderQuotaListResponse,
  usage?: TenantProviderUsageListResponse
): number {
  const quotaKeys = new Set(
    (quota?.items ?? []).map((item) => `${item.provider_id}:${item.capability}`)
  );
  return (usage?.items ?? []).filter(
    (item) => !quotaKeys.has(`${item.provider_id}:${item.capability}`)
  ).length;
}

function summaryValue(value: number, singular: string, plural: string): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

export function TenantProviderQuotaCard({
  quota,
  usage,
  availableProviders,
  loading = false,
  errorMessage = null,
  testId,
}: {
  quota?: TenantProviderQuotaListResponse;
  usage?: TenantProviderUsageListResponse;
  availableProviders?: ProviderAvailabilitySummaryResponse[];
  loading?: boolean;
  errorMessage?: string | null;
  testId?: string;
}) {
  const quotaSections = buildDashboardQuotaSections({ quota, usage, entryLimit: Infinity });
  const quotaWarningSummary = buildDashboardQuotaWarningSummary(quotaSections);
  const quotaCount = quota?.items.length ?? 0;
  const usageCount = usage?.items.length ?? 0;
  const usageWithoutQuota = countUsageWithoutQuota(quota, usage);
  const readyCount = availableProviders?.length ?? 0;

  return (
    <Card data-testid={testId}>
      <CardHeader>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Provider usage &amp; quotas</h2>
            <p className="mt-1 text-xs text-text-secondary">
              Tenant-level provider headroom and observed usage, using the same runtime-resolved provider model as dashboard, builder, playground, and evals.
            </p>
          </div>
          <div className="rounded-full border border-border bg-bg-elevated/70 px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-text-muted">
            {formatWindowLabel(quota, usage)}
          </div>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {errorMessage ? (
          <TableState kind="error" message={errorMessage} columns={1} />
        ) : loading ? (
          <TableState kind="loading" message="Loading provider usage and quotas…" columns={1} rows={4} />
        ) : (
          <>
            <div className="grid gap-3 lg:grid-cols-3">
              <div className="rounded-2xl border border-border bg-bg-elevated/60 px-4 py-4">
                <div className="flex items-center gap-2 text-text-secondary">
                  <ShieldCheck className="h-4 w-4 text-brand" />
                  <p className="text-xs uppercase tracking-[0.16em]">Quota-backed</p>
                </div>
                <p className="mt-3 text-3xl font-semibold text-text-primary">{quotaCount}</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">
                  {summaryValue(quotaCount, "policy", "policies")} configured against concrete provider capabilities.
                </p>
              </div>

              <div className="rounded-2xl border border-border bg-bg-elevated/60 px-4 py-4">
                <div className="flex items-center gap-2 text-text-secondary">
                  <Boxes className="h-4 w-4 text-brand" />
                  <p className="text-xs uppercase tracking-[0.16em]">Usage observed</p>
                </div>
                <p className="mt-3 text-3xl font-semibold text-text-primary">{usageCount}</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">
                  {summaryValue(usageCount, "provider lane", "provider lanes")} active in the current window.
                </p>
              </div>

              <div className="rounded-2xl border border-border bg-bg-elevated/60 px-4 py-4">
                <div className="flex items-center gap-2 text-text-secondary">
                  <TimerReset className="h-4 w-4 text-brand" />
                  <p className="text-xs uppercase tracking-[0.16em]">Needs policy</p>
                </div>
                <p className="mt-3 text-3xl font-semibold text-text-primary">{usageWithoutQuota}</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">
                  {summaryValue(usageWithoutQuota, "usage-only provider", "usage-only providers")} plus {summaryValue(readyCount, "runtime-ready assignment", "runtime-ready assignments")}.
                </p>
              </div>
            </div>

            <ProviderQuotaWarningPanel summary={quotaWarningSummary} testId="settings-provider-quota-warning-panel" />

            <div className="grid gap-4 xl:grid-cols-3">
              {quotaSections.map((section) => (
                <ProviderQuotaSectionCard key={section.key} section={section} />
              ))}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
