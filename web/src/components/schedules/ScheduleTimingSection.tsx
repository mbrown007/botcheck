import type { MisfirePolicy } from "@/lib/api";
import {
  FREQUENCY_PRESETS,
  formatTsInTimezone,
  type FrequencyPreset,
} from "@/components/schedules/schedule-form-helpers";

export function ScheduleTimingSection({
  preset,
  onChangePreset,
  cronExpr,
  setCronExpr,
  timezone,
  setTimezone,
  timezoneOptions,
  previewTz,
  previewTimes,
  previewLoading,
  previewError,
  defaultTimezone,
  misfirePolicy,
  setMisfirePolicy,
  active,
  setActive,
}: {
  preset: FrequencyPreset;
  onChangePreset: (value: FrequencyPreset) => void;
  cronExpr: string;
  setCronExpr: (value: string) => void;
  timezone: string;
  setTimezone: (value: string) => void;
  timezoneOptions: string[];
  previewTz: string;
  previewTimes: string[];
  previewLoading: boolean;
  previewError: string;
  defaultTimezone: string;
  misfirePolicy: MisfirePolicy;
  setMisfirePolicy: (value: MisfirePolicy) => void;
  active: boolean;
  setActive: (value: boolean) => void;
}) {
  return (
    <>
      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Frequency Preset</span>
        <select
          value={preset}
          onChange={(e) => onChangePreset(e.target.value as FrequencyPreset)}
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        >
          {FREQUENCY_PRESETS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Cron Expression</span>
        <input
          value={cronExpr}
          onChange={(e) => setCronExpr(e.target.value)}
          placeholder="0 9 * * *"
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm font-mono text-text-primary focus:border-border-focus focus:outline-none"
        />
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Timezone</span>
        <select
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        >
          {timezoneOptions.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </label>

      <div className="md:col-span-2 rounded-md border border-border bg-bg-elevated p-3">
        <p className="text-xs text-text-secondary">
          Effective timezone: <span className="font-mono text-text-primary">{previewTz}</span>
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          Instance default timezone: <span className="font-mono text-text-primary">{defaultTimezone}</span>
        </p>
        <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
          Next 5 Occurrences ({previewTz})
        </p>
        {previewLoading ? <p className="mt-2 text-xs text-warn">Computing schedule preview…</p> : null}
        {previewError ? <p className="mt-2 text-xs text-fail">{previewError}</p> : null}
        {!previewLoading && !previewError && previewTimes.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {previewTimes.map((value, idx) => (
              <li
                key={`${value}-${idx}`}
                className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary"
              >
                {formatTsInTimezone(value, previewTz)}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <label className="block">
        <span className="mb-1.5 block text-xs text-text-secondary">Misfire Policy</span>
        <select
          value={misfirePolicy}
          onChange={(e) => setMisfirePolicy(e.target.value as MisfirePolicy)}
          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        >
          <option value="skip">Skip</option>
          <option value="run_once">Run Once</option>
        </select>
      </label>

      <label className="flex items-center gap-2 self-end pb-2">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          className="h-4 w-4 rounded border-border bg-bg-elevated"
        />
        <span className="text-sm text-text-primary">Active</span>
      </label>
    </>
  );
}
