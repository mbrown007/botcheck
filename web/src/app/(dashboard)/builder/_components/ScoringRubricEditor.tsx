"use client";

import React from "react";
import {
  useFieldArray,
  useWatch,
  type Control,
  type FieldErrors,
  type UseFormRegister,
} from "react-hook-form";
import { cn } from "@/lib/utils";
import {
  SCORING_DIMENSION_OPTIONS,
  type ScenarioMetaFormValues,
} from "@/lib/schemas/scenario-meta";
import { MetadataFieldLabel } from "./MetadataFieldLabel";

interface ScoringRubricEditorProps {
  control: Control<ScenarioMetaFormValues>;
  register: UseFormRegister<ScenarioMetaFormValues>;
  errors: FieldErrors<ScenarioMetaFormValues>;
  onFocusField: () => void;
  showTitle?: boolean;
}

export function ScoringRubricEditor({
  control,
  register,
  errors,
  onFocusField,
  showTitle = true,
}: ScoringRubricEditorProps) {
  const watchedRubric = useWatch({
    control,
    name: "scoring_rubric",
  });
  const { fields, append, remove } = useFieldArray({
    control,
    name: "scoring_rubric",
  });

  const totalWeight = (watchedRubric ?? []).reduce((sum, row) => {
    const weight = row?.weight;
    if (typeof weight !== "number" || !Number.isFinite(weight)) {
      return sum;
    }
    return sum + weight;
  }, 0);
  const hasRows = fields.length > 0;
  const weightDelta = Math.abs(totalWeight - 1);
  const weightOffTarget = hasRows && weightDelta > 0.01;

  return (
    <div className="rounded-md border border-border bg-bg-surface/40 p-2">
      <div className="flex items-center justify-between gap-2">
        {showTitle ? (
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Scoring Rubric</p>
        ) : (
          <div />
        )}
        <button
          type="button"
          onClick={() =>
            append({
              dimension: "routing",
              threshold: 0.8,
              weight: 0.1,
              gate: false,
              custom_prompt: "",
            })
          }
          className="rounded border border-border px-2 py-1 text-[10px] text-text-secondary hover:text-text-primary"
        >
          + Add Dimension
        </button>
      </div>
      {fields.length === 0 ? (
        <p className="mt-2 text-[11px] text-text-muted">
          No rubric overrides configured.
        </p>
      ) : (
        <>
          <p
            className={cn(
              "mt-2 text-[11px]",
              weightOffTarget ? "text-warn" : "text-text-muted"
            )}
          >
            Total weight: {totalWeight.toFixed(2)} / 1.00
            {weightOffTarget ? " (adjust weights to sum to 1.00)" : ""}
          </p>

          <div className="mt-2 space-y-2">
            {fields.map((field, index) => {
              const dimensionError = errors.scoring_rubric?.[index]?.dimension?.message;
              const thresholdError = errors.scoring_rubric?.[index]?.threshold?.message;
              const weightError = errors.scoring_rubric?.[index]?.weight?.message;

              return (
                <div
                  key={field.id}
                  className="rounded border border-border bg-bg-base p-2"
                  data-testid={`rubric-row-${index}`}
                >
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                    <label className="block text-[10px] uppercase tracking-wide text-text-muted">
                      <MetadataFieldLabel
                        label="Dimension"
                        help="Which scoring dimension this rubric row evaluates, such as routing, policy, or reliability."
                      />
                      <select
                        {...register(`scoring_rubric.${index}.dimension`)}
                        onFocus={onFocusField}
                        className={cn(
                          "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                          dimensionError ? "border-fail-border" : null
                        )}
                      >
                        {SCORING_DIMENSION_OPTIONS.map((dimension) => (
                          <option key={dimension} value={dimension}>
                            {dimension}
                          </option>
                        ))}
                      </select>
                      {dimensionError ? (
                        <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                          {dimensionError}
                        </p>
                      ) : null}
                    </label>

                    <label className="block text-[10px] uppercase tracking-wide text-text-muted">
                      <MetadataFieldLabel
                        label="Threshold"
                        help="Score below this value is considered a failure for this dimension."
                      />
                      <input
                        {...register(`scoring_rubric.${index}.threshold`, {
                          setValueAs: (value: unknown) => {
                            if (typeof value === "number") {
                              return value;
                            }
                            if (typeof value === "string") {
                              const parsed = Number(value);
                              return Number.isFinite(parsed) ? parsed : Number.NaN;
                            }
                            return Number.NaN;
                          },
                        })}
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        onFocus={onFocusField}
                        className={cn(
                          "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                          thresholdError ? "border-fail-border" : null
                        )}
                      />
                      {thresholdError ? (
                        <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                          {thresholdError}
                        </p>
                      ) : null}
                    </label>

                    <label className="block text-[10px] uppercase tracking-wide text-text-muted">
                      <MetadataFieldLabel
                        label="Weight"
                        help="Relative contribution of this dimension to the overall score. All weights should usually sum to 1.00."
                      />
                      <input
                        {...register(`scoring_rubric.${index}.weight`, {
                          setValueAs: (value: unknown) => {
                            if (typeof value === "number") {
                              return value;
                            }
                            if (typeof value === "string") {
                              const parsed = Number(value);
                              return Number.isFinite(parsed) ? parsed : Number.NaN;
                            }
                            return Number.NaN;
                          },
                        })}
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        onFocus={onFocusField}
                        className={cn(
                          "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                          weightError ? "border-fail-border" : null
                        )}
                      />
                      {weightError ? (
                        <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                          {weightError}
                        </p>
                      ) : null}
                    </label>

                    <div className="flex items-end justify-end gap-2">
                      <label className="mb-1 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-text-muted">
                        <input
                          {...register(`scoring_rubric.${index}.gate`)}
                          type="checkbox"
                          onFocus={onFocusField}
                          className="h-3.5 w-3.5 rounded border border-border bg-bg-base accent-brand"
                        />
                        <MetadataFieldLabel
                          label="Gate"
                          help="If enabled, a failure on this dimension blocks the overall run gate."
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => remove(index)}
                        className="mb-1 rounded border border-fail-border px-2 py-1 text-[10px] text-fail hover:bg-fail-bg"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  <label className="mt-2 block text-[10px] uppercase tracking-wide text-text-muted">
                    <MetadataFieldLabel
                      label="Custom Guidance"
                      help="Optional tenant-defined scoring guidance for this dimension. Leave blank to use the shared default rubric meaning."
                    />
                    <textarea
                      {...register(`scoring_rubric.${index}.custom_prompt`)}
                      onFocus={onFocusField}
                      rows={2}
                      placeholder="Optional dimension-specific judging guidance"
                      data-testid={`rubric-custom-prompt-${index}`}
                      className="mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                  </label>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
