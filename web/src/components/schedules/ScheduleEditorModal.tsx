"use client";

import type { ScheduleResponse } from "@/lib/api";
import { ScheduleModalShell } from "@/components/schedules/ScheduleModalShell";
import { ScheduleRetrySection } from "@/components/schedules/ScheduleRetrySection";
import { ScheduleTargetSection } from "@/components/schedules/ScheduleTargetSection";
import { ScheduleTimingSection } from "@/components/schedules/ScheduleTimingSection";
import { ScheduleTransportSection } from "@/components/schedules/ScheduleTransportSection";
import { useScheduleFormState } from "@/app/(dashboard)/schedules/hooks/useScheduleFormState";
import { useScheduleActions } from "@/app/(dashboard)/schedules/hooks/useScheduleActions";

export function ScheduleEditorModal({
  mode,
  schedule,
  onClose,
  actions,
}: {
  mode: "create" | "edit";
  schedule?: ScheduleResponse;
  onClose: () => void;
  actions: ReturnType<typeof useScheduleActions>;
}) {
  const form = useScheduleFormState({ mode, schedule });

  const handleSubmit = async () => {
    const validationError = form.validate();
    if (validationError) {
      form.setError(validationError);
      return;
    }

    form.setSubmitting(true);
    form.setError("");
    try {
      if (mode === "create") {
        await actions.createOne(form.buildPayload() as import("@/lib/api").ScheduleCreateRequest);
      } else if (schedule) {
        await actions.updateOne(
          schedule.schedule_id,
          form.buildPayload() as import("@/lib/api").SchedulePatchRequest,
        );
      }
      onClose();
    } catch (err) {
      form.setError(err instanceof Error ? err.message : `Failed to ${mode} schedule`);
      form.setSubmitting(false);
    }
  };

  return (
    <ScheduleModalShell
      title={mode === "create" ? "New Schedule" : "Edit Schedule"}
      subtitle={mode === "edit" ? schedule?.schedule_id : undefined}
      onClose={onClose}
      onSubmit={handleSubmit}
      submitLabel={form.submitting ? (mode === "create" ? "Creating…" : "Saving…") : mode === "create" ? "Create Schedule" : "Save Changes"}
      submitDisabled={!form.canSubmit}
      error={form.error}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block md:col-span-2">
          <span className="mb-1.5 block text-xs text-text-secondary">Schedule Name</span>
          <input
            data-testid={`${mode}-schedule-name`}
            value={form.name}
            onChange={(e) => form.setName(e.target.value)}
            placeholder="Morning smoke pack"
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          />
          <p className="mt-1 text-xs text-text-muted">
            Optional human-friendly label shown in schedules and history views.
          </p>
        </label>
        <ScheduleTargetSection
          mode={mode}
          targetType={form.targetType}
          setTargetType={form.setTargetType}
          scenarioId={form.scenarioId}
          setScenarioId={form.setScenarioId}
          aiEnabled={form.aiEnabled}
          aiScenarioId={form.aiScenarioId}
          setAiScenarioId={form.setAiScenarioId}
          packId={form.packId}
          setPackId={form.setPackId}
          graphScenarios={form.graphScenarios}
          aiScenarios={form.aiScenarios}
          packs={form.packs}
        />
        <ScheduleTransportSection
          mode={mode}
          botEndpoint={form.botEndpoint}
          setBotEndpoint={form.setBotEndpoint}
          destinationsEnabled={form.destinationsEnabled}
          destinations={form.destinations}
          destinationId={form.destinationId}
          setDestinationId={form.setDestinationId}
          dispatchHint={form.dispatchHint}
        />
        <ScheduleRetrySection
          targetType={form.targetType}
          retryOnFailure={form.retryOnFailure}
          setRetryOnFailure={form.setRetryOnFailure}
        />
        <ScheduleTimingSection
          preset={form.preset}
          onChangePreset={form.onChangePreset}
          cronExpr={form.cronExpr}
          setCronExpr={form.setCronExpr}
          timezone={form.timezone}
          setTimezone={form.setTimezone}
          timezoneOptions={form.timezoneOptions}
          previewTz={form.previewTz}
          previewTimes={form.previewTimes}
          previewLoading={form.previewLoading}
          previewError={form.previewError}
          defaultTimezone={form.defaultTimezone}
          misfirePolicy={form.misfirePolicy}
          setMisfirePolicy={form.setMisfirePolicy}
          active={form.active}
          setActive={form.setActive}
        />
      </div>
    </ScheduleModalShell>
  );
}
