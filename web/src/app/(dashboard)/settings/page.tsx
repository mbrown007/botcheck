"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { TenantProviderAccessCard } from "@/components/providers/tenant-provider-access-card";
import { TenantProviderQuotaCard } from "@/components/providers/tenant-provider-quota-card";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import {
  availableProviderItems,
  useAvailableProviders,
  useFeatures,
  useTenant,
  useTenantProviderQuota,
  useTenantProviderUsage,
} from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";
import { TransportProfileSettingsCard } from "./_components/TransportProfileSettingsCard";

type FrequencyPreset = "hourly" | "daily" | "weekly";
type RetentionProfile = "ephemeral" | "standard" | "compliance" | "no_audio";

const FREQUENCY_OPTIONS: Array<{ value: FrequencyPreset; label: string; stepMs: number }> = [
  { value: "hourly", label: "Hourly", stepMs: 60 * 60 * 1000 },
  { value: "daily", label: "Daily", stepMs: 24 * 60 * 60 * 1000 },
  { value: "weekly", label: "Weekly", stepMs: 7 * 24 * 60 * 60 * 1000 },
];

const COMMON_TIMEZONES = [
  "UTC",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const RETENTION_OPTIONS: Array<{ value: RetentionProfile; label: string; description: string }> = [
  {
    value: "ephemeral",
    label: "Ephemeral",
    description: "Short retention window for high-sensitivity test data.",
  },
  {
    value: "standard",
    label: "Standard",
    description: "Balanced transcript/artifact retention for regular QA workflows.",
  },
  {
    value: "compliance",
    label: "Compliance",
    description: "Long retention period for audits and regulated environments.",
  },
  {
    value: "no_audio",
    label: "No Audio",
    description: "Avoid long-lived call artifacts while keeping run metadata.",
  },
];

function SettingsSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string;
  description: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-bg-surface">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-bg-elevated/40"
      >
        <div>
          <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
          <p className="mt-1 text-xs text-text-secondary">{description}</p>
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-text-muted" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden="true" />
        )}
      </button>
      {open ? <div className="border-t border-border px-5 py-5">{children}</div> : null}
    </section>
  );
}

