"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Activity, PencilLine, Plus, RefreshCw, Router, Users, Waypoints, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AccessPanel } from "@/components/auth/access-panel";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import {
  addAdminSipPoolMember,
  assignAdminSipPool,
  createAdminSipPool,
  patchAdminSipPoolAssignment,
  patchAdminSipPool,
  removeAdminSipPoolMember,
  revokeAdminSipPool,
  syncAdminSipTrunks,
  useAdminSipPools,
  useAdminSipTrunks,
  useAdminTenants,
} from "@/lib/api";
import type {
  AdminSIPTrunkPoolsListResponse,
  AdminSIPTrunksListResponse,
} from "@/lib/api/types";
import { useDashboardAccess } from "@/lib/current-user";

type Trunk = AdminSIPTrunksListResponse["items"][number];
type Pool = AdminSIPTrunkPoolsListResponse["items"][number];
type PoolAssignment = {
  tenant_id: string;
  tenant_label: string;
  is_default: boolean;
  is_active: boolean;
  max_channels?: number | null;
  reserved_channels?: number | null;
};
type AssignmentInput = {
  tenantId: string;
  tenantLabel: string;
  maxChannels: string;
  reservedChannels: string;
};
type AssignmentDraft = {
  tenantLabel: string;
  isDefault: boolean;
  isActive: boolean;
  maxChannels: string;
  reservedChannels: string;
};
type EditTabKey = "overview" | "trunks" | "assignments";
type ModalState =
  | { mode: "create" }
  | { mode: "edit"; trunkPoolId: string }
  | null;

const EMPTY_ASSIGNMENT_INPUT: AssignmentInput = {
  tenantId: "",
  tenantLabel: "",
  maxChannels: "",
  reservedChannels: "",
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function toPoolAssignment(raw: NonNullable<Pool["assignments"]>[number]): PoolAssignment {
  return {
    tenant_id: raw.tenant_id,
    tenant_label: raw.tenant_label ?? "",
    is_default: raw.is_default ?? false,
    is_active: raw.is_active ?? true,
    max_channels: raw.max_channels,
    reserved_channels: raw.reserved_channels,
  };
}

function sortTrunks(trunks: Trunk[]): Trunk[] {
  return [...trunks].sort((left, right) => {
    const providerCompare = (left.provider_name ?? "").localeCompare(right.provider_name ?? "");
    if (providerCompare !== 0) return providerCompare;
    return (left.name ?? left.trunk_id).localeCompare(right.name ?? right.trunk_id);
  });
}

function toggleSelectedValue(values: string[], nextValue: string): string[] {
  return values.includes(nextValue)
    ? values.filter((value) => value !== nextValue)
    : [...values, nextValue];
}

function parseOptionalIntegerInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function isValidOptionalIntegerInput(value: string, minimum: number): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (!/^\d+$/.test(trimmed)) return false;
  return Number.parseInt(trimmed, 10) >= minimum;
}

function formatAssignmentQuotaSummary(assignment: PoolAssignment): string {
  if (assignment.max_channels == null && assignment.reserved_channels == null) {
    return "No channel quota set";
  }
  return `Max ${assignment.max_channels ?? "—"} · Reserved ${assignment.reserved_channels ?? "—"}`;
}

function SipStatPill({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof Activity;
}) {
  return (
    <div className="inline-flex min-w-[8.5rem] items-center gap-3 rounded-2xl border border-border bg-bg-base/80 px-3 py-2.5">
      <div className="rounded-xl border border-border bg-bg-surface p-1.5">
        <Icon className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">{label}</p>
        <p className="text-sm font-semibold text-text-primary">{value}</p>
      </div>
    </div>
  );
}

