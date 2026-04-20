"use client";

import { useState } from "react";
import { Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  updateAdminTenant,
  useAdminProviders,
} from "@/lib/api";
import type {
  AdminTenantSummaryResponse,
  AdminProviderSummaryResponse,
} from "@/lib/api/types";
import { ProviderAssignmentRow } from "./ProviderAssignmentRow";

// ── Constants ────────────────────────────────────────────────────────────────

const CAPABILITIES = ["llm", "tts", "stt", "sip"] as const;
type Capability = (typeof CAPABILITIES)[number];
type TenantTab = "general" | Capability;

const CAPABILITY_LABELS: Record<Capability, string> = {
  llm: "LLM",
  tts: "TTS",
  stt: "STT",
  sip: "SIP",
};

const QUOTA_METRICS: Record<Capability, { value: string; label: string }[]> = {
  llm: [
    { value: "input_tokens", label: "Input tokens / day" },
    { value: "output_tokens", label: "Output tokens / day" },
    { value: "requests", label: "Requests / day" },
  ],
  tts: [
    { value: "characters", label: "Characters / day" },
    { value: "requests", label: "Requests / day" },
  ],
  stt: [
    { value: "audio_seconds", label: "Audio seconds / day" },
    { value: "requests", label: "Requests / day" },
  ],
  sip: [{ value: "sip_minutes", label: "SIP minutes / day" }],
};

// ── TenantEditModal ──────────────────────────────────────────────────────────

export function TenantEditModal({
  tenant,
  onUpdated,
  onClose,
}: {
  tenant: AdminTenantSummaryResponse;
  onUpdated: (tenant: AdminTenantSummaryResponse) => void | Promise<void>;
  onClose: () => void;
}) {
  const { data: providersData } = useAdminProviders(true);
  const providers = providersData?.items ?? [];

  const [activeTab, setActiveTab] = useState<TenantTab>("general");
  const [displayName, setDisplayName] = useState(tenant.display_name);
  const [generalBusy, setGeneralBusy] = useState(false);
  const [generalMessage, setGeneralMessage] = useState("");
  const [generalError, setGeneralError] = useState("");

  const byCapability = Object.fromEntries(
    CAPABILITIES.map((cap) => [
      cap,
      providers.filter((p) => p.capability === cap),
    ])
  ) as Record<Capability, AdminProviderSummaryResponse[]>;

  const activeTabs = CAPABILITIES.filter(
    (cap) => byCapability[cap].length > 0
  );
  const capabilityTabs = activeTabs;
  const tabProviders =
    activeTab === "general" ? [] : (byCapability[activeTab] ?? []);

  async function saveGeneral() {
    setGeneralBusy(true);
    setGeneralMessage("");
    setGeneralError("");
    try {
      const updated = await updateAdminTenant(tenant.tenant_id, {
        display_name: displayName,
      });
      await onUpdated(updated);
      setDisplayName(updated.display_name);
      setGeneralMessage("Tenant details updated.");
    } catch (error) {
      setGeneralError(
        error instanceof Error ? error.message : "Failed to update tenant"
      );
    } finally {
      setGeneralBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative z-10 flex max-h-[85vh] w-full max-w-2xl flex-col rounded-[1.5rem] border border-border bg-bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              {displayName}
            </h2>
            <p className="mt-0.5 font-mono text-xs text-text-muted">
              {tenant.tenant_id}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border px-6 pt-3">
          <button
            type="button"
            onClick={() => setActiveTab("general")}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === "general"
                ? "border border-b-0 border-border bg-bg-elevated text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            General
          </button>
          {capabilityTabs.map((cap) => (
            <button
              key={cap}
              type="button"
              onClick={() => setActiveTab(cap)}
              className={`rounded-t-lg px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === cap
                  ? "border border-b-0 border-border bg-bg-elevated text-text-primary"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {CAPABILITY_LABELS[cap]}
              <span className="ml-1.5 text-[11px] text-text-muted">
                ({byCapability[cap].length})
              </span>
            </button>
          ))}
        </div>

        {/* Tab body */}
        <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
          {activeTab === "general" ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block space-y-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                    Display Name
                  </span>
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    className="h-10 w-full rounded-md border border-border bg-bg-elevated px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                    placeholder="Tenant display name"
                  />
                </label>
                <div className="space-y-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                    Tenant ID
                  </span>
                  <div className="flex h-10 items-center rounded-md border border-border bg-bg-elevated px-3 font-mono text-sm text-text-secondary">
                    {tenant.tenant_id}
                  </div>
                </div>
              </div>
              <p className="text-sm text-text-secondary">
                Update the tenant name used across the dashboard, login, and admin surfaces.
              </p>
              {generalMessage ? (
                <p className="text-sm text-pass">{generalMessage}</p>
              ) : null}
              {generalError ? (
                <p className="text-sm text-fail">{generalError}</p>
              ) : null}
              <div className="flex justify-end">
                <Button
                  onClick={() => void saveGeneral()}
                  disabled={generalBusy || !displayName.trim() || displayName.trim() === tenant.display_name}
                >
                  <Save className="h-3.5 w-3.5" />
                  {generalBusy ? "Saving…" : "Save Changes"}
                </Button>
              </div>
            </div>
          ) : !providersData ? (
            <p className="text-sm text-text-muted">Loading providers…</p>
          ) : tabProviders.length === 0 ? (
            <p className="text-sm text-text-secondary">
              No {CAPABILITY_LABELS[activeTab]} providers in the catalogue.
            </p>
          ) : (
            tabProviders.map((provider) => (
              <ProviderAssignmentRow
                key={provider.provider_id}
                provider={provider}
                tenantId={tenant.tenant_id}
                metrics={QUOTA_METRICS[activeTab]}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-border px-6 py-4">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
