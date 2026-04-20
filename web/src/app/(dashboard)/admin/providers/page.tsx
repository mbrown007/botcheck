"use client";

import {
  Activity,
  ArrowRightLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AccessPanel } from "@/components/auth/access-panel";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import {
  assignAdminProvider,
  createAdminProvider,
  deleteAdminProvider,
  deleteAdminProviderAssignment,
  deleteAdminProviderCredential,
  deleteAdminProviderQuotaPolicy,
  updateAdminProvider,
  upsertAdminProviderCredential,
  upsertAdminProviderQuotaPolicy,
  useAdminProviderQuota,
  useAdminProviderQuotaPolicies,
  useAdminProviderUsage,
  useAdminProviders,
  useAdminTenants,
} from "@/lib/api";
import type {
  AdminProviderSummaryResponse,
  TenantProviderQuotaMetricResponse,
  TenantProviderUsageSummaryResponse,
} from "@/lib/api/types";
import { useDashboardAccess } from "@/lib/current-user";

const CAPABILITY_VENDORS: Record<string, { value: string; label: string }[]> = {
  llm: [
    { value: "openai", label: "OpenAI" },
    { value: "anthropic", label: "Anthropic" },
    { value: "mistral", label: "Mistral" },
    { value: "cohere", label: "Cohere" },
    { value: "groq", label: "Groq" },
    { value: "google", label: "Google" },
  ],
  judge: [
    { value: "anthropic", label: "Anthropic" },
    { value: "openai", label: "OpenAI" },
    { value: "google", label: "Google" },
  ],
  tts: [
    { value: "openai", label: "OpenAI" },
    { value: "elevenlabs", label: "ElevenLabs" },
    { value: "google", label: "Google" },
    { value: "azure", label: "Azure" },
  ],
  stt: [
    { value: "deepgram", label: "Deepgram" },
    { value: "openai", label: "OpenAI" },
    { value: "azure", label: "Azure" },
    { value: "google", label: "Google" },
  ],
  sip: [{ value: "sipgate", label: "sipgate" }],
};

const CAPABILITY_MODEL_SUGGESTIONS: Record<string, string[]> = {
  llm: ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-6", "claude-opus-4-6", "mistral-large-latest"],
  judge: ["claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o"],
  tts: ["gpt-4o-mini-tts", "eleven_flash_v2_5", "tts-1", "tts-1-hd"],
  stt: ["nova-2-general", "whisper-1"],
  sip: ["sip"],
};

const QUOTA_METRICS_BY_CAPABILITY: Record<string, string[]> = {
  llm: ["input_tokens", "output_tokens", "requests"],
  judge: ["input_tokens", "output_tokens", "requests"],
  tts: ["characters", "requests"],
  stt: ["audio_seconds", "requests"],
  sip: ["sip_minutes"],
};

type CredentialFieldKey = "api_key" | "region" | "endpoint";
type ManageTabKey = "overview" | "credential" | "quotas";
type QuotaDraft = { limit_per_day: string; soft_limit_pct: string };
type AssignedProviderGroup = {
  tenantId: string;
  tenantDisplayName: string;
  providers: AdminProviderSummaryResponse[];
};

type CredentialFieldConfig = {
  key: CredentialFieldKey;
  label: string;
  placeholder: string;
  inputType?: "text" | "password" | "url";
  helper?: string;
};

type ProviderModalState =
  | { mode: "assign" | "manage"; providerId: string }
  | null;

const DEFAULT_FIELDS: Record<CredentialFieldKey, string> = {
  api_key: "",
  region: "",
  endpoint: "",
};

function AddProviderModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [capability, setCapability] = useState("");
  const [vendor, setVendor] = useState("");
  const [model, setModel] = useState("");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const vendors = capability ? (CAPABILITY_VENDORS[capability] ?? []) : [];
  const modelSuggestions = capability ? (CAPABILITY_MODEL_SUGGESTIONS[capability] ?? []) : [];

  useEffect(() => {
    setVendor("");
    setModel("");
  }, [capability]);

  const canSubmit =
    capability.trim() &&
    vendor.trim() &&
    model.trim() &&
    apiKey.trim() &&
    !busy;

  async function handleSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    try {
      await createAdminProvider({
        capability,
        vendor,
        model: model.trim(),
        label: label.trim() || null,
        api_key: apiKey.trim(),
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create provider");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-[1.5rem] border border-border bg-bg-surface shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-5">
          <h2 className="text-base font-semibold text-text-primary">Add Provider</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Role / Capability
            </span>
            <select
              value={capability}
              onChange={(e) => setCapability(e.target.value)}
              className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary"
            >
              <option value="">Select capability…</option>
              <option value="llm">LLM</option>
              <option value="judge">Judge</option>
              <option value="tts">TTS</option>
              <option value="stt">STT</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Platform / Vendor
            </span>
            <select
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
              disabled={!capability}
              className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary disabled:opacity-50"
            >
              <option value="">Select vendor…</option>
              {vendors.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Model
            </span>
            <input
              list="model-suggestions"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={!vendor}
              placeholder={vendor ? "Enter model name…" : "Select vendor first"}
              className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary disabled:opacity-50"
            />
            <datalist id="model-suggestions">
              {modelSuggestions.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Label <span className="normal-case text-text-muted">(optional)</span>
            </span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Acme billing key"
              className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              API Key
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-…"
              className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary"
            />
          </label>

          {error ? <p className="text-xs text-fail">{error}</p> : null}
        </div>

        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {busy ? "Creating…" : "Add Provider"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatProviderTitle(provider: AdminProviderSummaryResponse): string {
  return `${provider.vendor}:${provider.model}`;
}

function formatMicrocents(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value / 100000000).toFixed(4)} USD`;
}

function availabilityBadge(status: string): { value: string; label: string } {
  switch (status) {
    case "available":
      return { value: "pass", label: "available" };
    case "agent_managed":
      return { value: "info", label: "agent-managed" };
    case "pending_validation":
      return { value: "warn", label: "pending validation" };
    case "invalid_credential":
      return { value: "fail", label: "invalid credential" };
    case "disabled":
      return { value: "warn", label: "disabled" };
    case "unconfigured":
      return { value: "fail", label: "unconfigured" };
    default:
      return { value: "pending", label: status.replaceAll("_", " ") };
  }
}

function credentialFieldsForProvider(
  provider: AdminProviderSummaryResponse | null
): CredentialFieldConfig[] {
  if (!provider) return [];
  if (provider.vendor === "azure") {
    return [
      {
        key: "api_key",
        label: "API key",
        placeholder: "Azure speech key",
        inputType: "password",
      },
      {
        key: "region",
        label: "Region",
        placeholder: "uksouth",
        helper: "Optional if endpoint is supplied.",
      },
      {
        key: "endpoint",
        label: "Endpoint",
        placeholder: "https://tenant-region.api.cognitive.microsoft.com",
        inputType: "url",
        helper: "Optional if region is supplied.",
      },
    ];
  }
  return [
    {
      key: "api_key",
      label: "API key",
      placeholder: `${provider.vendor} secret`,
      inputType: "password",
    },
  ];
}

function canSaveCredential(
  provider: AdminProviderSummaryResponse | null,
  values: Record<CredentialFieldKey, string>
): boolean {
  if (!provider || !provider.supports_platform_credentials) return false;
  if (!values.api_key.trim()) return false;
  if (provider.vendor !== "azure") return true;
  return values.region.trim().length > 0 || values.endpoint.trim().length > 0;
}

function credentialStateBadge(provider: AdminProviderSummaryResponse): { value: string; label: string } {
  const credential = provider.platform_credential;
  if (!credential?.has_stored_secret) {
    return { value: "pending", label: "no credential" };
  }
  switch (credential.validation_status) {
    case "valid":
      return { value: "pass", label: "stored & valid" };
    case "pending":
      return { value: "warn", label: "stored & pending" };
    case "invalid":
      return { value: "fail", label: "stored & invalid" };
    default:
      return { value: "info", label: "stored" };
  }
}

function credentialIndicator(provider: AdminProviderSummaryResponse): {
  icon: typeof CheckCircle2;
  className: string;
  label: string;
} {
  const credential = provider.platform_credential;
  if (!credential?.has_stored_secret || credential.validation_status === "invalid") {
    return {
      icon: XCircle,
      className: "text-fail",
      label: credential?.validation_status === "invalid" ? "Credential invalid" : "No credential",
    };
  }
  if (credential.validation_status === "pending") {
    return {
      icon: CheckCircle2,
      className: "text-warn",
      label: "Credential pending",
    };
  }
  return { icon: CheckCircle2, className: "text-pass", label: "Credential stored" };
}

function costSummary(provider: AdminProviderSummaryResponse): string {
  const cost = provider.cost_metadata;
  switch (provider.capability) {
    case "llm":
    case "judge":
      return `in ${formatMicrocents(cost.cost_per_input_token_microcents)} · out ${formatMicrocents(cost.cost_per_output_token_microcents)}`;
    case "tts":
      return `chars ${formatMicrocents(cost.cost_per_character_microcents)} · req ${formatMicrocents(cost.cost_per_request_microcents)}`;
    case "stt":
      return `audio ${formatMicrocents(cost.cost_per_audio_second_microcents)} · req ${formatMicrocents(cost.cost_per_request_microcents)}`;
    default:
      return "No primary cost metric";
  }
}

function quotaMetricsForCapability(capability: string): string[] {
  return QUOTA_METRICS_BY_CAPABILITY[capability] ?? [];
}

function formatWindowLabel(windowStart?: string, windowEnd?: string): string {
  if (!windowStart || !windowEnd) return "Rolling 24-hour window";
  return `${formatDateTime(windowStart)} to ${formatDateTime(windowEnd)}`;
}

function metricLabel(metric: string): string {
  switch (metric) {
    case "input_tokens":
      return "Input tokens";
    case "output_tokens":
      return "Output tokens";
    case "audio_seconds":
      return "Audio seconds";
    case "characters":
      return "Characters";
    case "sip_minutes":
      return "SIP minutes";
    case "requests":
      return "Requests";
    default:
      return metric.replaceAll("_", " ");
  }
}

function formatUsageMetricValue(metric: string, value: number): string {
  if (metric === "audio_seconds" || metric === "sip_minutes") {
    return value.toFixed(1);
  }
  return new Intl.NumberFormat().format(Math.round(value));
}

function usageValueForMetric(item: TenantProviderUsageSummaryResponse | undefined, metric: string): number {
  if (!item) return 0;
  switch (metric) {
    case "input_tokens":
      return item.input_tokens_24h;
    case "output_tokens":
      return item.output_tokens_24h;
    case "audio_seconds":
      return item.audio_seconds_24h;
    case "characters":
      return item.characters_24h;
    case "sip_minutes":
      return item.sip_minutes_24h;
    case "requests":
      return item.request_count_24h;
    default:
      return 0;
  }
}

function quotaStatusBadge(
  metric: TenantProviderQuotaMetricResponse | undefined
): { value: string; label: string } {
  if (!metric) return { value: "pending", label: "no policy" };
  switch (metric.status) {
    case "healthy":
      return { value: "pass", label: "healthy" };
    case "watch":
      return { value: "warn", label: "watch" };
    case "exceeded":
    case "blocked":
      return { value: "fail", label: metric.status };
    default:
      return { value: "info", label: metric.status.replaceAll("_", " ") };
  }
}

export default function AdminProvidersPage() {
  const { roleResolved, canAccessAdminProviders } = useDashboardAccess();
  const {
    data: providersData,
    error: providersError,
    mutate: mutateProviders,
  } = useAdminProviders(canAccessAdminProviders);
  const { data: tenantsData, error: tenantsError } = useAdminTenants(100, 0, canAccessAdminProviders);

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [modalState, setModalState] = useState<ProviderModalState>(null);
  const [assignTenantId, setAssignTenantId] = useState("");
  const [credentialValues, setCredentialValues] =
    useState<Record<CredentialFieldKey, string>>(DEFAULT_FIELDS);
  const [collapsedTenantGroups, setCollapsedTenantGroups] = useState<Record<string, boolean>>({});

  const providers = providersData?.items ?? [];
  const tenants = tenantsData?.items ?? [];
  const activeProvider =
    providers.find((provider) => provider.provider_id === modalState?.providerId) ?? null;

  const assignedProviders = providers
    .filter((provider) => provider.assigned_tenant)
    .sort((a, b) => {
      const tenantComparison = (a.assigned_tenant?.tenant_display_name ?? "").localeCompare(
        b.assigned_tenant?.tenant_display_name ?? ""
      );
      if (tenantComparison !== 0) return tenantComparison;
      return (a.label ?? formatProviderTitle(a)).localeCompare(b.label ?? formatProviderTitle(b));
    });
  const availableProviders = providers
    .filter((provider) => !provider.assigned_tenant)
    .sort((a, b) => (a.label ?? formatProviderTitle(a)).localeCompare(b.label ?? formatProviderTitle(b)));
  const assignedProviderGroups = assignedProviders.reduce<AssignedProviderGroup[]>((groups, provider) => {
    const tenantId = provider.assigned_tenant?.tenant_id ?? "";
    const tenantDisplayName = provider.assigned_tenant?.tenant_display_name ?? "Assigned tenant";
    const existing = groups.find((group) => group.tenantId === tenantId);
    if (existing) {
      existing.providers.push(provider);
      return groups;
    }
    groups.push({
      tenantId,
      tenantDisplayName,
      providers: [provider],
    });
    return groups;
  }, []);

  const assignedProviderIdKey = useMemo(
    () => assignedProviders.map((p) => p.provider_id).join("|"),
    [assignedProviders]
  );

  useEffect(() => {
    if (assignedProviderGroups.length === 0) return;
    setCollapsedTenantGroups((current) => {
      let changed = false;
      const next = { ...current };
      for (const group of assignedProviderGroups) {
        if (next[group.tenantId] === undefined) {
          next[group.tenantId] = true;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignedProviderIdKey]);

  useEffect(() => {
    if (modalState && !activeProvider) {
      setModalState(null);
    }
  }, [activeProvider, modalState]);

  useEffect(() => {
    setCredentialValues(DEFAULT_FIELDS);
    setErrorMessage("");
    if (!modalState || !activeProvider) {
      setAssignTenantId("");
      return;
    }
    if (modalState.mode === "assign") {
      setAssignTenantId(tenants[0]?.tenant_id ?? "");
    } else {
      setAssignTenantId(activeProvider.assigned_tenant?.tenant_id ?? "");
    }
  }, [activeProvider?.provider_id, modalState?.mode, tenantsData]);

  const pageStats = {
    total: providers.length,
    assigned: assignedProviders.length,
    available: availableProviders.length,
    pendingValidation: providers.filter(
      (provider) => provider.platform_credential?.validation_status === "pending"
    ).length,
  };

  const credentialFields = credentialFieldsForProvider(activeProvider);
  const canStoreCredential = canSaveCredential(activeProvider, credentialValues);
  const headerGlow =
    "pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(107,114,128,0.18),transparent_40%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.14),transparent_42%)]";

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading provider administration…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canAccessAdminProviders) {
    return (
      <AccessPanel
        title="Provider Admin"
        message="Provider administration is restricted to system_admin."
      />
    );
  }

  async function handleSaveCredential() {
    if (!activeProvider) return;
    setBusyKey("save-credential");
    setMessage("");
    setErrorMessage("");
    try {
      const payload = Object.fromEntries(
        credentialFields
          .map((field) => [field.key, credentialValues[field.key].trim()])
          .filter(([, value]) => (value as string).length > 0)
      );
      await upsertAdminProviderCredential(activeProvider.provider_id, { secret_fields: payload });
      setMessage(`Stored credential updated for ${formatProviderTitle(activeProvider)}.`);
      setCredentialValues(DEFAULT_FIELDS);
      await mutateProviders();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to store provider credential"
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDeleteCredential() {
    if (!activeProvider) return;
    if (
      !window.confirm(
        `Remove the stored platform credential for ${formatProviderTitle(activeProvider)}?`
      )
    ) {
      return;
    }
    setBusyKey("delete-credential");
    setMessage("");
    setErrorMessage("");
    try {
      await deleteAdminProviderCredential(activeProvider.provider_id);
      setMessage(`Stored credential removed for ${formatProviderTitle(activeProvider)}.`);
      await mutateProviders();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to remove provider credential"
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function handleAssignProvider() {
    if (!activeProvider || !assignTenantId) return;
    setBusyKey("assign-provider");
    setMessage("");
    setErrorMessage("");
    try {
      await assignAdminProvider(activeProvider.provider_id, { tenant_id: assignTenantId });
      const tenantName =
        tenants.find((tenant) => tenant.tenant_id === assignTenantId)?.display_name ?? assignTenantId;
      setMessage(`Assigned ${formatProviderTitle(activeProvider)} to ${tenantName}.`);
      setModalState(null);
      await mutateProviders();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to assign provider");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleUnassignProvider() {
    if (!activeProvider) return;
    if (
      !window.confirm(
        `Unassign ${formatProviderTitle(activeProvider)} from ${activeProvider.assigned_tenant?.tenant_display_name ?? "its tenant"}?`
      )
    ) {
      return;
    }
    setBusyKey("unassign-provider");
    setMessage("");
    setErrorMessage("");
    try {
      await deleteAdminProviderAssignment(activeProvider.provider_id);
      setMessage(`Unassigned ${formatProviderTitle(activeProvider)}.`);
      setModalState(null);
      await mutateProviders();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to unassign provider");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDeleteProvider(provider: AdminProviderSummaryResponse) {
    if (
      !window.confirm(
        `Delete provider "${formatProviderTitle(provider)}"? This removes its assignment and quota policies.`
      )
    ) {
      return;
    }
    setBusyKey(`delete-provider:${provider.provider_id}`);
    setMessage("");
    setErrorMessage("");
    try {
      await deleteAdminProvider(provider.provider_id);
      setMessage(`Provider ${formatProviderTitle(provider)} deleted.`);
      if (modalState?.providerId === provider.provider_id) {
        setModalState(null);
      }
      await mutateProviders();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to delete provider");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="space-y-6">
      {showAddModal ? (
        <AddProviderModal
          onClose={() => setShowAddModal(false)}
          onCreated={() => void mutateProviders()}
        />
      ) : null}
      {modalState && activeProvider ? (
              <ProviderWorkflowModal
          mode={modalState.mode}
          provider={activeProvider}
          tenants={tenants}
          tenantError={tenantsError instanceof Error ? tenantsError.message : ""}
          assignTenantId={assignTenantId}
          onAssignTenantIdChange={setAssignTenantId}
          credentialValues={credentialValues}
          onCredentialValuesChange={setCredentialValues}
          credentialFields={credentialFields}
          canStoreCredential={canStoreCredential}
          busyKey={busyKey}
          onSaveLabel={async (label) => {
            setBusyKey("save-label");
            setMessage("");
            setErrorMessage("");
            try {
              await updateAdminProvider(activeProvider.provider_id, { label });
              setMessage(
                `Updated provider name for ${formatProviderTitle(activeProvider)}.`
              );
              await mutateProviders();
            } catch (error) {
              setErrorMessage(error instanceof Error ? error.message : "Failed to update provider name");
              throw error;
            } finally {
              setBusyKey(null);
            }
          }}
          onClose={() => setModalState(null)}
          onAssign={() => void handleAssignProvider()}
          onSaveCredential={() => void handleSaveCredential()}
          onDeleteCredential={() => void handleDeleteCredential()}
          onUnassign={() => void handleUnassignProvider()}
          onNotice={setMessage}
          onError={setErrorMessage}
        />
      ) : null}

      <div className="relative overflow-hidden rounded-[1.5rem] border border-border bg-bg-surface">
        <div className={headerGlow} />
        <div className="relative flex flex-col gap-4 px-5 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-3 py-1 text-[11px] uppercase tracking-[0.24em] text-text-muted">
              <ShieldCheck className="h-3.5 w-3.5" />
              Provider Administration
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-text-primary">
                Provider Admin
              </h1>
              <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-text-muted">
                Provider Access Plane
              </p>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-text-secondary">
                Assign providers to tenants, check credentials, and manage quotas in one place.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <HeroStatPill label="Catalog" value={String(pageStats.total)} icon={Cpu} />
            <HeroStatPill label="Assigned" value={String(pageStats.assigned)} icon={ArrowRightLeft} />
            <HeroStatPill label="Available" value={String(pageStats.available)} icon={Activity} />
            <HeroStatPill
              label="Pending"
              value={String(pageStats.pendingValidation)}
              icon={RefreshCw}
            />
          </div>
        </div>
      </div>

      {message ? <p className="text-sm text-pass">{message}</p> : null}
      {errorMessage ? <p className="text-sm text-fail">{errorMessage}</p> : null}

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border bg-bg-subtle/60">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-text-primary">Provider Library</h2>
              <p className="mt-1 text-xs text-text-secondary">
                Assigned providers are linked to a tenant. Available providers are ready to assign.
              </p>
            </div>
            <div className="flex shrink-0 justify-end sm:ml-auto">
              <Button size="sm" onClick={() => setShowAddModal(true)}>
                <Plus className="h-3.5 w-3.5" />
                Add Provider
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardBody className="space-y-8 p-5">
          {providersError ? (
            <div className="text-sm text-fail">{providersError.message}</div>
          ) : !providersData ? (
            <TableState kind="loading" message="Loading providers…" columns={2} rows={6} />
          ) : (
            <>
              <AssignedProvidersSection
                groups={assignedProviderGroups}
                busyKey={busyKey}
                collapsedGroups={collapsedTenantGroups}
                onToggleGroup={(tenantId) =>
                  setCollapsedTenantGroups((current) => ({
                    ...current,
                    [tenantId]: !current[tenantId],
                  }))
                }
                onOpenAssign={(provider) => setModalState({ mode: "assign", providerId: provider.provider_id })}
                onOpenManage={(provider) => setModalState({ mode: "manage", providerId: provider.provider_id })}
                onDeleteProvider={(provider) => void handleDeleteProvider(provider)}
              />
              <ProviderSection
                title="Available Providers"
                description="These providers are available to assign."
                emptyMessage="No available providers remain."
                providers={availableProviders}
                mode="available"
                busyKey={busyKey}
                onOpenAssign={(provider) => setModalState({ mode: "assign", providerId: provider.provider_id })}
                onOpenManage={(provider) => setModalState({ mode: "manage", providerId: provider.provider_id })}
                onDeleteProvider={(provider) => void handleDeleteProvider(provider)}
              />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function HeroStatPill({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof Activity;
}) {
  return (
    <div className="inline-flex min-w-[9rem] items-center gap-3 rounded-2xl border border-border bg-bg-base/80 px-3 py-2.5">
      <div className="rounded-xl border border-border bg-bg-surface p-1.5">
        <Icon className="h-3.5 w-3.5 text-text-muted" />
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">{label}</p>
        <p className="text-sm font-semibold text-text-primary">{value}</p>
      </div>
    </div>
  );
}

function AssignedProvidersSection({
  groups,
  collapsedGroups,
  busyKey,
  onToggleGroup,
  onOpenAssign,
  onOpenManage,
  onDeleteProvider,
}: {
  groups: AssignedProviderGroup[];
  collapsedGroups: Record<string, boolean>;
  busyKey: string | null;
  onToggleGroup: (tenantId: string) => void;
  onOpenAssign: (provider: AdminProviderSummaryResponse) => void;
  onOpenManage: (provider: AdminProviderSummaryResponse) => void;
  onDeleteProvider: (provider: AdminProviderSummaryResponse) => void;
}) {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-text-primary">Assigned Providers</h3>
        <p className="text-xs text-text-secondary">
          Open a tenant to view and manage its providers.
        </p>
      </div>
      {groups.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-bg-base px-4 py-6 text-sm text-text-secondary">
          No providers are assigned yet.
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => {
            const collapsed = collapsedGroups[group.tenantId] ?? true;
            return (
              <div key={group.tenantId} className="overflow-hidden rounded-2xl border border-border bg-bg-base">
                <button
                  type="button"
                  aria-expanded={!collapsed}
                  onClick={() => onToggleGroup(group.tenantId)}
                  className="flex w-full cursor-pointer items-center justify-between gap-4 px-4 py-3 text-left transition-colors hover:bg-bg-elevated/70"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {collapsed ? (
                        <ChevronRight className="h-4 w-4 text-text-muted" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-text-muted" />
                      )}
                      <span className="truncate text-sm font-semibold text-text-primary">
                        {group.tenantDisplayName}
                      </span>
                    </div>
                    <p className="mt-1 pl-6 text-xs text-text-secondary">
                      {group.providers.length} provider{group.providers.length === 1 ? "" : "s"} assigned
                    </p>
                  </div>
                </button>
                {!collapsed ? (
                  <div className="border-t border-border">
                    {group.providers.map((provider) => (
                      <ProviderLibraryRow
                        key={provider.provider_id}
                        provider={provider}
                        mode="assigned"
                        busyKey={busyKey}
                        onOpenAssign={onOpenAssign}
                        onOpenManage={onOpenManage}
                        onDeleteProvider={onDeleteProvider}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ProviderSection({
  title,
  description,
  emptyMessage,
  providers,
  mode,
  busyKey,
  onOpenAssign,
  onOpenManage,
  onDeleteProvider,
}: {
  title: string;
  description: string;
  emptyMessage: string;
  providers: AdminProviderSummaryResponse[];
  mode: "assigned" | "available";
  busyKey: string | null;
  onOpenAssign: (provider: AdminProviderSummaryResponse) => void;
  onOpenManage: (provider: AdminProviderSummaryResponse) => void;
  onDeleteProvider: (provider: AdminProviderSummaryResponse) => void;
}) {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <p className="text-xs text-text-secondary">{description}</p>
      </div>
      {providers.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-bg-base px-4 py-6 text-sm text-text-secondary">
          {emptyMessage}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-bg-base">
          {providers.map((provider) => (
            <ProviderLibraryRow
              key={provider.provider_id}
              provider={provider}
              mode={mode}
              busyKey={busyKey}
              onOpenAssign={onOpenAssign}
              onOpenManage={onOpenManage}
              onDeleteProvider={onDeleteProvider}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ProviderLibraryRow({
  provider,
  mode,
  busyKey,
  onOpenAssign,
  onOpenManage,
  onDeleteProvider,
}: {
  provider: AdminProviderSummaryResponse;
  mode: "assigned" | "available";
  busyKey: string | null;
  onOpenAssign: (provider: AdminProviderSummaryResponse) => void;
  onOpenManage: (provider: AdminProviderSummaryResponse) => void;
  onDeleteProvider: (provider: AdminProviderSummaryResponse) => void;
}) {
  const credential = credentialIndicator(provider);
  const title = provider.label ?? formatProviderTitle(provider);
  const CredentialIcon = credential.icon;
  const canonicalTitle = formatProviderTitle(provider);
  const availability = availabilityBadge(provider.availability_status);

  return (
    <div className="flex flex-col gap-3 border-t border-border px-4 py-3 first:border-t-0 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="truncate text-sm font-semibold text-text-primary">{title}</h4>
          <StatusBadge value="info" label={provider.capability} />
          {provider.user_created ? <StatusBadge value="pending" label="custom" /> : null}
          <StatusBadge value={availability.value} label={availability.label} />
        </div>
        <p className="mt-1 truncate text-xs text-text-secondary">
          {provider.label ? `${canonicalTitle} · ` : ""}
          {mode === "assigned"
            ? costSummary(provider)
            : `${provider.assigned_tenant?.tenant_display_name ?? "No tenant assigned"} · ${costSummary(provider)}`}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3 md:flex-nowrap">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-surface px-3 py-1.5 text-xs text-text-secondary">
          <CredentialIcon className={`h-4 w-4 ${credential.className}`} />
          <span>{credential.label}</span>
        </div>
        {mode === "assigned" ? (
          <Button
            variant="secondary"
            onClick={() => onOpenManage(provider)}
            aria-label={`Manage ${canonicalTitle}`}
          >
            <Settings2 className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={() => onOpenAssign(provider)} aria-label={`Assign ${canonicalTitle}`}>
            <ArrowRightLeft className="h-4 w-4" />
            Assign
          </Button>
        )}
        {provider.user_created ? (
          <Button
            variant="secondary"
            disabled={busyKey === `delete-provider:${provider.provider_id}`}
            onClick={() => onDeleteProvider(provider)}
            aria-label={`Delete ${canonicalTitle}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function ProviderWorkflowModal({
  mode,
  provider,
  tenants,
  tenantError,
  assignTenantId,
  onAssignTenantIdChange,
  credentialValues,
  onCredentialValuesChange,
  credentialFields,
  canStoreCredential,
  busyKey,
  onSaveLabel,
  onClose,
  onAssign,
  onSaveCredential,
  onDeleteCredential,
  onUnassign,
  onNotice,
  onError,
}: {
  mode: "assign" | "manage";
  provider: AdminProviderSummaryResponse;
  tenants: Array<{ tenant_id: string; display_name: string }>;
  tenantError: string;
  assignTenantId: string;
  onAssignTenantIdChange: (value: string) => void;
  credentialValues: Record<CredentialFieldKey, string>;
  onCredentialValuesChange: (value: Record<CredentialFieldKey, string>) => void;
  credentialFields: CredentialFieldConfig[];
  canStoreCredential: boolean;
  busyKey: string | null;
  onSaveLabel: (label: string | null) => Promise<void>;
  onClose: () => void;
  onAssign: () => void;
  onSaveCredential: () => void;
  onDeleteCredential: () => void;
  onUnassign: () => void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const availability = availabilityBadge(provider.availability_status);
  const credential = credentialStateBadge(provider);
  const [activeTab, setActiveTab] = useState<ManageTabKey>("overview");
  const [quotaDrafts, setQuotaDrafts] = useState<Record<string, QuotaDraft>>({});
  const [quotaBusy, setQuotaBusy] = useState(false);
  const [quotaMessage, setQuotaMessage] = useState("");
  const [quotaErrorMessage, setQuotaErrorMessage] = useState("");
  const [labelDraft, setLabelDraft] = useState(provider.label ?? "");
  const [labelEditing, setLabelEditing] = useState(false);
  const manageMode = mode === "manage" && Boolean(provider.assigned_tenant);
  const allowedMetrics = quotaMetricsForCapability(provider.capability);
  const {
    data: usageData,
    error: usageError,
    mutate: mutateUsage,
  } = useAdminProviderUsage(provider.provider_id, manageMode);
  const {
    data: quotaData,
    error: quotaError,
    mutate: mutateQuota,
  } = useAdminProviderQuota(provider.provider_id, manageMode);
  const {
    data: quotaPoliciesData,
    error: quotaPoliciesError,
    mutate: mutateQuotaPolicies,
  } = useAdminProviderQuotaPolicies(provider.provider_id, manageMode);
  const quotaPoliciesByMetric = new Map(
    (quotaPoliciesData?.items ?? []).map((item) => [item.metric, item] as const)
  );
  const quotaSummaryByMetric = new Map(
    (quotaData?.item.metrics ?? []).map((item) => [item.metric, item] as const)
  );

  useEffect(() => {
    setActiveTab("overview");
    setQuotaMessage("");
    setQuotaErrorMessage("");
    setLabelDraft(provider.label ?? "");
    setLabelEditing(false);
  }, [provider.provider_id, provider.label, mode]);

  useEffect(() => {
    if (!manageMode) {
      setQuotaDrafts({});
      return;
    }
    const nextDrafts: Record<string, QuotaDraft> = {};
    for (const metric of allowedMetrics) {
      const existing = quotaPoliciesByMetric.get(metric);
      nextDrafts[metric] = {
        limit_per_day: existing ? String(existing.limit_per_day) : "",
        soft_limit_pct: existing ? String(existing.soft_limit_pct) : "80",
      };
    }
    setQuotaDrafts(nextDrafts);
  }, [allowedMetrics.join("|"), manageMode, provider.provider_id, quotaPoliciesData]);

  async function handleSaveQuotas() {
    if (!provider.assigned_tenant) return;
    setQuotaBusy(true);
    setQuotaMessage("");
    setQuotaErrorMessage("");
    onError("");
    try {
      for (const metric of allowedMetrics) {
        const draft = quotaDrafts[metric] ?? { limit_per_day: "", soft_limit_pct: "80" };
        const existing = quotaPoliciesByMetric.get(metric);
        const limitText = draft.limit_per_day.trim();
        const softLimitText = draft.soft_limit_pct.trim() || "80";
        if (!limitText) {
          if (existing) {
            await deleteAdminProviderQuotaPolicy(
              provider.provider_id,
              provider.assigned_tenant.tenant_id,
              metric
            );
          }
          continue;
        }
        if (!/^\d+$/.test(limitText)) {
          throw new Error(`${metricLabel(metric)} limit must be a whole number.`);
        }
        if (!/^\d+$/.test(softLimitText)) {
          throw new Error(`${metricLabel(metric)} soft limit must be a whole number.`);
        }
        const softLimitPct = Number(softLimitText);
        if (softLimitPct < 0 || softLimitPct > 100) {
          throw new Error(`${metricLabel(metric)} soft limit must be between 0 and 100.`);
        }
        await upsertAdminProviderQuotaPolicy(provider.provider_id, {
          tenant_id: provider.assigned_tenant.tenant_id,
          metric,
          limit_per_day: Number(limitText),
          soft_limit_pct: softLimitPct,
        });
      }
      const notice = `Saved quotas for ${formatProviderTitle(provider)}.`;
      setQuotaMessage(notice);
      onNotice(notice);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save provider quotas";
      setQuotaErrorMessage(message);
      onError(message);
    } finally {
      await Promise.all([mutateQuotaPolicies(), mutateQuota()]);
      setQuotaBusy(false);
    }
  }

  async function handleRemoveAllQuotas() {
    if (!provider.assigned_tenant || quotaPoliciesByMetric.size === 0) return;
    setQuotaBusy(true);
    setQuotaMessage("");
    setQuotaErrorMessage("");
    onError("");
    try {
      for (const policy of quotaPoliciesByMetric.values()) {
        await deleteAdminProviderQuotaPolicy(
          provider.provider_id,
          policy.tenant_id,
          policy.metric
        );
      }
      const nextDrafts: Record<string, QuotaDraft> = {};
      for (const metric of allowedMetrics) {
        nextDrafts[metric] = { limit_per_day: "", soft_limit_pct: "80" };
      }
      setQuotaDrafts(nextDrafts);
      const notice = `Removed quota policies for ${formatProviderTitle(provider)}.`;
      setQuotaMessage(notice);
      onNotice(notice);
      await Promise.all([mutateQuotaPolicies(), mutateQuota()]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to remove provider quotas";
      setQuotaErrorMessage(message);
      onError(message);
    } finally {
      setQuotaBusy(false);
    }
  }

  async function handleSaveLabel() {
    try {
      await onSaveLabel(labelDraft.trim() || null);
      setLabelEditing(false);
    } catch {
      // Page-level error state already receives the failure.
    }
  }

  const modalProviderTitle = provider.label ?? formatProviderTitle(provider);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 max-h-[90vh] w-full max-w-[56rem] overflow-auto rounded-[1.5rem] border border-border bg-bg-surface shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-text-primary">
                {mode === "assign" ? "Assign Provider" : "Manage Provider"}
              </h2>
              <StatusBadge value="info" label={provider.capability} />
              <StatusBadge value={availability.value} label={availability.label} />
            </div>
            {mode === "manage" && labelEditing ? (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  aria-label="Provider label"
                  value={labelDraft}
                  onChange={(event) => setLabelDraft(event.target.value)}
                  placeholder={formatProviderTitle(provider)}
                  className="min-w-[16rem] rounded-xl border border-border bg-bg-base px-3 py-2 text-sm text-text-primary"
                />
                <Button
                  variant="secondary"
                  onClick={() => void handleSaveLabel()}
                  disabled={busyKey === "save-label"}
                >
                  <Save className="h-4 w-4" />
                  {busyKey === "save-label" ? "Saving…" : "Save"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setLabelDraft(provider.label ?? "");
                    setLabelEditing(false);
                  }}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-text-secondary">{modalProviderTitle}</p>
                {mode === "manage" ? (
                  <button
                    type="button"
                    onClick={() => setLabelEditing(true)}
                    aria-label={`Rename ${formatProviderTitle(provider)}`}
                    className="rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
            )}
            {provider.label ? (
              <p className="text-xs text-text-muted">{formatProviderTitle(provider)}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-text-muted transition-colors hover:text-text-primary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="flex flex-wrap gap-2">
            <StatePill
              label="Assignment"
              badge={{
                value: provider.assigned_tenant ? "pass" : "pending",
                label: provider.assigned_tenant ? "assigned" : "available",
              }}
              detail={provider.assigned_tenant?.tenant_display_name ?? "No tenant"}
            />
            <StatePill label="Credential" badge={credential} detail={credential.label} />
            <StatePill
              label="Runtime"
              badge={{ value: "info", label: provider.runtime_scopes.join(" • ") || "none" }}
              detail={provider.runtime_scopes.join(" • ") || "No runtime scopes"}
            />
          </div>

          {mode === "assign" ? (
            <>
              <div className="rounded-2xl border border-border bg-bg-base p-4">
                <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                  Cost metadata
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <CostLine label="Input tokens" value={formatMicrocents(provider.cost_metadata.cost_per_input_token_microcents)} />
                  <CostLine label="Output tokens" value={formatMicrocents(provider.cost_metadata.cost_per_output_token_microcents)} />
                  <CostLine label="Audio second" value={formatMicrocents(provider.cost_metadata.cost_per_audio_second_microcents)} />
                  <CostLine label="Character" value={formatMicrocents(provider.cost_metadata.cost_per_character_microcents)} />
                  <CostLine label="Request" value={formatMicrocents(provider.cost_metadata.cost_per_request_microcents)} />
                </div>
              </div>

              <div className="rounded-2xl border border-border bg-bg-base p-4">
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
                    Assign to tenant
                  </span>
                  <select
                    aria-label="Assign to tenant"
                    value={assignTenantId}
                    onChange={(event) => onAssignTenantIdChange(event.target.value)}
                    className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                  >
                    <option value="">Select tenant…</option>
                    {tenants.map((tenant) => (
                      <option key={tenant.tenant_id} value={tenant.tenant_id}>
                        {tenant.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                {tenantError ? <p className="mt-3 text-xs text-fail">{tenantError}</p> : null}
                {!provider.platform_credential?.has_stored_secret ? (
                  <p className="mt-3 text-xs text-text-secondary">
                    This provider does not have a stored credential yet. You can assign it now and add the credential later.
                  </p>
                ) : null}
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {(["overview", "credential", "quotas"] as ManageTabKey[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium uppercase tracking-[0.18em] transition-colors ${
                      activeTab === tab
                        ? "border-brand bg-brand/10 text-text-primary"
                        : "border-border bg-bg-base text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {activeTab === "overview" ? (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-border bg-bg-base px-4 py-3 text-xs uppercase tracking-[0.18em] text-text-muted">
                    {formatWindowLabel(usageData?.window_start, usageData?.window_end)}
                  </div>
                  {usageError || quotaError ? (
                    <TableState
                      kind="error"
                      message={(usageError || quotaError)?.message ?? "Failed to load provider overview"}
                      columns={1}
                    />
                  ) : !usageData || !quotaData ? (
                    <TableState kind="loading" message="Loading provider overview…" columns={1} rows={4} />
                  ) : (
                    <>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        {allowedMetrics.map((metric) => {
                          const summary = quotaSummaryByMetric.get(metric);
                          return (
                            <UsageFact
                              key={metric}
                              label={metricLabel(metric)}
                              value={formatUsageMetricValue(
                                metric,
                                usageValueForMetric(usageData.item, metric)
                              )}
                              detail={
                                summary
                                  ? `${Math.round(summary.percent_used)}% of ${formatUsageMetricValue(metric, summary.limit_per_day)} daily limit`
                                  : "No daily quota policy"
                              }
                              badge={quotaStatusBadge(summary)}
                            />
                          );
                        })}
                        <UsageFact
                          label="Estimated cost"
                          value={
                            usageData.item.calculated_cost_microcents_24h == null
                              ? "—"
                              : formatMicrocents(usageData.item.calculated_cost_microcents_24h)
                          }
                          detail={`Requests ${new Intl.NumberFormat().format(
                            usageData.item.request_count_24h
                          )} in the last 24h`}
                          badge={{ value: "info", label: "24h" }}
                        />
                      </div>

                      <div className="rounded-2xl border border-border bg-bg-base p-4">
                        <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                          Cost rates
                        </p>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <CostLine label="Input tokens" value={formatMicrocents(provider.cost_metadata.cost_per_input_token_microcents)} />
                          <CostLine label="Output tokens" value={formatMicrocents(provider.cost_metadata.cost_per_output_token_microcents)} />
                          <CostLine label="Audio second" value={formatMicrocents(provider.cost_metadata.cost_per_audio_second_microcents)} />
                          <CostLine label="Character" value={formatMicrocents(provider.cost_metadata.cost_per_character_microcents)} />
                          <CostLine label="Request" value={formatMicrocents(provider.cost_metadata.cost_per_request_microcents)} />
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ) : null}

              {activeTab === "credential" ? (
                <div className="rounded-2xl border border-border bg-bg-base p-4">
                  <div className="space-y-4">
                    <div>
                      <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                        Platform credential
                      </p>
                      <p className="mt-2 text-sm text-text-secondary">
                        Updated {formatDateTime(provider.platform_credential?.updated_at)}.
                      </p>
                    </div>

                    {provider.supports_platform_credentials ? (
                      <>
                        <div className="grid gap-4">
                          {credentialFields.map((field) => (
                            <label key={field.key} className="block">
                              <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
                                {field.label}
                              </span>
                              <input
                                type={field.inputType ?? "text"}
                                aria-label={field.label}
                                value={credentialValues[field.key]}
                                onChange={(event) =>
                                  onCredentialValuesChange({
                                    ...credentialValues,
                                    [field.key]: event.target.value,
                                  })
                                }
                                placeholder={field.placeholder}
                                className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
                              />
                              {field.helper ? (
                                <span className="mt-1.5 block text-xs text-text-secondary">
                                  {field.helper}
                                </span>
                              ) : null}
                            </label>
                          ))}
                        </div>
                        {provider.vendor === "azure" ? (
                          <p className="text-xs text-text-secondary">
                            Azure credentials require an API key plus either region or endpoint.
                          </p>
                        ) : null}
                        <div className="flex flex-wrap gap-3">
                          <Button
                            onClick={onSaveCredential}
                            disabled={busyKey === "save-credential" || !canStoreCredential}
                          >
                            <KeyRound className="h-4 w-4" />
                            {busyKey === "save-credential" ? "Saving…" : "Store credential"}
                          </Button>
                          {provider.platform_credential?.has_stored_secret ? (
                            <Button
                              variant="secondary"
                              onClick={onDeleteCredential}
                              disabled={busyKey === "delete-credential"}
                            >
                              <Trash2 className="h-4 w-4" />
                              {busyKey === "delete-credential" ? "Removing…" : "Remove stored credential"}
                            </Button>
                          ) : null}
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-text-secondary">
                        This provider does not accept platform-stored credentials.
                      </p>
                    )}
                  </div>
                </div>
              ) : null}

              {activeTab === "quotas" ? (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-border bg-bg-base px-4 py-3">
                    <p className="text-xs font-medium uppercase tracking-[0.2em] text-text-muted">
                      Daily limits for {provider.assigned_tenant?.tenant_display_name ?? "assigned tenant"}
                    </p>
                    <p className="mt-2 text-sm text-text-secondary">
                      {formatWindowLabel(quotaData?.window_start, quotaData?.window_end)}
                    </p>
                  </div>
                  {quotaMessage ? <p className="text-xs text-pass">{quotaMessage}</p> : null}
                  {quotaErrorMessage ? <p className="text-xs text-fail">{quotaErrorMessage}</p> : null}
                  {quotaPoliciesError || quotaError || usageError ? (
                    <TableState
                      kind="error"
                      message={
                        quotaPoliciesError?.message ||
                        quotaError?.message ||
                        usageError?.message ||
                        "Failed to load provider quota data"
                      }
                      columns={1}
                    />
                  ) : !quotaPoliciesData || !quotaData || !usageData ? (
                    <TableState kind="loading" message="Loading provider quotas…" columns={1} rows={4} />
                  ) : (
                    <>
                      <div className="grid gap-4">
                        {allowedMetrics.map((metric) => {
                          const draft = quotaDrafts[metric] ?? {
                            limit_per_day: "",
                            soft_limit_pct: "80",
                          };
                          const policy = quotaPoliciesByMetric.get(metric);
                          const summary = quotaSummaryByMetric.get(metric);
                          return (
                            <QuotaEditorCard
                              key={metric}
                              label={metricLabel(metric)}
                              usedValue={formatUsageMetricValue(
                                metric,
                                usageValueForMetric(usageData.item, metric)
                              )}
                              detail={
                                summary
                                  ? `${Math.round(summary.percent_used)}% used · ${formatUsageMetricValue(metric, summary.remaining_24h)} remaining`
                                  : "No policy configured yet."
                              }
                              status={quotaStatusBadge(summary)}
                              limitValue={draft.limit_per_day}
                              softLimitValue={draft.soft_limit_pct}
                              onLimitValueChange={(value) =>
                                setQuotaDrafts((current) => ({
                                  ...current,
                                  [metric]: { ...current[metric], limit_per_day: value },
                                }))
                              }
                              onSoftLimitValueChange={(value) =>
                                setQuotaDrafts((current) => ({
                                  ...current,
                                  [metric]: { ...current[metric], soft_limit_pct: value },
                                }))
                              }
                              helper={
                                policy
                                  ? `Policy updated ${formatDateTime(policy.updated_at)}. Clear the limit to remove it on save.`
                                  : "Leave the limit blank to keep this metric without a quota."
                              }
                            />
                          );
                        })}
                      </div>
                      <div className="flex flex-wrap justify-end gap-3">
                        <Button
                          variant="secondary"
                          onClick={() => void handleRemoveAllQuotas()}
                          disabled={quotaBusy || quotaPoliciesByMetric.size === 0}
                        >
                          <Trash2 className="h-4 w-4" />
                          {quotaBusy ? "Updating…" : "Remove all quotas"}
                        </Button>
                        <Button onClick={() => void handleSaveQuotas()} disabled={quotaBusy}>
                          {quotaBusy ? "Saving…" : "Save quotas"}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-3 border-t border-border px-5 py-4">
          {mode === "manage" && provider.assigned_tenant ? (
            <Button
              variant="secondary"
              onClick={onUnassign}
              disabled={busyKey === "unassign-provider"}
            >
              <ArrowRightLeft className="h-4 w-4" />
              {busyKey === "unassign-provider" ? "Unassigning…" : "Unassign"}
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          {mode === "assign" ? (
            <Button onClick={onAssign} disabled={busyKey === "assign-provider" || !assignTenantId}>
              <ArrowRightLeft className="h-4 w-4" />
              {busyKey === "assign-provider" ? "Assigning…" : "Assign Provider"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function UsageFact({
  label,
  value,
  detail,
  badge,
}: {
  label: string;
  value: string;
  detail: string;
  badge: { value: string; label: string };
}) {
  return (
    <div className="rounded-2xl border border-border bg-bg-base px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">{label}</p>
        <StatusBadge value={badge.value} label={badge.label} />
      </div>
      <p className="mt-3 text-2xl font-semibold text-text-primary">{value}</p>
      <p className="mt-2 text-xs leading-5 text-text-secondary">{detail}</p>
    </div>
  );
}

function QuotaEditorCard({
  label,
  usedValue,
  detail,
  status,
  limitValue,
  softLimitValue,
  onLimitValueChange,
  onSoftLimitValueChange,
  helper,
}: {
  label: string;
  usedValue: string;
  detail: string;
  status: { value: string; label: string };
  limitValue: string;
  softLimitValue: string;
  onLimitValueChange: (value: string) => void;
  onSoftLimitValueChange: (value: string) => void;
  helper: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-bg-base p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">{label}</p>
          <p className="mt-2 text-lg font-semibold text-text-primary">{usedValue}</p>
          <p className="mt-1 text-xs text-text-secondary">Used in the last 24h</p>
        </div>
        <StatusBadge value={status.value} label={status.label} />
      </div>
      <p className="mt-3 text-xs leading-5 text-text-secondary">{detail}</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
            Limit per day
          </span>
          <input
            type="text"
            inputMode="numeric"
            value={limitValue}
            onChange={(event) => onLimitValueChange(event.target.value)}
            placeholder="Leave blank for no quota"
            className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
            Soft limit %
          </span>
          <input
            type="text"
            inputMode="numeric"
            value={softLimitValue}
            onChange={(event) => onSoftLimitValueChange(event.target.value)}
            placeholder="80"
            className="w-full rounded-xl border border-border bg-bg-surface px-3 py-2.5 text-sm text-text-primary"
          />
        </label>
      </div>
      <p className="mt-3 text-xs text-text-secondary">{helper}</p>
    </div>
  );
}

function StatePill({
  label,
  badge,
  detail,
}: {
  label: string;
  badge: { value: string; label: string };
  detail: string;
}) {
  return (
    <div className="inline-flex min-w-[12rem] items-start gap-3 rounded-2xl border border-border bg-bg-base px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">{label}</p>
        <p className="mt-1 truncate text-sm text-text-secondary">{detail}</p>
      </div>
      <StatusBadge value={badge.value} label={badge.label} />
    </div>
  );
}

function CostLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-bg-surface px-4 py-3">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="text-sm font-medium text-text-primary">{value}</span>
    </div>
  );
}
