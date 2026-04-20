"use client";

import { useState } from "react";
import { ArrowRightLeft, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import {
  assignAdminTenantProvider,
  deleteAdminTenantProviderAssignment,
  upsertAdminProviderQuotaPolicy,
  deleteAdminProviderQuotaPolicy,
  useAdminProviderAssignments,
  useAdminProviderQuotaPolicies,
} from "@/lib/api";
import type { AdminProviderSummaryResponse } from "@/lib/api/types";

export interface ProviderQuotaMetric {
  value: string;
  label: string;
}

export function ProviderAssignmentRow({
  provider,
  tenantId,
  metrics,
}: {
  provider: AdminProviderSummaryResponse;
  tenantId: string;
  metrics: ProviderQuotaMetric[];
}) {
  const [assignedToTenant, setAssignedToTenant] = useState(
    provider.assigned_tenant?.tenant_id === tenantId
  );
  const { data: assignmentsData, mutate: mutateAssignments } =
    useAdminProviderAssignments(provider.provider_id, assignedToTenant);
  const { data: quotaData, mutate: mutateQuotas } =
    useAdminProviderQuotaPolicies(provider.provider_id, assignedToTenant);

  const myAssignment =
    assignedToTenant
      ? assignmentsData?.items.find((a) => a.tenant_id === tenantId) ?? null
      : null;
  const myQuotas =
    assignedToTenant
      ? quotaData?.items.filter((p) => p.tenant_id === tenantId) ?? []
      : [];

  const [busy, setBusy] = useState<string | null>(null);
  const [quotaEdits, setQuotaEdits] = useState<
    Record<string, { limit: string; soft: string }>
  >({});
  const [rowError, setRowError] = useState("");

  async function toggleAssign() {
    setBusy("assign");
    setRowError("");
    try {
      if (assignedToTenant) {
        await deleteAdminTenantProviderAssignment(tenantId, provider.provider_id);
        setAssignedToTenant(false);
        // hooks are now disabled; no mutate needed
      } else {
        await assignAdminTenantProvider(tenantId, {
          provider_id: provider.provider_id,
          is_default: false,
        });
        setAssignedToTenant(true);
        // hooks just became enabled; SWR will auto-fetch on re-enable
        await mutateAssignments();
      }
    } catch (e) {
      setRowError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function setDefault(isDefault: boolean) {
    setBusy("default");
    setRowError("");
    try {
      await assignAdminTenantProvider(tenantId, {
        provider_id: provider.provider_id,
        is_default: isDefault,
      });
      await mutateAssignments();
    } catch (e) {
      setRowError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveQuota(metric: string) {
    const edit = quotaEdits[metric];
    if (!edit) return;
    setBusy(`quota-${metric}`);
    setRowError("");
    try {
      await upsertAdminProviderQuotaPolicy(provider.provider_id, {
        tenant_id: tenantId,
        metric,
        limit_per_day: Number(edit.limit),
        soft_limit_pct: Number(edit.soft),
      });
      setQuotaEdits((prev) => {
        const next = { ...prev };
        delete next[metric];
        return next;
      });
      await mutateQuotas();
    } catch (e) {
      setRowError(e instanceof Error ? e.message : "Failed to save quota");
    } finally {
      setBusy(null);
    }
  }

  async function removeQuota(metric: string) {
    setBusy(`remove-quota-${metric}`);
    setRowError("");
    try {
      await deleteAdminProviderQuotaPolicy(provider.provider_id, tenantId, metric);
      await mutateQuotas();
    } catch (e) {
      setRowError(e instanceof Error ? e.message : "Failed to remove quota");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className={`rounded-2xl border p-4 space-y-3 transition-colors ${
        assignedToTenant
          ? "border-border bg-bg-elevated/60"
          : "border-border/60 bg-bg-base"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">
              {provider.vendor}:{provider.model}
            </p>
            <StatusBadge
              value={provider.available ? "pass" : "fail"}
              label={provider.availability_status.replaceAll("_", " ")}
            />
            {myAssignment?.is_default && (
              <StatusBadge value="pass" label="default" />
            )}
          </div>
          <p className="mt-0.5 text-xs text-text-secondary">
            {provider.runtime_scopes.join(" · ")}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {myAssignment && (
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-text-secondary">
              <input
                type="checkbox"
                checked={myAssignment.is_default}
                disabled={busy === "default"}
                onChange={(e) => void setDefault(e.target.checked)}
              />
              Default
            </label>
          )}
          <Button
            size="sm"
            variant={assignedToTenant ? "destructive" : "secondary"}
            disabled={busy === "assign"}
            onClick={() => void toggleAssign()}
          >
            <ArrowRightLeft className="h-3.5 w-3.5" />
            {busy === "assign" ? "…" : assignedToTenant ? "Revoke" : "Assign"}
          </Button>
        </div>
      </div>

      {assignedToTenant && (
        <div className="space-y-2 border-t border-border pt-3">
          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
            Quota limits
          </p>
          {metrics.map((metric) => {
            const existing = myQuotas.find((q) => q.metric === metric.value);
            const edit = quotaEdits[metric.value];
            return (
              <div
                key={metric.value}
                className="flex flex-wrap items-center gap-2"
              >
                <span className="w-36 shrink-0 text-xs text-text-secondary">
                  {metric.label}
                </span>
                {edit ? (
                  <>
                    <input
                      type="number"
                      min={0}
                      value={edit.limit}
                      onChange={(e) =>
                        setQuotaEdits((prev) => ({
                          ...prev,
                          [metric.value]: {
                            ...prev[metric.value],
                            limit: e.target.value,
                          },
                        }))
                      }
                      placeholder="Daily limit"
                      className="w-28 rounded-lg border border-border bg-bg-surface px-2.5 py-1.5 text-xs text-text-primary"
                    />
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={edit.soft}
                      onChange={(e) =>
                        setQuotaEdits((prev) => ({
                          ...prev,
                          [metric.value]: {
                            ...prev[metric.value],
                            soft: e.target.value,
                          },
                        }))
                      }
                      placeholder="Soft %"
                      className="w-20 rounded-lg border border-border bg-bg-surface px-2.5 py-1.5 text-xs text-text-primary"
                    />
                    <Button
                      size="sm"
                      onClick={() => void saveQuota(metric.value)}
                      disabled={busy === `quota-${metric.value}`}
                    >
                      {busy === `quota-${metric.value}` ? "Saving…" : "Save"}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        setQuotaEdits((prev) => {
                          const next = { ...prev };
                          delete next[metric.value];
                          return next;
                        })
                      }
                    >
                      Cancel
                    </Button>
                  </>
                ) : existing ? (
                  <>
                    <span className="text-xs font-medium text-text-primary">
                      {existing.limit_per_day.toLocaleString()}
                    </span>
                    <span className="text-xs text-text-muted">
                      {existing.soft_limit_pct}% soft
                    </span>
                    <button
                      className="text-xs text-brand hover:underline"
                      onClick={() =>
                        setQuotaEdits((prev) => ({
                          ...prev,
                          [metric.value]: {
                            limit: String(existing.limit_per_day),
                            soft: String(existing.soft_limit_pct),
                          },
                        }))
                      }
                    >
                      Edit
                    </button>
                    <button
                      className="text-xs text-fail hover:underline disabled:opacity-50"
                      onClick={() => void removeQuota(metric.value)}
                      disabled={busy === `remove-quota-${metric.value}`}
                    >
                      <Trash2 className="inline h-3 w-3" />
                    </button>
                  </>
                ) : (
                  <button
                    className="text-xs text-brand hover:underline"
                    onClick={() =>
                      setQuotaEdits((prev) => ({
                        ...prev,
                        [metric.value]: { limit: "10000", soft: "80" },
                      }))
                    }
                  >
                    + Set limit
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {rowError && <p className="text-xs text-fail">{rowError}</p>}
    </div>
  );
}
