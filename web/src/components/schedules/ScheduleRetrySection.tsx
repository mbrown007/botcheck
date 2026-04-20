import type { ScheduleTargetType } from "@/components/schedules/schedule-form-helpers";

export function ScheduleRetrySection({
  targetType,
  retryOnFailure,
  setRetryOnFailure,
}: {
  targetType: ScheduleTargetType;
  retryOnFailure: boolean;
  setRetryOnFailure: (value: boolean) => void;
}) {
  return (
    <label className="block md:col-span-2">
      <span className="mb-1.5 block text-xs text-text-secondary">Retry Policy</span>
      {targetType === "scenario" ? (
        <div className="rounded-md border border-border bg-bg-elevated px-3 py-3">
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={retryOnFailure}
              onChange={(e) => setRetryOnFailure(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border bg-bg-base text-brand focus:ring-brand"
            />
            <div>
              <div className="text-sm font-medium text-text-primary">Run again on failure</div>
              <p className="mt-1 text-xs text-text-muted">
                If a scheduled run ends in failed or error, BotCheck immediately retries it once. Two consecutive failures are tracked for alerting.
              </p>
            </div>
          </label>
        </div>
      ) : (
        <div className="rounded-md border border-border bg-bg-elevated px-3 py-3 text-xs text-text-muted">
          Automatic retry-on-failure is only supported for single-scenario schedules in this slice.
        </div>
      )}
    </label>
  );
}
