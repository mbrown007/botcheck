"use client";

import { type FormEvent, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  createTransportProfile,
  deleteTransportProfile,
  fetchTransportProfileDetail,
  mapApiError,
  patchTenantSIPPool,
  useTenantSIPPools,
  updateTransportProfile,
  useTransportProfiles,
} from "@/lib/api";
import type {
  BotDestinationDetail,
  BotDestinationSummary,
  BotDestinationUpsertRequest,
  DirectHTTPTransportConfig,
  DestinationProtocol,
} from "@/lib/api";

type Tone = "info" | "warn" | "error";

type HttpMode = "generic_json" | "json_sse_chat";
type HeaderRow = { key: string; value: string };

interface FormState {
  name: string;
  protocol: DestinationProtocol;
  endpoint: string;
  caller_id: string;
  trunk_pool_id: string;
  legacy_trunk_id: string;
  capacity_scope: string;
  provisioned_channels: string;
  reserved_channels: string;
  botcheck_max_channels: string;
  http_mode: HttpMode;
  http_timeout_s: string;
  http_max_retries: string;
  http_request_text_field: string;
  http_request_history_field: string;
  http_request_session_id_field: string;
  http_response_text_field: string;
  http_request_body_defaults: string;
  header_rows: HeaderRow[];
}

const EMPTY_FORM: FormState = {
  name: "",
  protocol: "sip",
  endpoint: "",
  caller_id: "",
  trunk_pool_id: "",
  legacy_trunk_id: "",
  capacity_scope: "",
  provisioned_channels: "",
  reserved_channels: "",
  botcheck_max_channels: "",
  http_mode: "generic_json",
  http_timeout_s: "30",
  http_max_retries: "1",
  http_request_text_field: "message",
  http_request_history_field: "history",
  http_request_session_id_field: "session_id",
  http_response_text_field: "response",
  http_request_body_defaults: "",
  header_rows: [],
};

function parseOptionalInt(value: string): number | undefined {
  const candidate = value.trim();
  if (!candidate) return undefined;
  const parsed = Number(candidate);
  if (!Number.isFinite(parsed)) return undefined;
  return Math.trunc(parsed);
}

function parseOptionalFloat(value: string): number | undefined {
  const candidate = value.trim();
  if (!candidate) return undefined;
  const parsed = Number(candidate);
  if (!Number.isFinite(parsed)) return undefined;
  return parsed;
}

function computePreviewEffectiveChannels(form: FormState): number | null {
  if (form.protocol !== "sip") return null;
  const max = parseOptionalInt(form.botcheck_max_channels);
  if (typeof max === "number") return Math.max(1, max);
  const provisioned = parseOptionalInt(form.provisioned_channels);
  const reserved = parseOptionalInt(form.reserved_channels);
  if (typeof provisioned === "number" && typeof reserved === "number") {
    return Math.max(1, provisioned - reserved);
  }
  return null;
}

function formatAssignedPoolQuotaSummary(pool: {
  max_channels?: number | null;
  reserved_channels?: number | null;
}): string | null {
  if (pool.max_channels == null && pool.reserved_channels == null) return null;
  if (pool.max_channels != null && pool.reserved_channels != null) {
    const available = Math.max(0, pool.max_channels - pool.reserved_channels);
    return `Channel quota: ${available} available (${pool.max_channels} max, ${pool.reserved_channels} reserved)`;
  }
  if (pool.max_channels != null) {
    return `Channel quota: ${pool.max_channels} max`;
  }
  return `Channel quota: ${pool.reserved_channels} reserved`;
}