function formatInTimezone(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function SettingsPage() {
  const { data: tenant } = useTenant();
  const { data: features } = useFeatures();
  const { canManageTransportProfiles, canViewProviderQuota, roleResolved } = useDashboardAccess();
  const quotaEnabled = canViewProviderQuota && roleResolved;
  const providerUsageResponse = useTenantProviderUsage(quotaEnabled);
  const providerQuotaResponse = useTenantProviderQuota(quotaEnabled);
  const availableProvidersResponse = useAvailableProviders(quotaEnabled);
  const defaultTimezone = tenant?.instance_timezone || "UTC";
  const configuredRetention = (tenant?.default_retention_profile || "standard") as RetentionProfile;
  const [preset, setPreset] = useState<FrequencyPreset>("daily");
  const [scheduleTimezone, setScheduleTimezone] = useState(defaultTimezone);
  const [retentionOpen, setRetentionOpen] = useState(false);
  const [providerQuotaOpen, setProviderQuotaOpen] = useState(true);
  const [providerAccessOpen, setProviderAccessOpen] = useState(true);
  const [platformCapabilitiesOpen, setPlatformCapabilitiesOpen] = useState(false);
  const [accountSecurityOpen, setAccountSecurityOpen] = useState(false);
  const [schedulePreviewOpen, setSchedulePreviewOpen] = useState(false);

  useEffect(() => {
    setScheduleTimezone(defaultTimezone);
  }, [defaultTimezone]);

  const timezoneOptions = useMemo(() => {
    if (COMMON_TIMEZONES.includes(defaultTimezone)) {
      return COMMON_TIMEZONES;
    }
    return [defaultTimezone, ...COMMON_TIMEZONES];
  }, [defaultTimezone]);

  const previewTimes = useMemo(() => {
    const stepMs = FREQUENCY_OPTIONS.find((item) => item.value === preset)?.stepMs ?? 0;
    const now = Date.now();
    return Array.from({ length: 5 }, (_, i) => new Date(now + stepMs * (i + 1)));
  }, [preset]);
  const providerQuotaError = [
    providerUsageResponse.error?.message,
    providerQuotaResponse.error?.message,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" ");
  const providerAccessError = availableProvidersResponse.error?.message ?? null;
  const availableProviders = availableProviderItems(availableProvidersResponse.data);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Settings</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Tenant-wide configuration, destinations, and flags.
        </p>
      </div>

      <SettingsSection
        title="Retention & Compliance"
        description="Current policy state used for transcript and data lifecycle controls."
        open={retentionOpen}
        onToggle={() => setRetentionOpen((current) => !current)}
      >
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">
              Default Retention Profile
            </span>
            <select
              value={configuredRetention}
              disabled
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none disabled:cursor-not-allowed disabled:opacity-80"
            >
              {RETENTION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-muted">
              {RETENTION_OPTIONS.find((item) => item.value === configuredRetention)?.description}
            </p>
          </label>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
              <p className="text-xs text-text-secondary">Compliance Badge: Retention</p>
              <p className="mt-1 text-sm text-text-primary font-mono">{configuredRetention}</p>
            </div>
            <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
              <p className="text-xs text-text-secondary">Compliance Badge: Redaction</p>
              <div className="mt-1">
                <StatusBadge
                  value={tenant?.redaction_enabled ? "pass" : "fail"}
                  label={tenant?.redaction_enabled ? "Enabled" : "Disabled"}
                />
              </div>
            </div>
          </div>

          <p className="text-xs text-text-muted">
            Retention profile edits land with tenant policy APIs in the next phase. This view
            reflects the active configured policy.
          </p>
        </div>
      </SettingsSection>

      <TransportProfileSettingsCard
        enabled={features?.destinations_enabled === true}
        canManage={canManageTransportProfiles}
      />

      {canViewProviderQuota ? (
        <>
          <SettingsSection
            title="Provider Quota Overview"
            description="Daily usage, quota headroom, and current provider policy for this tenant."
            open={providerQuotaOpen}
            onToggle={() => setProviderQuotaOpen((current) => !current)}
          >
            <TenantProviderQuotaCard
              testId="settings-provider-quota-card"
              quota={providerQuotaResponse.data}
              usage={providerUsageResponse.data}
              availableProviders={availableProviders}
              loading={providerUsageResponse.isLoading || providerQuotaResponse.isLoading}
              errorMessage={providerQuotaError || null}
            />
          </SettingsSection>

          <SettingsSection
            title="Provider Access"
            description="Runtime-ready providers currently assigned to this tenant."
            open={providerAccessOpen}
            onToggle={() => setProviderAccessOpen((current) => !current)}
          >
            <TenantProviderAccessCard
              title="Tenant provider access"
              description="Runtime-ready providers currently assigned to this tenant across speech, LLM, and eval judging."
              providers={availableProviders}
              capabilities={["llm", "judge", "tts", "stt"]}
              loading={availableProvidersResponse.isLoading}
              errorMessage={providerAccessError}
              emptyMessage="No tenant-assigned providers are currently available for this tenant."
              testId="settings-tenant-provider-access-card"
            />
          </SettingsSection>
        </>
      ) : (
        <SettingsSection
          title="Provider Quota Overview"
          description="Usage, quota headroom, and provider assignment visibility start at the operator role."
          open={providerQuotaOpen}
          onToggle={() => setProviderQuotaOpen((current) => !current)}
        >
          <div data-testid="settings-provider-visibility-card">
            <p className="text-sm text-text-secondary">
              Ask a tenant admin to grant operator access if you need quota and provider visibility in settings.
            </p>
          </div>
        </SettingsSection>
      )}

      <SettingsSection
        title="Platform Capabilities"
        description="Runtime feature flags reported by the API `/features` capability endpoint."
        open={platformCapabilitiesOpen}
        onToggle={() => setPlatformCapabilitiesOpen((current) => !current)}
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
            <p className="text-xs text-text-secondary">TTS Cache</p>
            <div className="mt-1">
              <StatusBadge
                value={features?.tts_cache_enabled ? "pass" : "fail"}
                label={features?.tts_cache_enabled ? "Enabled" : "Disabled"}
              />
            </div>
          </div>
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
            <p className="text-xs text-text-secondary">Scenario Packs</p>
            <div className="mt-1">
              <StatusBadge
                value={features?.packs_enabled ? "pass" : "fail"}
                label={features?.packs_enabled ? "Enabled" : "Disabled"}
              />
            </div>
          </div>
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
            <p className="text-xs text-text-secondary">Transport Profiles</p>
            <div className="mt-1">
              <StatusBadge
                value={features?.destinations_enabled ? "pass" : "fail"}
                label={features?.destinations_enabled ? "Enabled" : "Disabled"}
              />
            </div>
          </div>
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
            <p className="text-xs text-text-secondary">AI Scenarios</p>
            <div className="mt-1">
              <StatusBadge
                value={features?.ai_scenarios_enabled ? "pass" : "fail"}
                label={features?.ai_scenarios_enabled ? "Enabled" : "Disabled"}
              />
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Account Security"
        description="2FA enrollment and recovery-code management moved to User Settings."
        open={accountSecurityOpen}
        onToggle={() => setAccountSecurityOpen((current) => !current)}
      >
        <div>
          <p className="text-xs text-text-secondary">
            Open the user menu in the top-right and select{" "}
            <span className="font-semibold text-text-primary">User Settings</span> to manage TOTP.
          </p>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Schedule Timezone Preview"
        description="Every schedule must show an explicit timezone. The instance timezone is the default."
        open={schedulePreviewOpen}
        onToggle={() => setSchedulePreviewOpen((current) => !current)}
      >
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">
                Frequency Preset
              </span>
              <select
                value={preset}
                onChange={(e) => setPreset(e.target.value as FrequencyPreset)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                {FREQUENCY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">
                Schedule Timezone
              </span>
              <select
                value={scheduleTimezone}
                onChange={(e) => setScheduleTimezone(e.target.value)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                {timezoneOptions.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="rounded-md border border-border bg-bg-elevated p-3 text-xs text-text-secondary">
            <p>
              Effective timezone:{" "}
              <span className="font-mono text-text-primary">{scheduleTimezone}</span>
            </p>
            <p className="mt-1">
              Instance default timezone:{" "}
              <span className="font-mono text-text-primary">{defaultTimezone}</span>
            </p>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Next 5 Occurrences ({scheduleTimezone})
            </h3>
            <ul className="mt-2 space-y-2">
              {previewTimes.map((date, i) => (
                <li
                  key={`${date.toISOString()}-${i}`}
                  className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                >
                  {formatInTimezone(date, scheduleTimezone)}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-text-muted">
              Preview-only UI in Phase 1. Full schedule CRUD, cron editing, and misfire handling
              land in the scheduling phase.
            </p>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
