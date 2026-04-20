export type FrequencyPreset = "hourly" | "daily" | "weekly";
export type ScheduleTargetType = "scenario" | "pack";

export const FREQUENCY_PRESETS: Array<{ value: FrequencyPreset; label: string; cron: string }> = [
  { value: "hourly", label: "Hourly", cron: "0 * * * *" },
  { value: "daily", label: "Daily", cron: "0 9 * * *" },
  { value: "weekly", label: "Weekly", cron: "0 9 * * 1" },
];

export const COMMON_TIMEZONES = [
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

export function formatTs(value?: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}

export function formatTsInTimezone(value: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function lastStatusVariant(status?: string | null): string {
  if (!status) {
    return "pending";
  }
  if (status === "dispatched") {
    return "pass";
  }
  if (status === "throttled") {
    return "warn";
  }
  if (status.startsWith("error_")) {
    return "fail";
  }
  return "pending";
}
