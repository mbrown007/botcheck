"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";
import type {
  FieldErrors,
  UseFormRegister,
  UseFormSetValue,
  UseFormWatch,
} from "react-hook-form";
import { useForm } from "react-hook-form";
import type { AIPersonaSummary, SpeechCapabilities } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  aiScenarioEditorFormSchema,
  createEmptyAIScenarioEditorValues,
  type AIScenarioEditorFormValues,
} from "@/lib/schemas/ai-scenario-editor";
import {
  buildCanonicalTtsVoice,
  deriveSttAuthoringState,
  deriveTtsAuthoringState,
  getDefaultModelForSttProvider,
  getDefaultSttProviderId,
  getDefaultVoiceForTtsProvider,
  OPENAI_TTS_VOICE_OPTIONS,
} from "@/lib/speech-authoring";

interface AIScenarioCreateWizardProps {
  personas: AIPersonaSummary[];
  speechCapabilities?: SpeechCapabilities;
  open: boolean;
  mode?: "create" | "edit";
  savingAIScenario: boolean;
  initialStep?: WizardStep;
  initialValues?: AIScenarioEditorFormValues | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: AIScenarioEditorFormValues) => Promise<boolean> | boolean;
}

type WizardStep = 0 | 1 | 2;

const STEP_TITLES = [
  "Basics",
  "Scenario Brief",
  "Evaluation & Data",
] as const;

function hasRuntimeOverride(value: string | null | undefined): boolean {
  return Boolean(value?.trim());
}

function countRuntimeOverrides(values: Pick<
  AIScenarioEditorFormValues,
  | "language"
  | "stt_endpointing_ms"
  | "transcript_merge_window_s"
  | "turn_timeout_s"
  | "max_duration_s"
  | "max_total_turns"
>): number {
  return [
    values.language,
    values.stt_endpointing_ms,
    values.transcript_merge_window_s,
    values.turn_timeout_s,
    values.max_duration_s,
    values.max_total_turns,
  ].filter((value) => hasRuntimeOverride(value)).length;
}

interface AIScenarioAdvancedRuntimeSettingsProps {
  open: boolean;
  runtimeOverrideCount: number;
  register: UseFormRegister<AIScenarioEditorFormValues>;
  errors: FieldErrors<AIScenarioEditorFormValues>;
  onToggle: () => void;
}

interface AIScenarioSpeechSettingsProps {
  register: UseFormRegister<AIScenarioEditorFormValues>;
  setValue: UseFormSetValue<AIScenarioEditorFormValues>;
  watch: UseFormWatch<AIScenarioEditorFormValues>;
  errors: FieldErrors<AIScenarioEditorFormValues>;
  speechCapabilities?: SpeechCapabilities;
}