function SyncedTrunksDialog({
  open,
  onOpenChange,
  trunks,
  total,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trunks: Trunk[];
  total: number;
  error: Error | undefined;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(94vw,52rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                Synced bridge trunks
              </Dialog.Title>
              <Dialog.Description className="max-w-2xl text-sm text-text-secondary">
                Review the current trunk inventory synced from the WebRTC SIP bridge.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close synced trunks"
                className="rounded-md border border-border bg-bg-base p-2 text-text-muted transition-colors hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mt-5 rounded-2xl border border-border bg-bg-base px-4 py-3 text-sm text-text-secondary">
            {trunks.filter((trunk) => trunk.is_active).length}/{total} active trunks
          </div>

          <div className="mt-4 space-y-3">
            {error ? (
              <TableState kind="error" title="Failed to load SIP trunks" message={error.message} columns={1} />
            ) : total === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                No synced trunks yet.
              </div>
            ) : (
              trunks.map((trunk) => {
                const trunkNumbers = trunk.numbers ?? [];
                return (
                  <div key={trunk.trunk_id} className="rounded-xl border border-border bg-bg-elevated px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-text-primary">
                          {trunk.name ?? trunk.trunk_id}
                        </p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {trunk.provider_name ?? "Unknown provider"} · {trunk.address ?? "No address"}
                        </p>
                      </div>
                      <StatusBadge
                        value={trunk.is_active ? "pass" : "fail"}
                        label={trunk.is_active ? "active" : "inactive"}
                      />
                    </div>
                    <p className="mt-2 font-mono text-[11px] text-text-muted">{trunk.trunk_id}</p>
                    <div className="mt-3 grid gap-2 text-xs text-text-secondary">
                      <p>Numbers: {trunkNumbers.length > 0 ? trunkNumbers.join(", ") : "—"}</p>
                      <p>Last synced: {formatDateTime(trunk.last_synced_at)}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PoolEditorDialog({
  open,
  mode,
  pool,
  trunks,
  poolName,
  setPoolName,
  selectedTrunkIds,
  setSelectedTrunkIds,
  tenants,
  busyKey,
  onOpenChange,
  onSave,
  onAssignTenant,
  onPatchAssignment,
  onRevokeTenant,
}: {
  open: boolean;
  mode: "create" | "edit";
  pool: Pool | null;
  trunks: Trunk[];
  poolName: string;
  setPoolName: (value: string) => void;
  selectedTrunkIds: string[];
  setSelectedTrunkIds: (value: string[]) => void;
  tenants: Array<{ tenant_id: string; display_name: string }>;
  busyKey: string | null;
  onOpenChange: (open: boolean) => void;
  onSave: () => void;
  onAssignTenant: (input: AssignmentInput) => Promise<void>;
  onPatchAssignment: (tenantId: string, draft: AssignmentDraft) => Promise<void>;
  onRevokeTenant: (tenantId: string) => void;
}) {
  const isCreate = mode === "create";
  const [activeTab, setActiveTab] = useState<EditTabKey>("overview");
  const [assignmentInput, setAssignmentInput] = useState<AssignmentInput>(EMPTY_ASSIGNMENT_INPUT);
  const [editingAssignmentTenantId, setEditingAssignmentTenantId] = useState<string | null>(null);
  const [assignmentDraft, setAssignmentDraft] = useState<AssignmentDraft | null>(null);

  const selectedProvider = useMemo(() => {
    const providerSource =
      selectedTrunkIds
        .map((trunkId) => trunks.find((trunk) => trunk.trunk_id === trunkId)?.provider_name?.trim())
        .find((provider) => provider) ?? "";
    return isCreate ? providerSource : pool?.provider_name ?? "";
  }, [isCreate, pool?.provider_name, selectedTrunkIds, trunks]);

  const visibleTrunks = useMemo(() => {
    if (isCreate) {
      return sortTrunks(trunks.filter((trunk) => trunk.is_active && trunk.provider_name));
    }
    const providerName = pool?.provider_name ?? "";
    return sortTrunks(
      trunks.filter(
        (trunk) =>
          trunk.provider_name === providerName &&
          (trunk.is_active || selectedTrunkIds.includes(trunk.trunk_id))
      )
    );
  }, [isCreate, pool?.provider_name, selectedTrunkIds, trunks]);

  const selectedCount = selectedTrunkIds.length;
  const assignments = (pool?.assignments ?? []).map(toPoolAssignment);
  const saveBusy = busyKey === "save-pool";
  const assignBusy = busyKey === "assign-pool";
  const selectedTenant =
    tenants.find((tenant) => tenant.tenant_id === assignmentInput.tenantId) ?? null;
  const assignmentInputValid =
    Boolean(assignmentInput.tenantId) &&
    isValidOptionalIntegerInput(assignmentInput.maxChannels, 1) &&
    isValidOptionalIntegerInput(assignmentInput.reservedChannels, 0);
  const assignmentDraftValid =
    assignmentDraft != null &&
    isValidOptionalIntegerInput(assignmentDraft.maxChannels, 1) &&
    isValidOptionalIntegerInput(assignmentDraft.reservedChannels, 0);

  useEffect(() => {
    if (!open) return;
    setActiveTab("overview");
    setAssignmentInput(EMPTY_ASSIGNMENT_INPUT);
    setEditingAssignmentTenantId(null);
    setAssignmentDraft(null);
  }, [open, pool?.trunk_pool_id]);

  function beginEditAssignment(assignment: PoolAssignment) {
    setEditingAssignmentTenantId(assignment.tenant_id);
    setAssignmentDraft({
      tenantLabel: assignment.tenant_label,
      isDefault: assignment.is_default,
      isActive: assignment.is_active,
      maxChannels: assignment.max_channels == null ? "" : String(assignment.max_channels),
      reservedChannels: assignment.reserved_channels == null ? "" : String(assignment.reserved_channels),
    });
  }

  async function submitAssignment() {
    await onAssignTenant(assignmentInput);
    setAssignmentInput(EMPTY_ASSIGNMENT_INPUT);
  }

  async function submitAssignmentPatch() {
    if (!editingAssignmentTenantId || !assignmentDraft) return;
    await onPatchAssignment(editingAssignmentTenantId, assignmentDraft);
    setEditingAssignmentTenantId(null);
    setAssignmentDraft(null);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(94vw,56rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                {isCreate ? "Create trunk pool" : "Edit trunk pool"}
              </Dialog.Title>
              <Dialog.Description className="max-w-2xl text-sm text-text-secondary">
                {isCreate
                  ? "Create a same-provider pool and choose one or more active synced trunks to include."
                  : "Review the pool, manage trunks, and control tenant assignments from one place."}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close trunk pool editor"
                className="rounded-md border border-border bg-bg-base p-2 text-text-muted transition-colors hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {!isCreate ? (
            <div role="tablist" aria-label="Pool editor sections" className="mt-5 flex flex-wrap gap-2">
              {([
                ["overview", "Overview"],
                ["trunks", "Trunks"],
                ["assignments", "Assignments & Quotas"],
              ] as const).map(([key, label]) => {
                const active = activeTab === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActiveTab(key)}
                    aria-pressed={active}
                    className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                      active
                        ? "border-border-focus bg-bg-elevated text-text-primary"
                        : "border-border bg-bg-base text-text-secondary hover:border-border-focus hover:text-text-primary"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          ) : null}

          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
            <div className="space-y-5">
              {isCreate || activeTab === "overview" ? (
                <>
                  <div className="space-y-2">
                    <label htmlFor="sip-pool-name" className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                      Pool name
                    </label>
                    <input
                      id="sip-pool-name"
                      value={poolName}
                      onChange={(event) => setPoolName(event.target.value)}
                      className="w-full rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary"
                      placeholder="UK Outbound"
                    />
                  </div>

                  {!isCreate && pool ? (
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-2xl border border-border bg-bg-base p-4">
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
                          Pool
                        </p>
                        <p className="mt-3 text-sm font-semibold text-text-primary">{pool.name}</p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {pool.provider_name} · {pool.selection_policy}
                        </p>
                        <p className="mt-3 font-mono text-[11px] text-text-muted">{pool.trunk_pool_id}</p>
                      </div>
                      <div className="rounded-2xl border border-border bg-bg-base p-4">
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
                          Assignment
                        </p>
                        <p className="mt-3 text-sm font-semibold text-text-primary">
                          {assignments.length} tenant{assignments.length === 1 ? "" : "s"} assigned
                        </p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {selectedCount} trunk{selectedCount === 1 ? "" : "s"} in this pool
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {assignments.slice(0, 3).map((assignment) => (
                            <span
                              key={`${pool.trunk_pool_id}:${assignment.tenant_id}`}
                              className="rounded-full border border-border bg-bg-surface px-3 py-1.5 text-xs text-text-secondary"
                            >
                              {assignment.tenant_label}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}

              {isCreate || activeTab === "trunks" ? (
                <div className="rounded-2xl border border-border bg-bg-base">
                  <div className="border-b border-border px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">Pool trunks</p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {isCreate
                            ? "Select one provider, then choose one or more active trunks."
                            : "Keep the pool on one provider and adjust which synced trunks are included."}
                        </p>
                      </div>
                      <div className="text-right text-xs text-text-muted">
                        <p>{selectedCount} selected</p>
                        <p>{selectedProvider || "Choose trunks to set provider"}</p>
                      </div>
                    </div>
                  </div>
                  <div className="space-y-2 p-4">
                    {visibleTrunks.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-sm text-text-secondary">
                        {isCreate
                          ? "No active synced trunks are available yet. Sync trunks first."
                          : "No synced trunks are available for this provider."}
                      </div>
                    ) : (
                      visibleTrunks.map((trunk) => {
                        const checked = selectedTrunkIds.includes(trunk.trunk_id);
                        const disabled =
                          (isCreate &&
                            Boolean(selectedProvider) &&
                            trunk.provider_name !== selectedProvider &&
                            !checked) ||
                          (!isCreate && !trunk.is_active && !checked);
                        return (
                          <label
                            key={trunk.trunk_id}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition-colors ${
                              checked
                                ? "border-border-focus bg-bg-elevated"
                                : "border-border bg-bg-surface hover:border-border-focus"
                            } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={disabled}
                              onChange={() =>
                                setSelectedTrunkIds(toggleSelectedValue(selectedTrunkIds, trunk.trunk_id))
                              }
                              className="mt-1 h-4 w-4 rounded border-border text-text-primary"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-text-primary">
                                  {trunk.name ?? trunk.trunk_id}
                                </p>
                                <StatusBadge
                                  value={trunk.is_active ? "pass" : "fail"}
                                  label={trunk.is_active ? "active" : "inactive"}
                                />
                              </div>
                              <p className="mt-1 text-xs text-text-secondary">
                                {trunk.provider_name ?? "Unknown provider"} · {trunk.address ?? "No address"}
                              </p>
                              <p className="mt-1 font-mono text-[11px] text-text-muted">
                                {trunk.trunk_id}
                              </p>
                            </div>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>
              ) : null}

              {!isCreate && pool && activeTab === "assignments" ? (
                <div className="space-y-5">
                  <div className="rounded-2xl border border-border bg-bg-base">
                    <div className="border-b border-border px-4 py-3">
                      <p className="text-sm font-semibold text-text-primary">Assigned tenants</p>
                      <p className="mt-1 text-xs text-text-secondary">
                        Update labels, defaults, status, and channel quotas for each tenant assignment.
                      </p>
                    </div>
                    <div className="space-y-3 p-4">
                      {assignments.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-border px-3 py-4 text-sm text-text-secondary">
                          No tenant assignments yet.
                        </div>
                      ) : (
                        assignments.map((assignment) => {
                          const isEditing = editingAssignmentTenantId === assignment.tenant_id;
                          const updateBusy = busyKey === `assign-update-${assignment.tenant_id}`;
                          const revokeBusy = busyKey === `assign-remove-${assignment.tenant_id}`;
                          return (
                            <div
                              key={`${pool.trunk_pool_id}:${assignment.tenant_id}`}
                              className="rounded-xl border border-border bg-bg-surface px-4 py-4"
                            >
                              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="text-sm font-medium text-text-primary">
                                      {assignment.tenant_label}
                                    </p>
                                    {assignment.is_default ? (
                                      <span className="rounded-full border border-border bg-bg-elevated px-2.5 py-1 text-[11px] text-text-secondary">
                                        default
                                      </span>
                                    ) : null}
                                    <StatusBadge
                                      value={assignment.is_active ? "pass" : "warn"}
                                      label={assignment.is_active ? "active" : "inactive"}
                                    />
                                  </div>
                                  <p className="mt-1 text-xs text-text-secondary">
                                    {assignment.tenant_id}
                                  </p>
                                  <p className="mt-2 text-xs text-text-secondary">
                                    {formatAssignmentQuotaSummary(assignment)}
                                  </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() =>
                                      isEditing
                                        ? (setEditingAssignmentTenantId(null), setAssignmentDraft(null))
                                        : beginEditAssignment(assignment)
                                    }
                                    disabled={updateBusy || revokeBusy}
                                  >
                                    {isEditing ? "Cancel" : "Edit"}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => void onRevokeTenant(assignment.tenant_id)}
                                    disabled={revokeBusy || updateBusy}
                                  >
                                    Revoke
                                  </Button>
                                </div>
                              </div>

                              {isEditing && assignmentDraft ? (
                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                  <label htmlFor={`sip-draft-label-${assignment.tenant_id}`} className="space-y-1">
                                    <span className="text-xs text-text-muted">Tenant label</span>
                                    <input
                                      id={`sip-draft-label-${assignment.tenant_id}`}
                                      value={assignmentDraft.tenantLabel}
                                      onChange={(event) =>
                                        setAssignmentDraft({
                                          ...assignmentDraft,
                                          tenantLabel: event.target.value,
                                        })
                                      }
                                      className="w-full rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary"
                                    />
                                  </label>
                                  <label htmlFor={`sip-draft-max-${assignment.tenant_id}`} className="space-y-1">
                                    <span className="text-xs text-text-muted">Max channels</span>
                                    <input
                                      id={`sip-draft-max-${assignment.tenant_id}`}
                                      inputMode="numeric"
                                      value={assignmentDraft.maxChannels}
                                      onChange={(event) =>
                                        setAssignmentDraft({
                                          ...assignmentDraft,
                                          maxChannels: event.target.value,
                                        })
                                      }
                                      className="w-full rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary"
                                      placeholder="Optional"
                                    />
                                  </label>
                                  <label htmlFor={`sip-draft-reserved-${assignment.tenant_id}`} className="space-y-1">
                                    <span className="text-xs text-text-muted">Reserved channels</span>
                                    <input
                                      id={`sip-draft-reserved-${assignment.tenant_id}`}
                                      inputMode="numeric"
                                      value={assignmentDraft.reservedChannels}
                                      onChange={(event) =>
                                        setAssignmentDraft({
                                          ...assignmentDraft,
                                          reservedChannels: event.target.value,
                                        })
                                      }
                                      className="w-full rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary"
                                      placeholder="Optional"
                                    />
                                  </label>
                                  <div className="grid gap-2 sm:grid-cols-2">
                                    <label className="flex items-center gap-2 rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary">
                                      <input
                                        type="checkbox"
                                        checked={assignmentDraft.isDefault}
                                        onChange={(event) =>
                                          setAssignmentDraft({
                                            ...assignmentDraft,
                                            isDefault: event.target.checked,
                                          })
                                        }
                                        className="h-4 w-4 rounded border-border text-text-primary"
                                      />
                                      Default assignment
                                    </label>
                                    <label className="flex items-center gap-2 rounded-xl border border-border bg-bg-base px-3 py-2.5 text-sm text-text-primary">
                                      <input
                                        type="checkbox"
                                        checked={assignmentDraft.isActive}
                                        onChange={(event) =>
                                          setAssignmentDraft({
                                            ...assignmentDraft,
                                            isActive: event.target.checked,
                                          })
                                        }
                                        className="h-4 w-4 rounded border-border text-text-primary"
                                      />
                                      Active
                                    </label>
                                  </div>
                                  <div className="md:col-span-2 flex justify-end">
                                    <Button
                                      size="sm"
                                      onClick={() => void submitAssignmentPatch()}
                                      disabled={updateBusy || !assignmentDraftValid}
                                    >
                                      {updateBusy ? "Saving…" : "Save assignment"}
                                    </Button>
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-bg-base">
                    <div className="border-b border-border px-4 py-3">
                      <p className="text-sm font-semibold text-text-primary">Assign tenant</p>
                      <p className="mt-1 text-xs text-text-secondary">
                        Add a tenant to this pool and optionally set channel limits now.
                      </p>
                    </div>
                    <div className="grid gap-3 p-4 md:grid-cols-2">
                      <label htmlFor="sip-assign-tenant" className="space-y-1">
                        <span className="text-xs text-text-muted">Tenant</span>
                        <select
                          id="sip-assign-tenant"
                          value={assignmentInput.tenantId}
                          onChange={(event) =>
                            setAssignmentInput({
                              ...assignmentInput,
                              tenantId: event.target.value,
                              tenantLabel:
                                assignmentInput.tenantLabel ||
                                tenants.find((tenant) => tenant.tenant_id === event.target.value)?.display_name ||
                                "",
                            })
                          }
                          className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                        >
                          <option value="">Assign tenant…</option>
                          {tenants.map((tenant) => (
                            <option key={tenant.tenant_id} value={tenant.tenant_id}>
                              {tenant.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label htmlFor="sip-assign-label" className="space-y-1">
                        <span className="text-xs text-text-muted">Tenant label</span>
                        <input
                          id="sip-assign-label"
                          value={assignmentInput.tenantLabel}
                          onChange={(event) =>
                            setAssignmentInput({
                              ...assignmentInput,
                              tenantLabel: event.target.value,
                            })
                          }
                          className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                          placeholder={selectedTenant?.display_name ?? "Friendly tenant label"}
                        />
                      </label>
                      <label htmlFor="sip-assign-max-channels" className="space-y-1">
                        <span className="text-xs text-text-muted">Max channels</span>
                        <input
                          id="sip-assign-max-channels"
                          inputMode="numeric"
                          value={assignmentInput.maxChannels}
                          onChange={(event) =>
                            setAssignmentInput({
                              ...assignmentInput,
                              maxChannels: event.target.value,
                            })
                          }
                          className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                          placeholder="Optional"
                        />
                      </label>
                      <label htmlFor="sip-assign-reserved-channels" className="space-y-1">
                        <span className="text-xs text-text-muted">Reserved channels</span>
                        <input
                          id="sip-assign-reserved-channels"
                          inputMode="numeric"
                          value={assignmentInput.reservedChannels}
                          onChange={(event) =>
                            setAssignmentInput({
                              ...assignmentInput,
                              reservedChannels: event.target.value,
                            })
                          }
                          className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                          placeholder="Optional"
                        />
                      </label>
                      <div className="md:col-span-2 flex justify-end">
                        <Button
                          onClick={() => void submitAssignment()}
                          disabled={assignBusy || !assignmentInputValid}
                        >
                          {assignBusy ? "Assigning…" : "Assign tenant"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-2xl border border-border bg-bg-base p-4">
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                Summary
              </p>
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-border bg-bg-surface px-3 py-3">
                  <p className="text-xs text-text-muted">Provider</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {selectedProvider || "Choose trunks"}
                  </p>
                </div>
                <div className="rounded-xl border border-border bg-bg-surface px-3 py-3">
                  <p className="text-xs text-text-muted">Selected trunks</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{selectedCount}</p>
                </div>
                {!isCreate && pool ? (
                  <div className="rounded-xl border border-border bg-bg-surface px-3 py-3">
                    <p className="text-xs text-text-muted">Assigned tenants</p>
                    <p className="mt-1 text-sm font-medium text-text-primary">
                      {assignments.length}
                    </p>
                  </div>
                ) : null}
                {!isCreate && pool ? (
                  <div className="rounded-xl border border-border bg-bg-surface px-3 py-3">
                    <p className="text-xs text-text-muted">Pool ID</p>
                    <p className="mt-1 font-mono text-[11px] text-text-secondary">
                      {pool.trunk_pool_id}
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="mt-6 flex flex-col gap-2">
                {!isCreate && activeTab === "assignments" ? (
                  <p className="text-center text-xs text-text-muted">
                    Switch to Overview or Trunks to save pool changes.
                  </p>
                ) : (
                  <Button
                    onClick={() => void onSave()}
                    disabled={saveBusy || !poolName.trim() || !selectedProvider || selectedCount === 0 || editingAssignmentTenantId !== null}
                  >
                    {saveBusy ? "Saving…" : isCreate ? "Create pool" : "Save changes"}
                  </Button>
                )}
                <Dialog.Close asChild>
                  <Button variant="secondary">Cancel</Button>
                </Dialog.Close>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function AdminSipPage() {
  const { roleResolved, canAccessAdminSip } = useDashboardAccess();
  const { data: trunksData, error: trunksError, mutate: mutateTrunks } = useAdminSipTrunks(canAccessAdminSip);
  const { data: poolsData, error: poolsError, mutate: mutatePools } = useAdminSipPools(canAccessAdminSip);
  const { data: tenantsData } = useAdminTenants(200, 0, canAccessAdminSip);

  const [syncing, setSyncing] = useState(false);
  const [showTrunksModal, setShowTrunksModal] = useState(false);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [poolName, setPoolName] = useState("");
  const [selectedTrunkIds, setSelectedTrunkIds] = useState<string[]>([]);

  const trunks = trunksData?.items ?? [];
  const pools = poolsData?.items ?? [];
  const tenantItems = tenantsData?.items ?? [];
  const sortedTrunks = useMemo(() => sortTrunks(trunks), [trunks]);
  const tenantOptions = useMemo(
    () => tenantItems.map((tenant) => ({ tenant_id: tenant.tenant_id, display_name: tenant.display_name })),
    [tenantItems]
  );

  const editingPool = useMemo(() => {
    if (modalState?.mode !== "edit") return null;
    return pools.find((pool) => pool.trunk_pool_id === modalState.trunkPoolId) ?? null;
  }, [modalState, pools]);

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canAccessAdminSip) {
    return (
      <AccessPanel
        title="SIP Admin"
        message="SIP administration is restricted to system_admin."
      />
    );
  }

  async function refreshAll() {
    await Promise.all([mutateTrunks(), mutatePools()]);
  }

  function openCreateModal() {
    setPoolName("");
    setSelectedTrunkIds([]);
    setModalState({ mode: "create" });
  }

  function openEditModal(pool: Pool) {
    setPoolName(pool.name);
    setSelectedTrunkIds((pool.members ?? []).map((member) => member.trunk_id));
    setModalState({ mode: "edit", trunkPoolId: pool.trunk_pool_id });
  }

  function closeModal(nextOpen: boolean) {
    if (nextOpen) return;
    setModalState(null);
    setPoolName("");
    setSelectedTrunkIds([]);
  }

  async function handleSync() {
    setSyncing(true);
    setMessage("");
    setErrorMessage("");
    try {
      const result = await syncAdminSipTrunks();
      setMessage(`SIP sync complete. ${result.active}/${result.total} trunks active.`);
      await refreshAll();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to sync SIP trunks");
    } finally {
      setSyncing(false);
    }
  }

  async function handleSavePool() {
    setBusyKey("save-pool");
    setMessage("");
    setErrorMessage("");
    try {
      if (modalState?.mode === "create") {
        const selectedTrunks = trunks.filter((trunk) => selectedTrunkIds.includes(trunk.trunk_id));
        const providerName = selectedTrunks.find((trunk) => trunk.provider_name)?.provider_name ?? "";
        const createdPool = await createAdminSipPool({
          name: poolName,
          provider_name: providerName,
        });
        for (const trunkId of selectedTrunkIds) {
          await addAdminSipPoolMember(createdPool.trunk_pool_id, { trunk_id: trunkId, priority: 100 });
        }
        setMessage("Trunk pool created.");
      } else if (modalState?.mode === "edit" && editingPool) {
        if (poolName.trim() !== editingPool.name.trim()) {
          await patchAdminSipPool(editingPool.trunk_pool_id, { name: poolName.trim() });
        }
        const currentMemberIds = new Set((editingPool.members ?? []).map((member) => member.trunk_id));
        const nextMemberIds = new Set(selectedTrunkIds);
        for (const memberId of currentMemberIds) {
          if (!nextMemberIds.has(memberId)) {
            await removeAdminSipPoolMember(editingPool.trunk_pool_id, memberId);
          }
        }
        for (const memberId of nextMemberIds) {
          if (!currentMemberIds.has(memberId)) {
            await addAdminSipPoolMember(editingPool.trunk_pool_id, { trunk_id: memberId, priority: 100 });
          }
        }
        setMessage("Trunk pool updated.");
      }
      await mutatePools();
      setModalState(null);
      setPoolName("");
      setSelectedTrunkIds([]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to save trunk pool");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleAssignTenant(input: AssignmentInput) {
    if (!editingPool) return;
    if (!input.tenantId) return;
    setBusyKey("assign-pool");
    setErrorMessage("");
    try {
      await assignAdminSipPool(editingPool.trunk_pool_id, {
        tenant_id: input.tenantId,
        tenant_label: input.tenantLabel || undefined,
        is_default: false,
        max_channels: parseOptionalIntegerInput(input.maxChannels) ?? undefined,
        reserved_channels: parseOptionalIntegerInput(input.reservedChannels) ?? undefined,
      });
      await mutatePools();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to assign pool");
      throw err;
    } finally {
      setBusyKey(null);
    }
  }

  async function handlePatchAssignment(tenantId: string, draft: AssignmentDraft) {
    if (!editingPool) return;
    setBusyKey(`assign-update-${tenantId}`);
    setErrorMessage("");
    try {
      await patchAdminSipPoolAssignment(editingPool.trunk_pool_id, tenantId, {
        tenant_label: draft.tenantLabel || undefined,
        is_default: draft.isDefault,
        is_active: draft.isActive,
        max_channels: parseOptionalIntegerInput(draft.maxChannels),
        reserved_channels: parseOptionalIntegerInput(draft.reservedChannels),
      });
      await mutatePools();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to update assignment");
      throw err;
    } finally {
      setBusyKey(null);
    }
  }

  async function handleRevokeTenant(tenantId: string) {
    if (!editingPool) return;
    setBusyKey(`assign-remove-${tenantId}`);
    setErrorMessage("");
    try {
      await revokeAdminSipPool(editingPool.trunk_pool_id, tenantId);
      await mutatePools();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to revoke assignment");
      throw err;
    } finally {
      setBusyKey(null);
    }
  }

  const activeTrunkCount = trunks.filter((trunk) => trunk.is_active).length;
  const totalAssignments = pools.reduce(
    (count, pool) => count + (pool.assignments?.length ?? 0),
    0
  );

  return (
    <div className="space-y-6">
      <SyncedTrunksDialog
        open={showTrunksModal}
        onOpenChange={setShowTrunksModal}
        trunks={sortedTrunks}
        total={trunksData?.total ?? 0}
        error={trunksError}
      />

      <div className="relative overflow-hidden rounded-[1.5rem] border border-border bg-bg-surface">
        <div className="relative flex flex-col gap-4 px-5 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-text-primary">SIP Admin</h1>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-text-secondary">
                Manage trunk pools, review synced trunks, and control tenant access from one place.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <SipStatPill label="Trunks" value={String(trunksData?.total ?? 0)} icon={Router} />
            <SipStatPill label="Active" value={String(activeTrunkCount)} icon={Activity} />
            <SipStatPill label="Pools" value={String(pools.length)} icon={Waypoints} />
            <SipStatPill label="Assigned" value={String(totalAssignments)} icon={Users} />
          </div>
        </div>
      </div>

      {message ? <p className="text-sm text-pass">{message}</p> : null}
      {errorMessage ? <p className="text-sm text-fail">{errorMessage}</p> : null}

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border bg-bg-subtle/60">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-text-primary">Trunk Pools</h2>
              <p className="mt-1 text-xs text-text-secondary">
                Create shared pools from synced trunks and assign them to tenants.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 sm:ml-auto">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setShowTrunksModal(true)}
                disabled={!trunksData && !trunksError}
              >
                <Router className="mr-2 h-3.5 w-3.5" />
                Synced bridge trunks
                <span className="ml-2 rounded-full border border-border bg-bg-base px-2 py-0.5 text-[11px] text-text-muted">
                  {activeTrunkCount}/{trunksData?.total ?? 0}
                </span>
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void handleSync()} disabled={syncing}>
                <RefreshCw className="mr-2 h-3.5 w-3.5" />
                {syncing ? "Syncing…" : "Sync trunks"}
              </Button>
              <Button size="sm" onClick={openCreateModal}>
                <Plus className="mr-2 h-3.5 w-3.5" />
                Create pool
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardBody className="space-y-4 p-5">
          {poolsError ? (
            <TableState kind="error" title="Failed to load trunk pools" message={poolsError.message} columns={1} />
          ) : !poolsData ? (
            <TableState kind="loading" message="Loading trunk pools…" columns={1} rows={5} />
          ) : pools.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
              Start by creating a pool from one or more active bridge trunks.
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-border bg-bg-base">
              {pools.map((pool, index) => {
                const members = pool.members ?? [];
                const assignments = pool.assignments ?? [];
                const assignmentPreview = assignments.slice(0, 3);
                const hiddenAssignments = assignments.length - assignmentPreview.length;
                return (
                  <div
                    key={pool.trunk_pool_id}
                    className={`flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between ${
                      index > 0 ? "border-t border-border" : ""
                    }`}
                  >
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-text-primary">{pool.name}</p>
                        <StatusBadge
                          value={pool.is_active ? "pass" : "warn"}
                          label={pool.is_active ? "active" : "inactive"}
                        />
                        <span className="rounded-full border border-border bg-bg-elevated px-2.5 py-1 text-[11px] text-text-secondary">
                          {pool.provider_name}
                        </span>
                      </div>
                      <p className="text-xs text-text-secondary">
                        {pool.selection_policy} · {members.length} trunk{members.length === 1 ? "" : "s"} ·{" "}
                        {assignments.length} assigned tenant{assignments.length === 1 ? "" : "s"}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {assignmentPreview.length > 0 ? (
                          <>
                            {assignmentPreview.map((assignment) => (
                              <span
                                key={`${pool.trunk_pool_id}:${assignment.tenant_id}`}
                                className="rounded-full border border-border bg-bg-elevated px-3 py-1.5 text-xs text-text-secondary"
                              >
                                {assignment.tenant_label}
                              </span>
                            ))}
                            {hiddenAssignments > 0 ? (
                              <span className="rounded-full border border-border bg-bg-base px-3 py-1.5 text-xs text-text-muted">
                                +{hiddenAssignments} more
                              </span>
                            ) : null}
                          </>
                        ) : (
                          <span className="text-sm text-text-secondary">No tenants assigned yet.</span>
                        )}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-4 lg:ml-6">
                      <div className="grid min-w-[10rem] grid-cols-2 gap-3 rounded-xl border border-border bg-bg-surface px-3 py-3">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.14em] text-text-muted">Trunks</p>
                          <p className="mt-1 text-sm font-semibold text-text-primary">{members.length}</p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.14em] text-text-muted">Tenants</p>
                          <p className="mt-1 text-sm font-semibold text-text-primary">{assignments.length}</p>
                        </div>
                      </div>
                      <Button variant="secondary" size="sm" onClick={() => openEditModal(pool)}>
                        <PencilLine className="mr-2 h-4 w-4" />
                        Edit pool
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardBody>
      </Card>

      <PoolEditorDialog
        open={modalState !== null}
        mode={modalState?.mode ?? "create"}
        pool={editingPool}
        trunks={trunks}
        poolName={poolName}
        setPoolName={setPoolName}
        selectedTrunkIds={selectedTrunkIds}
        setSelectedTrunkIds={setSelectedTrunkIds}
        tenants={tenantOptions}
        busyKey={busyKey}
        onOpenChange={closeModal}
        onSave={handleSavePool}
        onAssignTenant={handleAssignTenant}
        onPatchAssignment={handlePatchAssignment}
        onRevokeTenant={handleRevokeTenant}
      />
    </div>
  );
}