function formFromDestination(destination: BotDestinationDetail): FormState {
  const httpConfig = (destination.direct_http_config ?? {}) as DirectHTTPTransportConfig;
  const bodyDefaults = httpConfig.request_body_defaults;
  return {
    name: String(destination.name ?? ""),
    protocol: (String(destination.protocol ?? "sip") as DestinationProtocol),
    endpoint: String(destination.default_dial_target ?? destination.endpoint ?? ""),
    caller_id: String(destination.caller_id ?? ""),
    trunk_pool_id: String(destination.trunk_pool_id ?? ""),
    legacy_trunk_id: String(destination.trunk_id ?? ""),
    capacity_scope: String(destination.capacity_scope ?? ""),
    provisioned_channels:
      destination.provisioned_channels == null ? "" : String(destination.provisioned_channels),
    reserved_channels: destination.reserved_channels == null ? "" : String(destination.reserved_channels),
    botcheck_max_channels:
      destination.botcheck_max_channels == null ? "" : String(destination.botcheck_max_channels),
    http_mode: (httpConfig.http_mode ?? "generic_json") as HttpMode,
    http_timeout_s:
      httpConfig.timeout_s == null ? "30" : String(httpConfig.timeout_s),
    http_max_retries:
      httpConfig.max_retries == null ? "1" : String(httpConfig.max_retries),
    http_request_text_field: String(httpConfig.request_text_field ?? "message"),
    http_request_history_field: String(httpConfig.request_history_field ?? "history"),
    http_request_session_id_field: String(httpConfig.request_session_id_field ?? "session_id"),
    http_response_text_field: String(httpConfig.response_text_field ?? "response"),
    http_request_body_defaults:
      bodyDefaults && Object.keys(bodyDefaults).length > 0
        ? JSON.stringify(bodyDefaults, null, 2)
        : "",
    header_rows: Object.entries(destination.headers ?? {}).map(([key, value]) => ({
      key,
      value: String(value),
    })),
  };
}

function buildDirectHttpConfig(form: FormState): DirectHTTPTransportConfig {
  const isSseChat = form.http_mode === "json_sse_chat";
  const defaultsText = form.http_request_body_defaults.trim();
  const request_body_defaults = defaultsText
    ? (JSON.parse(defaultsText) as Record<string, unknown>)
    : undefined;
  return {
    http_mode: form.http_mode,
    method: "POST",
    request_content_type: "json",
    request_text_field: form.http_request_text_field.trim() || "message",
    request_history_field: isSseChat ? null : (form.http_request_history_field.trim() || null),
    request_session_id_field: form.http_request_session_id_field.trim() || null,
    ...(request_body_defaults != null && { request_body_defaults }),
    response_text_field: form.http_response_text_field.trim() || "response",
    timeout_s: parseOptionalFloat(form.http_timeout_s) ?? 30,
    max_retries: parseOptionalInt(form.http_max_retries) ?? 1,
  };
}

function isValidJsonObject(text: string): boolean {
  if (!text.trim()) return true;
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && !Array.isArray(parsed) && parsed !== null;
  } catch {
    return false;
  }
}

function TransportSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-bg-elevated/40">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition-colors hover:bg-bg-elevated/60"
      >
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-secondary">
            {title}
          </p>
          {description ? (
            <p className="mt-1 text-xs text-text-muted">{description}</p>
          ) : null}
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-text-muted" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden="true" />
        )}
      </button>
      {open ? <div className="border-t border-border px-4 py-4">{children}</div> : null}
    </section>
  );
}