export function AIScenarioSpeechSettings({
  register,
  setValue,
  watch,
  errors,
  speechCapabilities,
}: AIScenarioSpeechSettingsProps) {
  const ttsVoiceField = register("tts_voice");
  const rawTtsVoice = watch("tts_voice") ?? "";
  const sttProviderField = register("stt_provider");
  const sttModelField = register("stt_model");
  const rawSttProvider = watch("stt_provider") ?? "";
  const rawSttModel = watch("stt_model") ?? "";
  const ttsAuthoringState = deriveTtsAuthoringState(rawTtsVoice, speechCapabilities);
  const sttAuthoringState = deriveSttAuthoringState(
    rawSttProvider,
    rawSttModel,
    speechCapabilities
  );
  const activeTtsProvider = ttsAuthoringState.activeProvider;
  const selectedProviderId = ttsAuthoringState.currentProviderUnavailable
    ? ttsAuthoringState.parsed.providerId
    : ttsAuthoringState.parsed.isEmpty
      ? ""
      : ttsAuthoringState.displayProviderId;
  const rawSttProviderTrimmed = rawSttProvider.trim().toLowerCase();
  const rawSttModelTrimmed = rawSttModel.trim();
  const selectedSttProviderId = sttAuthoringState.currentProviderUnavailable
    ? rawSttProviderTrimmed
    : rawSttProviderTrimmed || (rawSttModelTrimmed ? sttAuthoringState.displayProviderId : "");
  const unresolvedTtsVoiceMessage =
    ttsAuthoringState.currentProviderUnavailable
      ? `Stored value uses an unavailable provider: ${ttsAuthoringState.parsed.canonical || ttsAuthoringState.parsed.raw}`
      : activeTtsProvider?.voice_mode === "freeform_id" &&
          ttsAuthoringState.displayProviderId &&
          ttsAuthoringState.parsed.isIncomplete
        ? "Voice ID is required for this provider."
        : undefined;
  const unresolvedSttProviderMessage = sttAuthoringState.currentProviderUnavailable
    ? `Stored value uses an unavailable STT provider: ${rawSttProviderTrimmed || rawSttProvider}`
    : undefined;

  function handleTtsProviderChange(nextProviderId: string) {
    if (!nextProviderId || nextProviderId === "__unavailable__") {
      setValue("tts_voice", "", {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: true,
      });
      return;
    }

    const nextVoice =
      ttsAuthoringState.parsed.providerId === nextProviderId &&
      !ttsAuthoringState.currentProviderUnavailable
        ? ttsAuthoringState.parsed.voice
        : getDefaultVoiceForTtsProvider(nextProviderId);
    setValue("tts_voice", buildCanonicalTtsVoice(nextProviderId, nextVoice), {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
  }

  function handleTtsVoiceChange(nextVoice: string) {
    const providerId =
      ttsAuthoringState.displayProviderId || ttsAuthoringState.parsed.providerId;
    if (!providerId) {
      return;
    }
    setValue("tts_voice", buildCanonicalTtsVoice(providerId, nextVoice), {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
  }

  function handleSttProviderChange(nextProviderId: string) {
    if (!nextProviderId || nextProviderId === "__unavailable__") {
      setValue("stt_provider", "", {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: true,
      });
      setValue("stt_model", "", {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: true,
      });
      return;
    }

    const nextModel =
      rawSttProviderTrimmed === nextProviderId && rawSttModelTrimmed
        ? rawSttModelTrimmed
        : getDefaultModelForSttProvider(nextProviderId);
    setValue("stt_provider", nextProviderId, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
    setValue("stt_model", nextModel, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
  }

  function handleSttModelChange(nextModel: string) {
    const providerId =
      selectedSttProviderId || getDefaultSttProviderId(speechCapabilities);
    if (!providerId) {
      return;
    }
    setValue("stt_provider", providerId, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
    setValue("stt_model", nextModel, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    });
  }

  return (
    <div className="grid gap-4">
      <div className="rounded-2xl border border-border/80 bg-bg-base/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
        <div className="px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">
            Voice Profile
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            Optional text-to-speech override for this AI scenario. Leave it blank to use the
            platform default voice.
          </p>
        </div>

        <div className="border-t border-border/70 px-4 pb-4 pt-3">
          <input {...ttsVoiceField} type="hidden" />

          {ttsAuthoringState.currentProviderUnavailable ? (
            <div className="mb-3 rounded-xl border border-warn-border bg-warn-bg/40 px-3 py-2 text-xs text-text-secondary">
              This scenario keeps its stored voice override, but that provider is not available in
              this deployment. Choose an available provider below or leave the field blank to return
              to the platform default.
            </div>
          ) : null}

          <div className="grid gap-3">
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                TTS Provider
              </span>
              <select
                data-testid="ai-scenario-tts-provider-select"
                value={selectedProviderId}
                onChange={(event) => handleTtsProviderChange(event.target.value)}
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="">Use platform default</option>
                {ttsAuthoringState.currentProviderUnavailable ? (
                  <option value={ttsAuthoringState.parsed.providerId}>
                    Unavailable: {ttsAuthoringState.parsed.providerId}
                  </option>
                ) : null}
                {ttsAuthoringState.availableProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-text-muted">
                Capability options follow the providers assigned to this tenant.
              </p>
            </label>

            {selectedProviderId && activeTtsProvider ? (
              activeTtsProvider.voice_mode === "static_select" &&
              activeTtsProvider.id === "openai" ? (
                <label className="block">
                  <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                    Voice
                  </span>
                  <select
                    data-testid="ai-scenario-tts-voice-select"
                    value={
                      ttsAuthoringState.displayVoice ||
                      getDefaultVoiceForTtsProvider(activeTtsProvider.id)
                    }
                    onChange={(event) => handleTtsVoiceChange(event.target.value)}
                    className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                  >
                    {OPENAI_TTS_VOICE_OPTIONS.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.label}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-text-muted">
                    Stores the canonical <code>{`${activeTtsProvider.id}:voice`}</code> form in
                    scenario config.
                  </p>
                </label>
              ) : (
                <label className="block">
                  <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                    Voice ID
                  </span>
                  <input
                    data-testid="ai-scenario-tts-voice-input"
                    value={ttsAuthoringState.displayVoice}
                    onChange={(event) => handleTtsVoiceChange(event.target.value)}
                    placeholder="Voice ID"
                    aria-invalid={unresolvedTtsVoiceMessage ? "true" : "false"}
                    className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-text-muted">
                    Voice IDs are provider-defined and stored exactly as entered.
                  </p>
                </label>
              )
            ) : (
              <div className="min-w-0 rounded-xl border border-dashed border-border/80 bg-bg-surface/60 px-3 py-3 text-sm text-text-secondary">
                Platform default speech settings will apply unless you pick an explicit provider.
              </div>
            )}
          </div>

          {errors.tts_voice?.message || unresolvedTtsVoiceMessage ? (
            <p className="mt-2 text-xs text-fail">
              {errors.tts_voice?.message ?? unresolvedTtsVoiceMessage}
            </p>
          ) : null}
        </div>
      </div>

      <div className="rounded-2xl border border-border/80 bg-bg-base/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
        <div className="px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">
            Listening Profile
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            Optional speech-to-text override for this AI scenario. Leave it blank to use the
            platform default provider and model.
          </p>
        </div>

        <div className="border-t border-border/70 px-4 pb-4 pt-3">
          <input {...sttProviderField} type="hidden" />
          <input {...sttModelField} type="hidden" />

          {sttAuthoringState.currentProviderUnavailable ? (
            <div className="mb-3 rounded-xl border border-warn-border bg-warn-bg/40 px-3 py-2 text-xs text-text-secondary">
              This scenario keeps its stored listening override, but that provider is not available
              in this deployment. Choose an available provider below or leave the fields blank to
              return to the platform default.
            </div>
          ) : null}

          <div className="grid gap-3">
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                STT Provider
              </span>
              <select
                data-testid="ai-scenario-stt-provider-select"
                value={selectedSttProviderId}
                onChange={(event) => handleSttProviderChange(event.target.value)}
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="">Use platform default</option>
                {sttAuthoringState.currentProviderUnavailable ? (
                  <option value={rawSttProviderTrimmed}>
                    Unavailable: {rawSttProviderTrimmed}
                  </option>
                ) : null}
                {sttAuthoringState.availableProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-text-muted">
                Provider availability follows the same tenant provider access contract as graph
                scenarios.
              </p>
            </label>

            {selectedSttProviderId ? (
              <label className="block">
                <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                  STT Model
                </span>
                <input
                  data-testid="ai-scenario-stt-model-input"
                  value={
                    rawSttModelTrimmed ||
                    sttAuthoringState.displayModel ||
                    getDefaultModelForSttProvider(selectedSttProviderId)
                  }
                  onChange={(event) => handleSttModelChange(event.target.value)}
                  placeholder="Model ID"
                  aria-invalid={unresolvedSttProviderMessage ? "true" : "false"}
                  className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                />
                <p className="mt-1 text-xs text-text-muted">
                  Model identifiers are provider-defined and stored exactly as entered.
                </p>
              </label>
            ) : (
              <div className="min-w-0 rounded-xl border border-dashed border-border/80 bg-bg-surface/60 px-3 py-3 text-sm text-text-secondary">
                Platform default listening settings will apply unless you pick an explicit provider.
              </div>
            )}
          </div>

          {errors.stt_provider?.message || errors.stt_model?.message || unresolvedSttProviderMessage ? (
            <p className="mt-2 text-xs text-fail">
              {errors.stt_provider?.message ??
                errors.stt_model?.message ??
                unresolvedSttProviderMessage}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function AIScenarioAdvancedRuntimeSettings({
  open,
  runtimeOverrideCount,
  register,
  errors,
  onToggle,
}: AIScenarioAdvancedRuntimeSettingsProps) {
  return (
    <div className="rounded-2xl border border-border/80 bg-bg-base/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
      >
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">
            Advanced Runtime Settings
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            Optional timing and transcript controls for AI-run behavior. Speech provider overrides
            are managed above.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-medium text-text-primary">
            {runtimeOverrideCount > 0 ? `${runtimeOverrideCount} overrides` : "Optional"}
          </p>
          <p className="mt-1 text-xs text-text-muted">{open ? "Hide" : "Show"}</p>
        </div>
      </button>

      {open ? (
        <div className="border-t border-border/70 px-4 pb-4 pt-3">
          <div className="mb-3 rounded-xl border border-brand/20 bg-brand-muted/20 px-3 py-2 text-xs text-text-secondary">
            These settings tune call timing and transcript handling only. Speech provider and
            model overrides live in the profiles above.
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                Language
              </span>
              <input
                data-testid="ai-scenario-runtime-language-input"
                {...register("language")}
                placeholder="en-US"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              <p className="mt-1 text-xs text-text-muted">
                BCP-47 language tag applied to listening and synthesis.
              </p>
            </label>

            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                STT Endpointing (ms)
              </span>
              <input
                data-testid="ai-scenario-runtime-stt-endpointing-input"
                {...register("stt_endpointing_ms")}
                type="number"
                min={0}
                step={1}
                placeholder="2000"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              {errors.stt_endpointing_ms ? (
                <p className="mt-1 text-xs text-fail">{errors.stt_endpointing_ms.message}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Silence window before an utterance is considered finished.
                </p>
              )}
            </label>

            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                Transcript Merge Window (s)
              </span>
              <input
                data-testid="ai-scenario-runtime-transcript-merge-window-input"
                {...register("transcript_merge_window_s")}
                type="number"
                min={0.1}
                step={0.1}
                placeholder="1.5"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              {errors.transcript_merge_window_s ? (
                <p className="mt-1 text-xs text-fail">{errors.transcript_merge_window_s.message}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Holds follow-up transcript fragments together before closing the turn.
                </p>
              )}
            </label>

            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                Turn Timeout (s)
              </span>
              <input
                data-testid="ai-scenario-runtime-turn-timeout-input"
                {...register("turn_timeout_s")}
                type="number"
                min={0.1}
                step={0.1}
                placeholder="15"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              {errors.turn_timeout_s ? (
                <p className="mt-1 text-xs text-fail">{errors.turn_timeout_s.message}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Default time to wait before the bot is marked timed out.
                </p>
              )}
            </label>

            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                Max Duration (s)
              </span>
              <input
                data-testid="ai-scenario-runtime-max-duration-input"
                {...register("max_duration_s")}
                type="number"
                min={0.1}
                step={0.1}
                placeholder="300"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              {errors.max_duration_s ? (
                <p className="mt-1 text-xs text-fail">{errors.max_duration_s.message}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Hard wall-clock cap for the full AI scenario run.
                </p>
              )}
            </label>

            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                Max Total Turns
              </span>
              <input
                data-testid="ai-scenario-runtime-max-total-turns-input"
                {...register("max_total_turns")}
                type="number"
                min={1}
                step={1}
                placeholder="50"
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
              {errors.max_total_turns ? (
                <p className="mt-1 text-xs text-fail">{errors.max_total_turns.message}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Safety cap to stop unexpectedly long or looping calls.
                </p>
              )}
            </label>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AIScenarioCreateWizard({
  personas,
  speechCapabilities,
  open,
  mode = "create",
  savingAIScenario,
  initialStep = 0,
  initialValues,
  onOpenChange,
  onSubmit,
}: AIScenarioCreateWizardProps) {
  const [step, setStep] = useState<WizardStep>(initialStep);
  const [advancedRuntimeOpen, setAdvancedRuntimeOpen] = useState(() =>
    countRuntimeOverrides(initialValues ?? createEmptyAIScenarioEditorValues()) > 0
  );
  const form = useForm<AIScenarioEditorFormValues>({
    resolver: zodResolver(aiScenarioEditorFormSchema),
    mode: "onChange",
    defaultValues: createEmptyAIScenarioEditorValues(),
  });
  const {
    register,
    handleSubmit,
    trigger,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = form;
  const languageValue = watch("language");
  const sttEndpointingValue = watch("stt_endpointing_ms");
  const transcriptMergeWindowValue = watch("transcript_merge_window_s");
  const turnTimeoutValue = watch("turn_timeout_s");
  const maxDurationValue = watch("max_duration_s");
  const maxTotalTurnsValue = watch("max_total_turns");
  const runtimeOverrideCount = countRuntimeOverrides({
    language: languageValue,
    stt_endpointing_ms: sttEndpointingValue,
    transcript_merge_window_s: transcriptMergeWindowValue,
    turn_timeout_s: turnTimeoutValue,
    max_duration_s: maxDurationValue,
    max_total_turns: maxTotalTurnsValue,
  });

  useEffect(() => {
    if (!open) {
      reset(createEmptyAIScenarioEditorValues());
      setStep(initialStep);
      setAdvancedRuntimeOpen(false);
    }
  }, [initialStep, open, reset]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const nextValues = initialValues ?? createEmptyAIScenarioEditorValues();
    reset(nextValues);
    setStep(initialStep);
    setAdvancedRuntimeOpen(countRuntimeOverrides(nextValues) > 0);
  }, [initialStep, initialValues, open, reset]);

  const stepFields = useMemo<Record<WizardStep, Array<keyof AIScenarioEditorFormValues>>>(
    () => ({
      0: ["name", "publicId", "namespace", "personaId"],
      1: ["scenarioBrief", "scenarioFactsText"],
      2: ["evaluationObjective", "openingStrategy", "datasetSource", "scoringProfile"],
    }),
    []
  );

  async function handleNext() {
    const isValid = await trigger(stepFields[step]);
    if (!isValid || step === 2) {
      return;
    }
    setStep((current) => (current + 1) as WizardStep);
  }

  function handleBack() {
    if (step === 0) {
      return;
    }
    setStep((current) => (current - 1) as WizardStep);
  }

  async function handleWizardSubmit(values: AIScenarioEditorFormValues) {
    const created = await onSubmit(values);
    if (!created) {
      return;
    }
    onOpenChange(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[80] max-h-[calc(100vh-2rem)] w-[min(920px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface shadow-2xl">
          <div className="border-b border-border px-6 py-5">
            <div className="flex items-start justify-between gap-6">
              <div>
                <Dialog.Title className="text-xl font-semibold text-text-primary">
                  {mode === "edit" ? "Edit AI Scenario" : "Create AI Scenario"}
                </Dialog.Title>
                <Dialog.Description className="mt-1 text-sm text-text-secondary">
                  {mode === "edit"
                    ? "Update the scenario brief, persona assignment, and evaluation criteria without leaving the catalog."
                    : "Build an intent-first caller simulation with a persona, concrete scenario brief, and explicit success objective."}
                </Dialog.Description>
              </div>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary"
              >
                Close
              </button>
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {STEP_TITLES.map((title, index) => {
                const active = index === step;
                const completed = index < step;
                return (
                  <div
                    key={title}
                    className={[
                      "rounded-xl border px-3 py-2",
                      active
                        ? "border-brand bg-brand-muted/30"
                        : completed
                          ? "border-pass-border bg-pass-bg/40"
                          : "border-border bg-bg-base/60",
                    ].join(" ")}
                  >
                    <p className="text-[10px] uppercase tracking-[0.18em] text-text-muted">
                      Step {index + 1}
                    </p>
                    <p className="mt-1 text-sm font-medium text-text-primary">{title}</p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_240px]">
            <div className="min-w-0 px-6 py-5">
              {step === 0 ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-sm font-medium text-text-primary">Choose the identity and handle.</p>
                    <p className="mt-1 text-sm text-text-secondary">
                      Start with a clear scenario name, optional stable public ID, and the persona
                      who will role-play the caller.
                    </p>
                  </div>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Scenario Name
                    </span>
                    <input
                      data-testid="ai-scenario-name-input"
                      {...register("name")}
                      placeholder="Delayed flight reassurance"
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.name ? <p className="mt-1 text-xs text-fail">{errors.name.message}</p> : null}
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Public ID
                    </span>
                    <input
                      data-testid="ai-scenario-public-id-input"
                      {...register("publicId")}
                      placeholder="Optional. Auto-generated from the name."
                      disabled={mode === "edit"}
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.publicId ? (
                      <p className="mt-1 text-xs text-fail">{errors.publicId.message}</p>
                    ) : (
                      <p className="mt-1 text-xs text-text-muted">
                        {mode === "edit"
                          ? "Public IDs stay stable once created."
                          : "Leave blank unless you need a stable external identifier."}
                      </p>
                    )}
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Namespace
                    </span>
                    <input
                      data-testid="ai-scenario-namespace-input"
                      {...register("namespace")}
                      placeholder="support/refunds"
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.namespace ? (
                      <p className="mt-1 text-xs text-fail">{errors.namespace.message}</p>
                    ) : (
                      <p className="mt-1 text-xs text-text-muted">
                        Optional catalog path for grouping AI scenarios by workflow or product area.
                      </p>
                    )}
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Persona
                    </span>
                    <select
                      data-testid="ai-scenario-persona-select"
                      {...register("personaId")}
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">Select persona…</option>
                      {personas.map((row) => (
                        <option key={row.persona_id} value={row.persona_id}>
                          {row.display_name}
                        </option>
                      ))}
                    </select>
                    {errors.personaId ? (
                      <p className="mt-1 text-xs text-fail">{errors.personaId.message}</p>
                    ) : null}
                  </label>

                  {personas.length === 0 ? (
                    <div className="rounded-xl border border-warn-border bg-warn-bg/40 px-4 py-3 text-sm text-text-secondary">
                      No personas available yet. Create one first in{" "}
                      <Link href="/personas" className="font-medium text-brand underline-offset-2 hover:underline">
                        Personas
                      </Link>
                      .
                    </div>
                  ) : null}
                </div>
              ) : null}

              {step === 1 ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-sm font-medium text-text-primary">Describe the caller’s situation.</p>
                    <p className="mt-1 text-sm text-text-secondary">
                      Explain intent, context, constraints, and emotional pressure. This is the
                      main brief the AI caller will role-play.
                    </p>
                  </div>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Scenario Brief
                    </span>
                    <textarea
                      data-testid="ai-scenario-brief-input"
                      {...register("scenarioBrief")}
                      rows={8}
                      placeholder="You have a delayed Ryanair flight from Sydney to New York, you are at the airport with two small children, and need confirmation on when the flight will leave and what support is available."
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.scenarioBrief ? (
                      <p className="mt-1 text-xs text-fail">{errors.scenarioBrief.message}</p>
                    ) : null}
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Structured Facts JSON
                    </span>
                    <textarea
                      data-testid="ai-scenario-facts-input"
                      {...register("scenarioFactsText")}
                      rows={5}
                      placeholder={'{ "booking_ref": "ABC123", "airline": "Ryanair" }'}
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 font-mono text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.scenarioFactsText ? (
                      <p className="mt-1 text-xs text-fail">{errors.scenarioFactsText.message}</p>
                    ) : (
                      <p className="mt-1 text-xs text-text-muted">
                        Optional. Use this for machine-readable details like booking refs, route,
                        plan type, or account status.
                      </p>
                    )}
                  </label>
                </div>
              ) : null}

              {step === 2 ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-sm font-medium text-text-primary">Define success and runtime behavior.</p>
                    <p className="mt-1 text-sm text-text-secondary">
                      Tell the judge what good looks like and set whether the caller waits for the
                      bot greeting or speaks first.
                    </p>
                  </div>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Evaluation Objective
                    </span>
                    <textarea
                      data-testid="ai-scenario-objective-input"
                      {...register("evaluationObjective")}
                      rows={5}
                      placeholder="The bot should confirm the delay accurately, explain likely next steps, and respond with empathy appropriate for a stressed parent travelling with children."
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {errors.evaluationObjective ? (
                      <p className="mt-1 text-xs text-fail">{errors.evaluationObjective.message}</p>
                    ) : null}
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                      Opening Strategy
                    </span>
                    <select
                      data-testid="ai-scenario-opening-strategy"
                      {...register("openingStrategy")}
                      className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="wait_for_bot_greeting">Wait for bot greeting</option>
                      <option value="caller_opens">Caller opens first</option>
                    </select>
                  </label>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                        Dataset Source
                      </span>
                      <input
                        {...register("datasetSource")}
                        placeholder="Optional"
                        className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                    </label>

                    <label className="block">
                      <span className="mb-1 block text-xs uppercase tracking-wide text-text-muted">
                        Scoring Profile
                      </span>
                      <input
                        {...register("scoringProfile")}
                        placeholder="Optional"
                        className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                    </label>
                  </div>

                  <AIScenarioSpeechSettings
                    register={register}
                    setValue={setValue}
                    watch={watch}
                    errors={errors}
                    speechCapabilities={speechCapabilities}
                  />

                  <AIScenarioAdvancedRuntimeSettings
                    open={advancedRuntimeOpen}
                    runtimeOverrideCount={runtimeOverrideCount}
                    register={register}
                    errors={errors}
                    onToggle={() => setAdvancedRuntimeOpen((current) => !current)}
                  />
                </div>
              ) : null}
            </div>

            <aside className="min-w-0 border-t border-border bg-bg-base/50 px-6 py-5 xl:border-l xl:border-t-0">
              <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">
                Step Guidance
              </p>
              {step === 0 ? (
                <div className="mt-3 space-y-3 text-sm text-text-secondary">
                  <p>
                    Use the scenario name for the operator-facing title. Keep the persona reusable
                    and the scenario specific.
                  </p>
                  <p>
                    The public ID is optional. Only fill it if you need a stable handle for
                    schedules, automations, or external references.
                  </p>
                </div>
              ) : null}
              {step === 1 ? (
                <div className="mt-3 space-y-3 text-sm text-text-secondary">
                  <p>
                    Write the brief the way you would hand it to a human tester: goal, context,
                    urgency, and notable constraints.
                  </p>
                  <p>
                    Facts JSON is best for structured values the runtime or judge may want to read
                    exactly.
                  </p>
                </div>
              ) : null}
              {step === 2 ? (
                <div className="mt-3 space-y-3 text-sm text-text-secondary">
                  <p>
                    Keep the evaluation objective outcome-focused. It should describe success, not
                    restate the brief.
                  </p>
                  <p>
                    Use “Wait for bot greeting” unless the test specifically needs the caller to
                    speak first.
                  </p>
                  <p>
                    Runtime overrides are optional. Use them only when the caller needs different
                    timing or transcript behavior than the default AI scenario profile.
                  </p>
                </div>
              ) : null}
            </aside>
          </div>

          <div className="flex items-center justify-between border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={handleBack} disabled={step === 0 || savingAIScenario}>
              Back
            </Button>
            <div className="flex items-center gap-2">
              {step < 2 ? (
                <Button onClick={() => void handleNext()} disabled={savingAIScenario}>
                  Next
                </Button>
              ) : (
                <Button
                  data-testid="ai-scenario-create-btn"
                  onClick={handleSubmit(handleWizardSubmit)}
                  disabled={savingAIScenario}
                >
                  {savingAIScenario
                    ? mode === "edit"
                      ? "Saving…"
                      : "Creating…"
                    : mode === "edit"
                      ? "Save Changes"
                      : "Create AI Scenario"}
                </Button>
              )}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
