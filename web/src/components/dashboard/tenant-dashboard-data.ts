import type {
  FeaturesResponse,
  GraiEvalRunHistorySummary,
  PlatformHealthResponse,
  RunResponse,
  ScheduleResponse,
  TenantProviderQuotaListResponse,
  TenantProviderQuotaMetricResponse,
  TenantProviderQuotaSummaryResponse,
  TenantProviderUsageListResponse,
  TenantProviderUsageSummaryResponse,
} from "@/lib/api";

const DASHBOARD_WINDOW_HOURS = 24;
const ACTIVITY_BUCKETS = 12;

export const SCHEDULE_ALERT_THRESHOLD = 2;

export interface DashboardActivityBucket {
  label: string;
  totalRuns: number;
  scheduledRuns: number;
  failedRuns: number;
}

export interface DashboardSummary {
  alertingSchedules: ScheduleResponse[];
  scheduledRuns24h: number;
  recentScheduledFailures24h: number;
  totalRuns24h: number;
  failedRuns24h: number;
  lastFailedScheduledRun: RunResponse | null;
  recentFailedRuns: RunResponse[];
  evalRuns24h: number;
  failedEvalRuns24h: number;
  lastEvalRun: GraiEvalRunHistorySummary | null;
  activity: DashboardActivityBucket[];
}

export interface DashboardHealthItem {
  label: string;
  status: string;
  tone: "pass" | "warn" | "fail" | "pending";
  detail: string;
}

export interface DashboardQuotaEntry {
  providerId: string;
  providerLabel: string;
  capability: string;
  status: string;
  badgeLabel: string;
  metricLabel: string;
  usageLabel: string;
  detail: string;
  progressPct: number;
  source: "quota" | "usage";
}

export interface DashboardQuotaSection {
  key: "llm" | "speech" | "sip";
  title: string;
  description: string;
  state: "ready" | "partial" | "empty";
  badgeValue: string;
  badgeLabel: string;
  entries: DashboardQuotaEntry[];
  emptyMessage: string;
}

export interface DashboardQuotaWarningItem {
  key: string;
  tone: "fail" | "warn" | "info";
  badgeLabel: string;
  title: string;
  detail: string;
}

export interface DashboardQuotaWarningSummary {
  tone: "pass" | "fail" | "warn" | "info";
  badgeLabel: string;
  title: string;
  detail: string;
  items: DashboardQuotaWarningItem[];
}

export function isScheduledRun(run: RunResponse): boolean {
  return run.trigger_source === "schedule" || Boolean(run.schedule_id);
}

export function isFailedRun(run: RunResponse): boolean {
  return run.state === "failed" || run.state === "error";
}

export function isFailedEvalRun(run: GraiEvalRunHistorySummary): boolean {
  return run.status === "failed" || run.failed_count > 0;
}

