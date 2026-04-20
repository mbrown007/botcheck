"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Pencil, Plus } from "lucide-react";
import { AccessPanel } from "@/components/auth/access-panel";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import {
  createAdminTenant,
  deleteAdminTenant,
  reinstateAdminTenant,
  suspendAdminTenant,
  useAdminTenants,
} from "@/lib/api";
import type { AdminTenantSummaryResponse } from "@/lib/api/types";
import { useDashboardAccess } from "@/lib/current-user";
import { TenantEditModal } from "./tenant-edit-modal";

export default function AdminTenantsPage() {
  const { roleResolved, canAccessAdminTenants } = useDashboardAccess();
  const { data, error, mutate } = useAdminTenants(50, 0, canAccessAdminTenants);
  const [form, setForm] = useState({ tenant_id: "", slug: "", display_name: "" });
  const [creating, setCreating] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [editingTenant, setEditingTenant] = useState<AdminTenantSummaryResponse | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [tenantsOpen, setTenantsOpen] = useState(true);

  if (!roleResolved) {
    return (
      <div className="rounded-2xl border border-border bg-bg-surface p-6">
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
      </div>
    );
  }

  if (!canAccessAdminTenants) {
    return (
      <AccessPanel
        title="Tenant Admin"
        message="Platform tenant administration is restricted to system_admin."
      />
    );
  }

  async function handleCreate() {
    setCreating(true);
    setMessage("");
    setErrorMessage("");
    try {
      await createAdminTenant({
        ...form,
        feature_overrides: {},
        quota_config: {},
      });
      setForm({ tenant_id: "", slug: "", display_name: "" });
      setMessage("Tenant created.");
      await mutate();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create tenant");
    } finally {
      setCreating(false);
    }
  }

  async function runAction(key: string, action: () => Promise<unknown>, success: string) {
    setBusyKey(key);
    setMessage("");
    setErrorMessage("");
    try {
      await action();
      setMessage(success);
      await mutate();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Tenant action failed");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="space-y-6">
      {editingTenant && (
        <TenantEditModal
          tenant={editingTenant}
          onUpdated={async (updatedTenant) => {
            setEditingTenant(updatedTenant);
            await mutate();
          }}
          onClose={() => setEditingTenant(null)}
        />
      )}

      <div>
        <h1 className="text-xl font-semibold text-text-primary">Tenant Admin</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Platform-level tenant lifecycle, provider assignments, and quota configuration.
        </p>
      </div>

      <section className="overflow-hidden rounded-2xl border border-border bg-bg-surface">
        <button
          type="button"
          onClick={() => setCreateOpen((current) => !current)}
          className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-bg-elevated/40"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-bg-elevated text-text-secondary">
              <Plus className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Create Tenant</h2>
              <p className="text-xs text-text-secondary">
                Add a tenant with its ID, slug, and display name.
              </p>
            </div>
          </div>
          {createOpen ? (
            <ChevronDown className="h-4 w-4 text-text-muted" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden="true" />
          )}
        </button>
        {createOpen ? (
          <div className="border-t border-border px-5 py-5">
            <div className="grid gap-3 md:grid-cols-4">
              <input
                value={form.tenant_id}
                onChange={(event) =>
                  setForm((current) => ({ ...current, tenant_id: event.target.value }))
                }
                placeholder="tenant_id"
                className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
              />
              <input
                value={form.slug}
                onChange={(event) =>
                  setForm((current) => ({ ...current, slug: event.target.value }))
                }
                placeholder="tenant-slug"
                className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
              />
              <input
                value={form.display_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, display_name: event.target.value }))
                }
                placeholder="Display name"
                className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
              />
              <Button
                onClick={() => void handleCreate()}
                disabled={
                  creating ||
                  !form.tenant_id.trim() ||
                  !form.slug.trim() ||
                  !form.display_name.trim()
                }
              >
                {creating ? "Creating…" : "Create Tenant"}
              </Button>
            </div>
          </div>
        ) : null}
      </section>

      {message ? <p className="text-sm text-pass">{message}</p> : null}
      {errorMessage ? <p className="text-sm text-fail">{errorMessage}</p> : null}

      <section className="overflow-hidden rounded-2xl border border-border bg-bg-surface">
        <button
          type="button"
          onClick={() => setTenantsOpen((current) => !current)}
          className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-bg-elevated/40"
        >
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Tenants</h2>
            <p className="text-xs text-text-secondary">
              {data?.total ?? 0} configured across the platform.
            </p>
          </div>
          {tenantsOpen ? (
            <ChevronDown className="h-4 w-4 text-text-muted" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden="true" />
          )}
        </button>
        {tenantsOpen ? (
          <div className="border-t border-border">
            {error ? (
              <TableState kind="error" title="Failed to load tenants" message={error.message} columns={7} />
            ) : !data ? (
              <TableState kind="loading" message="Loading tenants…" columns={7} rows={5} />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                    <th className="px-5 py-3 font-medium">Tenant</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Users</th>
                    <th className="px-5 py-3 font-medium">Workloads</th>
                    <th className="hidden px-5 py-3 font-medium xl:table-cell">Quotas</th>
                    <th className="hidden px-5 py-3 font-medium xl:table-cell">Overrides</th>
                    <th className="px-5 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((tenant) => {
                    const isDeleted = Boolean(tenant.deleted_at);
                    const isSuspended = Boolean(tenant.suspended_at);
                    return (
                      <tr key={tenant.tenant_id} className="border-b border-border last:border-0">
                        <td className="px-5 py-3">
                          <div className="text-text-primary">{tenant.display_name}</div>
                          <div className="font-mono text-[11px] text-text-muted">
                            {tenant.tenant_id} · {tenant.slug}
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <StatusBadge
                            value={isDeleted ? "fail" : isSuspended ? "warn" : "pass"}
                            label={isDeleted ? "deleted" : isSuspended ? "suspended" : "active"}
                          />
                        </td>
                        <td className="px-5 py-3 text-text-secondary">
                          {tenant.active_users}/{tenant.total_users}
                        </td>
                        <td className="px-5 py-3 text-text-secondary">
                          {tenant.scenario_count} scenarios · {tenant.schedule_count} schedules · {tenant.pack_count} packs
                        </td>
                        <td className="hidden px-5 py-3 text-[11px] text-text-muted xl:table-cell">
                          runs {tenant.effective_quotas.max_concurrent_runs} · day {tenant.effective_quotas.max_runs_per_day}
                        </td>
                        <td className="hidden px-5 py-3 text-[11px] text-text-muted xl:table-cell">
                          {Object.keys(tenant.feature_overrides ?? {}).length} flags · {Object.keys(tenant.quota_config ?? {}).length} quota overrides
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex flex-wrap justify-end gap-2">
                            {!isDeleted && (
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => setEditingTenant(tenant)}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                                Edit
                              </Button>
                            )}
                            {!isDeleted && !isSuspended ? (
                              <Button
                                size="sm"
                                variant="secondary"
                                disabled={busyKey === `${tenant.tenant_id}:suspend`}
                                onClick={() =>
                                  void runAction(
                                    `${tenant.tenant_id}:suspend`,
                                    () => suspendAdminTenant(tenant.tenant_id),
                                    "Tenant suspended."
                                  )
                                }
                              >
                                Suspend
                              </Button>
                            ) : null}
                            {!isDeleted && isSuspended ? (
                              <Button
                                size="sm"
                                variant="secondary"
                                disabled={busyKey === `${tenant.tenant_id}:reinstate`}
                                onClick={() =>
                                  void runAction(
                                    `${tenant.tenant_id}:reinstate`,
                                    () => reinstateAdminTenant(tenant.tenant_id),
                                    "Tenant reinstated."
                                  )
                                }
                              >
                                Reinstate
                              </Button>
                            ) : null}
                            {!isDeleted ? (
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={busyKey === `${tenant.tenant_id}:delete`}
                                onClick={() =>
                                  void runAction(
                                    `${tenant.tenant_id}:delete`,
                                    () => deleteAdminTenant(tenant.tenant_id),
                                    "Tenant soft-deleted."
                                  )
                                }
                              >
                                Soft Delete
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}