export function TransportProfileSettingsCard({
  enabled,
  canManage,
}: {
  enabled: boolean;
  canManage: boolean;
}) {
  const { data: destinations, error, mutate } = useTransportProfiles(enabled);
  const { data: tenantPools, mutate: mutateTenantPools } = useTenantSIPPools(enabled);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingPoolId, setEditingPoolId] = useState<string | null>(null);
  const [poolLabelDraft, setPoolLabelDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [editFetching, setEditFetching] = useState(false);
  const [message, setMessage] = useState<{ tone: Tone; text: string } | null>(null);
  const [editorOpen, setEditorOpen] = useState(true);
  const [profilesOpen, setProfilesOpen] = useState(true);
  const [poolsOpen, setPoolsOpen] = useState(false);

  const previewChannels = useMemo(() => computePreviewEffectiveChannels(form), [form]);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setEditorOpen(false);
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!enabled || !canManage) return;

    const name = form.name.trim();
    const endpoint = form.endpoint.trim();
    if (!name) {
      setMessage({ tone: "warn", text: "Name is required." });
      return;
    }
    if (form.protocol === "http" && !endpoint) {
      setMessage({ tone: "warn", text: "Endpoint URL is required for HTTP transport profiles." });
      return;
    }
    if (form.protocol === "http" && parseOptionalFloat(form.http_timeout_s) == null) {
      setMessage({ tone: "warn", text: "Timeout must be a valid number of seconds." });
      return;
    }
    if (form.protocol === "http" && parseOptionalInt(form.http_max_retries) == null) {
      setMessage({ tone: "warn", text: "Max retries must be a whole number." });
      return;
    }
    if (form.protocol === "http" && !isValidJsonObject(form.http_request_body_defaults)) {
      setMessage({ tone: "warn", text: "Request body defaults must be a JSON object (e.g. {\"key\": \"value\"})." });
      return;
    }

    const payload: BotDestinationUpsertRequest = {
      name,
      protocol: form.protocol,
      caller_id: form.caller_id.trim() || undefined,
      trunk_pool_id: form.trunk_pool_id.trim() || undefined,
      trunk_id:
        form.protocol === "sip" && !form.trunk_pool_id.trim()
          ? form.legacy_trunk_id.trim() || undefined
          : undefined,
      is_active: true,
      headers: Object.fromEntries(
        form.header_rows
          .filter((row) => row.key.trim())
          .map((row) => [row.key.trim(), row.value])
      ),
    };
    if (endpoint) {
      if (form.protocol === "http") {
        payload.endpoint = endpoint;
        payload.default_dial_target = endpoint;
      } else {
        payload.default_dial_target = endpoint;
      }
    }

    if (form.protocol === "sip") {
      if (!payload.trunk_pool_id && !payload.trunk_id) {
        setMessage({ tone: "warn", text: "Select an assigned trunk pool for SIP transport profiles." });
        setBusy(false);
        return;
      }
      payload.capacity_scope = form.capacity_scope.trim() || undefined;
      payload.provisioned_channels = parseOptionalInt(form.provisioned_channels);
      payload.reserved_channels = parseOptionalInt(form.reserved_channels);
      payload.botcheck_max_channels = parseOptionalInt(form.botcheck_max_channels);
    }
    if (form.protocol === "http") {
      payload.direct_http_config = buildDirectHttpConfig(form);
    }

    setBusy(true);
    setMessage(null);
    try {
      if (editingId) {
        await updateTransportProfile(editingId, payload);
        setMessage({ tone: "info", text: "Transport profile updated." });
      } else {
        await createTransportProfile(payload);
        setMessage({ tone: "info", text: "Transport profile created." });
      }
      await mutate();
      resetForm();
    } catch (err) {
      const mapped = mapApiError(err, "Transport profile save failed.");
      setMessage({ tone: mapped.tone, text: mapped.message });
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(destinationId: string) {
    if (!enabled || !canManage || busy) return;
    if (!window.confirm("Delete this transport profile?")) return;

    setBusy(true);
    setMessage(null);
    try {
      await deleteTransportProfile(destinationId);
      await mutate();
      setMessage({ tone: "info", text: "Transport profile deleted." });
      if (editingId === destinationId) resetForm();
    } catch (err) {
      const mapped = mapApiError(err, "Transport profile delete failed.");
      setMessage({ tone: mapped.tone, text: mapped.message });
    } finally {
      setBusy(false);
    }
  }

  async function onSavePoolLabel(trunkPoolId: string) {
    if (!enabled || !canManage || !poolLabelDraft.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      await patchTenantSIPPool(trunkPoolId, { tenant_label: poolLabelDraft.trim() });
      await mutateTenantPools();
      setEditingPoolId(null);
      setPoolLabelDraft("");
      setMessage({ tone: "info", text: "Tenant pool label updated." });
    } catch (err) {
      const mapped = mapApiError(err, "Tenant SIP pool update failed.");
      setMessage({ tone: mapped.tone, text: mapped.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-bg-surface">
      <div className="border-b border-border px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Transport Profiles</h2>
          <p className="mt-1 text-xs text-text-secondary">
            Manage reusable SIP, HTTP, WebRTC, and mock transport profiles. SIP capacity controls stay separate from direct HTTP request mapping.
          </p>
        </div>
      </div>
      <div className="space-y-4 px-5 py-5">
        {!enabled && (
          <div className="rounded-md border border-warn-border bg-warn-bg px-3 py-2 text-xs text-warn">
            Transport profile management is disabled on this environment.
          </div>
        )}
        {!canManage && enabled ? (
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-muted">
            Read-only access. Transport profile create, edit, and delete require editor role or above.
          </div>
        ) : null}

        {message && (
          <div
            className={`rounded-md border px-3 py-2 text-xs ${
              message.tone === "error"
                ? "border-fail-border bg-fail-bg text-fail"
                : message.tone === "warn"
                  ? "border-warn-border bg-warn-bg text-warn"
                  : "border-border bg-bg-elevated text-text-secondary"
            }`}
          >
            {message.text}
          </div>
        )}

        <TransportSection
          title={editingId ? "Edit Transport Profile Details" : "Transport Profile Editor"}
          description={
            editingId
              ? "Update the selected transport profile."
              : "Add a reusable SIP, HTTP, WebRTC, or mock transport profile."
          }
          open={editorOpen}
          onToggle={() => setEditorOpen((current) => !current)}
        >
          <form className="space-y-3" onSubmit={onSubmit}>
            <div className="grid gap-3 md:grid-cols-3">
              <label className="block">
                <span className="mb-1 block text-xs text-text-secondary">Name</span>
                <input
                  value={form.name}
                  onChange={(e) => updateField("name", e.target.value)}
                  disabled={!canManage}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  placeholder="Carrier A"
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-xs text-text-secondary">Protocol</span>
                <select
                  value={form.protocol}
                  onChange={(e) => updateField("protocol", e.target.value as DestinationProtocol)}
                  disabled={!canManage}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                >
                  <option value="sip">SIP</option>
                  <option value="http">HTTP</option>
                  <option value="webrtc">WebRTC</option>
                  <option value="mock">Mock</option>
                </select>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs text-text-secondary">
                  {form.protocol === "http" ? "Endpoint URL" : "Default Dial Target"}
                </span>
                <input
                  value={form.endpoint}
                  onChange={(e) => updateField("endpoint", e.target.value)}
                  disabled={!canManage}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  placeholder={
                    form.protocol === "http"
                      ? "https://bot.internal/chat"
                      : "Optional: sip:+44...@carrier.example.com or +44..."
                  }
                />
              </label>
            </div>

            {form.protocol === "sip" && (
              <div className="grid gap-3 md:grid-cols-4">
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">Assigned Trunk Pool</span>
                  <select
                    value={form.trunk_pool_id}
                    onChange={(e) => updateField("trunk_pool_id", e.target.value)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  >
                    <option value="">Select pool</option>
                    {(tenantPools?.items ?? []).map((pool) => (
                      <option key={pool.trunk_pool_id} value={pool.trunk_pool_id}>
                        {pool.tenant_label} · {pool.provider_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">Capacity Scope</span>
                  <input
                    value={form.capacity_scope}
                    onChange={(e) => updateField("capacity_scope", e.target.value)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    placeholder="carrier-a"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">Provisioned</span>
                  <input
                    value={form.provisioned_channels}
                    onChange={(e) => updateField("provisioned_channels", e.target.value)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    placeholder="10"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">Reserved</span>
                  <input
                    value={form.reserved_channels}
                    onChange={(e) => updateField("reserved_channels", e.target.value)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    placeholder="2"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">BotCheck Max</span>
                  <input
                    value={form.botcheck_max_channels}
                    onChange={(e) => updateField("botcheck_max_channels", e.target.value)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    placeholder="(optional)"
                  />
                </label>
                {form.legacy_trunk_id ? (
                  <div className="md:col-span-4 rounded-md border border-warn-border bg-warn-bg px-3 py-2 text-xs text-warn">
                    Legacy raw trunk ID preserved: <span className="font-mono">{form.legacy_trunk_id}</span>.
                    Select a trunk pool and save to migrate this destination.
                  </div>
                ) : null}
              </div>
            )}

            {form.protocol === "http" && (
              <div className="space-y-3 rounded-md border border-border bg-bg-elevated/60 p-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-secondary">
                    HTTP Request Mapping
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    Configure how BotCheck constructs requests and reads responses for this HTTP agent. Auth headers go in the Headers field above.
                  </p>
                </div>

                {/* HTTP destination type */}
                <label className="block">
                  <span className="mb-1 block text-xs text-text-secondary">HTTP Destination Type</span>
                  <select
                    value={form.http_mode}
                    onChange={(e) => updateField("http_mode", e.target.value as HttpMode)}
                    disabled={!canManage}
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  >
                    <option value="generic_json">Generic JSON API</option>
                    <option value="json_sse_chat">JSON Request + SSE Reply</option>
                  </select>
                  <p className="mt-1 text-xs text-text-muted">
                    {form.http_mode === "json_sse_chat"
                      ? "Use for agents that stream responses as Server-Sent Events (text/event-stream). History and response field mapping are not required."
                      : "Use for agents that return a plain JSON or text response body."}
                  </p>
                </label>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <label className="block">
                    <span className="mb-1 block text-xs text-text-secondary">Request Text Field</span>
                    <input
                      value={form.http_request_text_field}
                      onChange={(e) => updateField("http_request_text_field", e.target.value)}
                      disabled={!canManage}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                      placeholder="message"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs text-text-secondary">Session ID Field</span>
                    <input
                      value={form.http_request_session_id_field}
                      onChange={(e) => updateField("http_request_session_id_field", e.target.value)}
                      disabled={!canManage}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                      placeholder="session_id"
                    />
                  </label>
                  {form.http_mode === "generic_json" && (
                    <>
                      <label className="block">
                        <span className="mb-1 block text-xs text-text-secondary">History Field</span>
                        <input
                          value={form.http_request_history_field}
                          onChange={(e) => updateField("http_request_history_field", e.target.value)}
                          disabled={!canManage}
                          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                          placeholder="history"
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs text-text-secondary">Response Text Field</span>
                        <input
                          value={form.http_response_text_field}
                          onChange={(e) => updateField("http_response_text_field", e.target.value)}
                          disabled={!canManage}
                          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                          placeholder="response"
                        />
                      </label>
                    </>
                  )}
                  <label className="block">
                    <span className="mb-1 block text-xs text-text-secondary">Timeout (s)</span>
                    <input
                      value={form.http_timeout_s}
                      onChange={(e) => updateField("http_timeout_s", e.target.value)}
                      disabled={!canManage}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                      placeholder="30"
                      inputMode="decimal"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs text-text-secondary">Max Retries</span>
                    <input
                      value={form.http_max_retries}
                      onChange={(e) => updateField("http_max_retries", e.target.value)}
                      disabled={!canManage}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                      placeholder="1"
                      inputMode="numeric"
                    />
                  </label>
                </div>

                {/* Auth headers */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-text-secondary">Auth Headers</p>
                    <button
                      type="button"
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          header_rows: [...prev.header_rows, { key: "", value: "" }],
                        }))
                      }
                      disabled={!canManage}
                      className="text-xs text-text-muted hover:text-text-primary disabled:opacity-40"
                    >
                      + Add header
                    </button>
                  </div>
                  {form.header_rows.length === 0 ? (
                    <p className="text-xs text-text-muted">
                      No headers configured. Add <span className="font-mono">Authorization</span> for bearer-token auth.
                    </p>
                  ) : (
                    <div className="space-y-1.5">
                      {form.header_rows.map((row, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <input
                            value={row.key}
                            onChange={(e) =>
                              setForm((prev) => {
                                const next = [...prev.header_rows];
                                next[idx] = { ...next[idx], key: e.target.value };
                                return { ...prev, header_rows: next };
                              })
                            }
                            disabled={!canManage}
                            className="w-40 flex-shrink-0 rounded-md border border-border bg-bg-elevated px-2 py-1.5 font-mono text-xs text-text-primary"
                            placeholder="Authorization"
                          />
                          <input
                            value={row.value}
                            onChange={(e) =>
                              setForm((prev) => {
                                const next = [...prev.header_rows];
                                next[idx] = { ...next[idx], value: e.target.value };
                                return { ...prev, header_rows: next };
                              })
                            }
                            disabled={!canManage}
                            className="min-w-0 flex-1 rounded-md border border-border bg-bg-elevated px-2 py-1.5 font-mono text-xs text-text-primary"
                            placeholder="Bearer <token>"
                          />
                          <button
                            type="button"
                            onClick={() =>
                              setForm((prev) => ({
                                ...prev,
                                header_rows: prev.header_rows.filter((_, i) => i !== idx),
                              }))
                            }
                            disabled={!canManage}
                            className="flex-shrink-0 text-xs text-text-muted hover:text-fail disabled:opacity-40"
                            aria-label="Remove header"
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Request body defaults — advanced */}
                <div className="space-y-1">
                  <p className="text-xs text-text-secondary">
                    Default Request Context
                    <span className="ml-1 text-text-muted">(optional, JSON object)</span>
                  </p>
                  <p className="text-xs text-text-muted">
                    Static fields merged into every request body — useful for dashboard context, routing hints, or feature flags.
                  </p>
                  <textarea
                    value={form.http_request_body_defaults}
                    onChange={(e) => updateField("http_request_body_defaults", e.target.value)}
                    disabled={!canManage}
                    rows={4}
                    spellCheck={false}
                    className={`w-full rounded-md border px-3 py-2 font-mono text-xs text-text-primary ${
                      form.http_request_body_defaults.trim() && !isValidJsonObject(form.http_request_body_defaults)
                        ? "border-fail-border bg-fail-bg"
                        : "border-border bg-bg-elevated"
                    }`}
                    placeholder={'{\n  "dashboard_context": { "uid": "ops-overview" }\n}'}
                  />
                  {form.http_request_body_defaults.trim() && !isValidJsonObject(form.http_request_body_defaults) && (
                    <p className="text-xs text-fail">Invalid JSON</p>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-secondary">
              <span>
                Effective channels preview: {previewChannels == null ? "n/a" : String(previewChannels)}
              </span>
              <div className="flex items-center gap-2">
                {editingId && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={resetForm}
                    disabled={busy || !canManage}
                  >
                    Cancel Edit
                  </Button>
                )}
                <Button type="submit" size="sm" disabled={busy || !enabled || !canManage}>
                  {editingId ? "Update Transport Profile" : "Create Transport Profile"}
                </Button>
              </div>
            </div>
          </form>
        </TransportSection>

        <div className="space-y-3">
          <TransportSection
            title="Saved Profiles"
            description="Reusable transport profiles available to this tenant."
            open={profilesOpen}
            onToggle={() => setProfilesOpen((current) => !current)}
          >
            <div className="space-y-2">
            {error && (
              <div className="rounded-md border border-fail-border bg-fail-bg px-3 py-2 text-xs text-fail">
                Failed to load transport profiles: {error.message}
              </div>
            )}
            {!error && !destinations && (
              <div className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-secondary">
                Loading transport profiles...
              </div>
            )}
            {destinations && destinations.length === 0 && (
              <div className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-secondary">
                No transport profiles yet.
              </div>
            )}
            {destinations?.map((destination) => {
              const activeScheduleCount = destination.active_schedule_count ?? 0;
              const activePackRunCount = destination.active_pack_run_count ?? 0;
              const inUse = destination.in_use === true || activeScheduleCount > 0 || activePackRunCount > 0;
              const assignedPool = tenantPools?.items.find(
                (pool) => pool.trunk_pool_id === destination.trunk_pool_id
              );
              return (
                <div
                  key={destination.destination_id}
                  className="flex items-center justify-between rounded-md border border-border bg-bg-elevated px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-text-primary">{destination.name}</p>
                    <p className="truncate text-xs text-text-secondary">
                      {destination.protocol.toUpperCase()} ·{" "}
                      {destination.protocol === "http"
                        ? destination.endpoint || "No endpoint URL"
                        : destination.default_dial_target || "No default dial target"}
                    </p>
                    {destination.protocol === "http" && destination.direct_http_config && (
                      <p className="text-xs text-text-muted">
                        {destination.direct_http_config.http_mode === "json_sse_chat"
                          ? "JSON + SSE Reply"
                          : "Generic JSON API"}
                        {" · "}Request field: {destination.direct_http_config.request_text_field || "message"}
                        {destination.direct_http_config.http_mode !== "json_sse_chat" &&
                          ` · Response field: ${destination.direct_http_config.response_text_field || "response"}`}
                        {(destination.header_count ?? 0) > 0 &&
                          ` · ${String(destination.header_count)} auth header${destination.header_count === 1 ? "" : "s"}`}
                      </p>
                    )}
                    {destination.trunk_pool_id && (
                      <p className="text-xs text-text-muted">
                        Pool: {assignedPool?.tenant_label || destination.trunk_pool_id}
                        {assignedPool?.provider_name ? ` · ${assignedPool.provider_name}` : ""}
                      </p>
                    )}
                    {!destination.trunk_pool_id && destination.trunk_id && (
                      <p className="text-xs text-warn">
                        Legacy raw trunk destination: {destination.trunk_id}
                      </p>
                    )}
                    {destination.protocol === "sip" && (
                      <p className="text-xs text-text-muted">
                        Scope: {destination.capacity_scope || "(none)"} · Effective: {destination.effective_channels ?? "n/a"}
                      </p>
                    )}
                    {inUse && (
                      <p className="text-xs text-warn">
                        In use · Active schedules: {activeScheduleCount} · Active pack runs: {activePackRunCount}
                      </p>
                    )}
                  </div>
                  <div className="ml-3 flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void (async () => {
                        setEditFetching(true);
                        try {
                          const detail = await fetchTransportProfileDetail(destination.destination_id);
                          setEditingId(destination.destination_id);
                          setForm(formFromDestination(detail));
                          setMessage(null);
                        } finally {
                          setEditFetching(false);
                        }
                      })()}
                      disabled={busy || editFetching || !enabled || !canManage}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => void onDelete(destination.destination_id)}
                      disabled={busy || !enabled || !canManage || inUse}
                      title={inUse ? "Remove active schedules and active pack runs before deleting" : undefined}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              );
            })}
            </div>
          </TransportSection>

          {/* Assigned trunk pools — informational, rename only */}
          {tenantPools?.items?.length ? (
            <TransportSection
              title="Assigned Trunk Pools"
              description="SIP capacity pools assigned to this tenant. Pool membership is managed by platform admins."
              open={poolsOpen}
              onToggle={() => setPoolsOpen((current) => !current)}
            >
              <div className="space-y-2">
              {tenantPools.items.map((pool) => {
                const quotaSummary = formatAssignedPoolQuotaSummary(pool);
                return (
                <div
                  key={pool.trunk_pool_id}
                  className="flex items-center justify-between rounded-md border border-border bg-bg-elevated px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-text-primary">{pool.tenant_label}</p>
                    <p className="truncate text-xs text-text-secondary">
                      {pool.provider_name} · {pool.pool_name} · {pool.member_count} trunk
                      {pool.member_count === 1 ? "" : "s"}
                      {pool.is_default ? " · default" : ""}
                    </p>
                    {quotaSummary ? (
                      <p className="truncate text-xs text-text-muted">{quotaSummary}</p>
                    ) : null}
                  </div>
                  <div className="ml-3 flex items-center gap-2">
                    {editingPoolId === pool.trunk_pool_id ? (
                      <>
                        <input
                          value={poolLabelDraft}
                          onChange={(e) => setPoolLabelDraft(e.target.value)}
                          className="w-44 rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary"
                        />
                        <Button
                          size="sm"
                          onClick={() => void onSavePoolLabel(pool.trunk_pool_id)}
                          disabled={busy || !poolLabelDraft.trim()}
                        >
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setEditingPoolId(null);
                            setPoolLabelDraft("");
                          }}
                          disabled={busy}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setEditingPoolId(pool.trunk_pool_id);
                          setPoolLabelDraft(pool.tenant_label);
                        }}
                        disabled={busy || !canManage}
                      >
                        Rename
                      </Button>
                    )}
                  </div>
                </div>
              );
              })}
              </div>
            </TransportSection>
          ) : null}
        </div>
      </div>
    </section>
  );
}