export function formatDashboardDateTime(value?: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDashboardRelativeTime(
  value?: string | null,
  now: Date = new Date()
): string {
  if (!value) {
    return "No recent activity";
  }
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) {
    return "No recent activity";
  }
  const deltaMinutes = Math.round((ts - now.getTime()) / 60_000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(deltaMinutes) < 60) {
    return formatter.format(deltaMinutes, "minute");
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (Math.abs(deltaHours) < 24) {
    return formatter.format(deltaHours, "hour");
  }
  return formatter.format(Math.round(deltaHours / 24), "day");
}

export function summarizeTenantDashboard(params: {
  runs: RunResponse[];
  schedules: ScheduleResponse[];
  evalRuns: GraiEvalRunHistorySummary[];
  now?: Date;
}): DashboardSummary {
  const now = params.now ?? new Date();
  const windowStart = now.getTime() - DASHBOARD_WINDOW_HOURS * 60 * 60 * 1000;

  const recentRuns = params.runs.filter((run) => isWithinWindow(run.created_at, windowStart, now));
  const recentScheduledRuns = recentRuns.filter(isScheduledRun);
  const recentFailedRuns = [...params.runs]
    .filter(isFailedRun)
    .sort((left, right) => compareDatesDesc(left.created_at, right.created_at))
    .slice(0, 5);
  const recentScheduledFailures = recentScheduledRuns.filter(isFailedRun);
  const alertingSchedules = [...params.schedules]
    .filter((schedule) => schedule.retry_on_failure && (schedule.consecutive_failures ?? 0) >= SCHEDULE_ALERT_THRESHOLD)
    .sort((left, right) => (right.consecutive_failures ?? 0) - (left.consecutive_failures ?? 0));
  const recentEvalRuns = params.evalRuns.filter((run) =>
    isWithinWindow(run.created_at, windowStart, now)
  );

  return {
    alertingSchedules,
    scheduledRuns24h: recentScheduledRuns.length,
    recentScheduledFailures24h: recentScheduledFailures.length,
    totalRuns24h: recentRuns.length,
    failedRuns24h: recentRuns.filter(isFailedRun).length,
    lastFailedScheduledRun:
      [...recentScheduledFailures].sort((left, right) =>
        compareDatesDesc(left.created_at, right.created_at)
      )[0] ?? null,
    recentFailedRuns,
    evalRuns24h: recentEvalRuns.length,
    failedEvalRuns24h: recentEvalRuns.filter(isFailedEvalRun).length,
    lastEvalRun:
      [...params.evalRuns].sort((left, right) => compareDatesDesc(left.created_at, right.created_at))[0] ??
      null,
    activity: buildActivityBuckets(recentRuns, now),
  };
}

export function buildPlatformHealthItems(params: {
  health?: PlatformHealthResponse;
  features?: FeaturesResponse;
}): DashboardHealthItem[] {
  const providerCircuits = params.features?.provider_circuits ?? [];
  const openCircuits = providerCircuits.filter((item) => item.state === "open").length;
  const apiOk = params.health?.status === "ok";
  const providerOk = params.features?.provider_degraded !== true;
  const harnessOk =
    params.features?.harness_degraded !== true &&
    (params.features?.harness_state === "closed" || params.features?.harness_state === undefined);

  return [
    {
      label: "API",
      status: apiOk ? "healthy" : "checking",
      tone: apiOk ? "pass" : "pending",
      detail: params.health?.service ?? "botcheck-api",
    },
    {
      label: "Provider routing",
      status: providerOk ? "healthy" : "degraded",
      tone: providerOk ? "pass" : "warn",
      detail:
        openCircuits > 0 ? `${openCircuits} provider circuit open` : "No provider degradation detected",
    },
    {
      label: "Speech harness",
      status: harnessOk ? "healthy" : params.features?.harness_state ?? "checking",
      tone: harnessOk ? "pass" : params.features?.harness_state ? "warn" : "pending",
      detail:
        params.features?.harness_state === "closed"
          ? "Voice path ready"
          : params.features?.harness_state
            ? `Harness state ${params.features.harness_state}`
            : "Waiting for harness state",
    },
  ];
}

export function buildDashboardQuotaSections(params: {
  quota?: TenantProviderQuotaListResponse;
  usage?: TenantProviderUsageListResponse;
  /** Maximum entries per section. Defaults to 3 (dashboard compact view). Pass Infinity for settings. */
  entryLimit?: number;
}): DashboardQuotaSection[] {
  const quotaItems = params.quota?.items ?? [];
  const usageItems = params.usage?.items ?? [];
  // Key by provider_id:capability — the same provider_id can appear under multiple
  // capabilities (e.g. a model registered for both "llm" and "judge"). Keying by
  // provider_id alone would silently overwrite earlier entries with the last-seen one.
  const entryLimit = params.entryLimit ?? 3;
  const usageByProvider = new Map(
    usageItems.map((item) => [`${item.provider_id}:${item.capability}`, item])
  );

  return [
    buildQuotaSection({
      key: "llm",
      title: "LLM provider quota",
      description: "24-hour headroom across judge and LLM providers.",
      emptyMessage: "No LLM provider quotas are configured yet.",
      quotaItems: quotaItems.filter((item) => item.capability === "llm" || item.capability === "judge"),
      usageItems: usageItems.filter((item) => item.capability === "llm" || item.capability === "judge"),
      usageByProvider,
      entryLimit,
    }),
    buildQuotaSection({
      key: "speech",
      title: "Speech provider quota",
      description: "Voice generation and transcription limits in the current window.",
      emptyMessage: "No speech provider quotas are configured yet.",
      quotaItems: quotaItems.filter((item) => item.capability === "tts" || item.capability === "stt"),
      usageItems: usageItems.filter((item) => item.capability === "tts" || item.capability === "stt"),
      usageByProvider,
      entryLimit,
    }),
    buildQuotaSection({
      key: "sip",
      title: "SIP minutes",
      description: "Tenant calling headroom with quota-aware minute usage.",
      emptyMessage: "No SIP minute quotas are configured yet.",
      quotaItems: quotaItems.filter((item) => item.capability === "sip"),
      usageItems: usageItems.filter((item) => item.capability === "sip"),
      usageByProvider,
      entryLimit,
    }),
  ];
}

export function buildDashboardQuotaWarningSummary(
  sections: DashboardQuotaSection[]
): DashboardQuotaWarningSummary {
  const items: DashboardQuotaWarningItem[] = [];

  for (const section of sections) {
    for (const entry of section.entries) {
      if (entry.source === "quota" && entry.status === "fail") {
        items.push({
          key: `fail:${section.key}:${entry.providerId}:${entry.metricLabel}`,
          tone: "fail",
          badgeLabel: "over limit",
          title: `${entry.providerLabel} exceeded ${entry.metricLabel.toLowerCase()}`,
          detail: entry.usageLabel,
        });
        continue;
      }
      if (entry.source === "quota" && entry.status === "warn") {
        items.push({
          key: `warn:${section.key}:${entry.providerId}:${entry.metricLabel}`,
          tone: "warn",
          badgeLabel: "watch",
          title: `${entry.providerLabel} is near ${entry.metricLabel.toLowerCase()}`,
          detail: entry.usageLabel,
        });
        continue;
      }
      if (entry.source === "usage") {
        items.push({
          key: `usage:${section.key}:${entry.providerId}:${entry.metricLabel}`,
          tone: "info",
          badgeLabel: "no policy",
          title: `${entry.providerLabel} is active without a quota policy`,
          detail: entry.detail,
        });
      }
    }
  }

  items.sort((left, right) => {
    const toneOrder = { fail: 0, warn: 1, info: 2 };
    const toneDelta = toneOrder[left.tone] - toneOrder[right.tone];
    if (toneDelta !== 0) {
      return toneDelta;
    }
    return left.title.localeCompare(right.title);
  });

  const failCount = items.filter((item) => item.tone === "fail").length;
  const warnCount = items.filter((item) => item.tone === "warn").length;
  const infoCount = items.filter((item) => item.tone === "info").length;

  if (failCount > 0) {
    return {
      tone: "fail",
      badgeLabel: failCount === 1 ? "limit reached" : `${failCount} limits reached`,
      title: failCount === 1 ? "A provider quota is over limit" : `${failCount} provider quotas are over limit`,
      detail: "Hard-limit providers can now block preview, run launch, or eval dispatch until usage resets or the quota changes.",
      items: items.slice(0, 4),
    };
  }

  if (warnCount > 0) {
    const details: string[] = [];
    details.push(
      warnCount === 1
        ? "A provider is approaching its soft limit in the current 24-hour window."
        : `${warnCount} providers are approaching soft limits in the current 24-hour window.`
    );
    if (infoCount > 0) {
      details.push(
        infoCount === 1
          ? "1 active provider still has no quota policy."
          : `${infoCount} active providers still have no quota policy.`
      );
    }
    return {
      tone: "warn",
      badgeLabel: warnCount === 1 ? "watch" : `${warnCount} at risk`,
      title: warnCount === 1 ? "A provider quota needs attention" : `${warnCount} provider quotas need attention`,
      detail: details.join(" "),
      items: items.slice(0, 4),
    };
  }

  if (infoCount > 0) {
    return {
      tone: "info",
      badgeLabel: infoCount === 1 ? "policy gap" : `${infoCount} policy gaps`,
      title: infoCount === 1 ? "An active provider has no quota policy" : `${infoCount} active providers have no quota policy`,
      detail: "Usage is being observed for these providers, but no quota guardrail has been configured yet.",
      items: items.slice(0, 4),
    };
  }

  return {
    tone: "pass",
    badgeLabel: "healthy",
    title: "Provider quota headroom looks healthy",
    detail: "No providers are near limits and no usage-only quota gaps were detected in the current window.",
    items: [],
  };
}

function buildQuotaSection(params: {
  key: DashboardQuotaSection["key"];
  title: string;
  description: string;
  emptyMessage: string;
  quotaItems: TenantProviderQuotaSummaryResponse[];
  usageItems: TenantProviderUsageSummaryResponse[];
  usageByProvider: Map<string, TenantProviderUsageSummaryResponse>;
  entryLimit: number;
}): DashboardQuotaSection {
  const quotaEntries = [...params.quotaItems]
    .map((item) => {
      const primaryMetric = pickPrimaryQuotaMetric(item.metrics);
      if (!primaryMetric) {
        return null;
      }
      return quotaEntry(item, primaryMetric, params.usageByProvider.get(`${item.provider_id}:${item.capability}`));
    })
    .filter((item): item is DashboardQuotaEntry => item !== null)
    .sort(compareQuotaEntries);

  const partialEntries = params.usageItems
    .filter((item) => !params.quotaItems.some(
      (quota) => quota.provider_id === item.provider_id && quota.capability === item.capability
    ))
    .map(usageEntry)
    .sort(compareQuotaEntries);

  if (quotaEntries.length > 0) {
    const worst = quotaEntries[0];
    return {
      key: params.key,
      title: params.title,
      description: params.description,
      state: "ready",
      badgeValue: worst.status,
      badgeLabel: worst.badgeLabel,
      entries: quotaEntries.slice(0, params.entryLimit),
      emptyMessage: params.emptyMessage,
    };
  }
  if (partialEntries.length > 0) {
    return {
      key: params.key,
      title: params.title,
      description: params.description,
      state: "partial",
      badgeValue: "pending",
      badgeLabel: "partial",
      entries: partialEntries.slice(0, params.entryLimit),
      emptyMessage: params.emptyMessage,
    };
  }
  return {
    key: params.key,
    title: params.title,
    description: params.description,
    state: "empty",
    badgeValue: "pending",
    badgeLabel: "not configured",
    entries: [],
    emptyMessage: params.emptyMessage,
  };
}

function pickPrimaryQuotaMetric(
  metrics: TenantProviderQuotaMetricResponse[]
): TenantProviderQuotaMetricResponse | null {
  if (!metrics.length) {
    return null;
  }
  return [...metrics].sort((left, right) => {
    if (left.hard_limit_reached !== right.hard_limit_reached) {
      return left.hard_limit_reached ? -1 : 1;
    }
    if (left.soft_limit_reached !== right.soft_limit_reached) {
      return left.soft_limit_reached ? -1 : 1;
    }
    return right.percent_used - left.percent_used;
  })[0]!;
}

function quotaEntry(
  provider: TenantProviderQuotaSummaryResponse,
  metric: TenantProviderQuotaMetricResponse,
  usage: TenantProviderUsageSummaryResponse | undefined
): DashboardQuotaEntry {
  return {
    providerId: provider.provider_id,
    providerLabel: formatProviderLabel(provider.vendor, provider.model),
    capability: provider.capability,
    status: metric.status === "healthy" ? "pass" : metric.status === "watch" ? "warn" : "fail",
    badgeLabel: metric.status === "healthy" ? "healthy" : metric.status,
    metricLabel: formatQuotaMetricLabel(metric.metric),
    usageLabel: `${formatMetricValue(metric.metric, metric.used_24h)} / ${formatMetricValue(metric.metric, metric.limit_per_day)}`,
    detail:
      usage?.last_recorded_at != null
        ? `Last activity ${formatDashboardRelativeTime(usage.last_recorded_at)}`
        : `${formatMetricValue(metric.metric, metric.remaining_24h)} remaining`,
    progressPct: Math.max(6, Math.min(100, metric.percent_used)),
    source: "quota",
  };
}

function usageEntry(usage: TenantProviderUsageSummaryResponse): DashboardQuotaEntry {
  const metric = pickPrimaryUsageMetric(usage);
  return {
    providerId: usage.provider_id,
    providerLabel: formatProviderLabel(usage.vendor, usage.model),
    capability: usage.capability,
    status: "pending",
    badgeLabel: "usage only",
    metricLabel: formatQuotaMetricLabel(metric.metric),
    usageLabel: formatMetricValue(metric.metric, metric.value),
    detail:
      usage.last_recorded_at != null
        ? `Active ${formatDashboardRelativeTime(usage.last_recorded_at)} • quota not configured`
        : "Recent usage observed • quota not configured",
    progressPct: 34,
    source: "usage",
  };
}

function pickPrimaryUsageMetric(usage: TenantProviderUsageSummaryResponse): {
  metric: TenantProviderQuotaMetricResponse["metric"];
  value: number;
} {
  const candidates: Array<{ metric: TenantProviderQuotaMetricResponse["metric"]; value: number }> = [
    { metric: "input_tokens", value: usage.input_tokens_24h ?? 0 },
    { metric: "output_tokens", value: usage.output_tokens_24h ?? 0 },
    { metric: "characters", value: usage.characters_24h ?? 0 },
    { metric: "audio_seconds", value: usage.audio_seconds_24h ?? 0 },
    { metric: "sip_minutes", value: usage.sip_minutes_24h ?? 0 },
    { metric: "requests", value: usage.request_count_24h ?? 0 },
  ];
  return candidates.sort((left, right) => right.value - left.value)[0] ?? { metric: "requests", value: 0 };
}

function compareQuotaEntries(left: DashboardQuotaEntry, right: DashboardQuotaEntry): number {
  const rank = (entry: DashboardQuotaEntry) => {
    if (entry.status === "fail") return 0;
    if (entry.status === "warn") return 1;
    if (entry.source === "usage") return 2;
    return 3;
  };
  return rank(left) - rank(right) || right.progressPct - left.progressPct || left.providerLabel.localeCompare(right.providerLabel);
}

function formatProviderLabel(vendor: string, model: string): string {
  return `${vendor}:${model}`;
}

function formatQuotaMetricLabel(metric: string): string {
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

function formatMetricValue(metric: string, value: number): string {
  if (metric === "audio_seconds") {
    if (value >= 60) {
      return `${(value / 60).toFixed(value >= 600 ? 0 : 1)} min`;
    }
    return `${Math.round(value)} sec`;
  }
  if (metric === "sip_minutes") {
    return `${value.toFixed(value >= 10 ? 0 : 1)} min`;
  }
  return new Intl.NumberFormat(undefined, {
    notation: value >= 1000 ? "compact" : "standard",
    maximumFractionDigits: value >= 1000 ? 1 : 0,
  }).format(value);
}

function buildActivityBuckets(runs: RunResponse[], now: Date): DashboardActivityBucket[] {
  const endTs = now.getTime();
  const bucketMs = (DASHBOARD_WINDOW_HOURS * 60 * 60 * 1000) / ACTIVITY_BUCKETS;
  const buckets = Array.from({ length: ACTIVITY_BUCKETS }, (_, index) => {
    const bucketStart = endTs - bucketMs * (ACTIVITY_BUCKETS - index);
    return {
      label: new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
      }).format(new Date(bucketStart)),
      totalRuns: 0,
      scheduledRuns: 0,
      failedRuns: 0,
    };
  });

  for (const run of runs) {
    const ts = parseTimestamp(run.created_at);
    if (ts === null) {
      continue;
    }
    const bucketIndex = Math.min(
      ACTIVITY_BUCKETS - 1,
      Math.max(0, Math.floor((ts - (endTs - DASHBOARD_WINDOW_HOURS * 60 * 60 * 1000)) / bucketMs))
    );
    const bucket = buckets[bucketIndex];
    bucket.totalRuns += 1;
    if (isScheduledRun(run)) {
      bucket.scheduledRuns += 1;
    }
    if (isFailedRun(run)) {
      bucket.failedRuns += 1;
    }
  }

  return buckets;
}

function isWithinWindow(value: string | null | undefined, windowStart: number, now: Date): boolean {
  const ts = parseTimestamp(value);
  return ts !== null && ts >= windowStart && ts <= now.getTime();
}

function compareDatesDesc(left?: string | null, right?: string | null): number {
  return (parseTimestamp(right) ?? 0) - (parseTimestamp(left) ?? 0);
}

function parseTimestamp(value?: string | null): number | null {
  if (!value) {
    return null;
  }
  const ts = Date.parse(value);
  return Number.isNaN(ts) ? null : ts;
}
