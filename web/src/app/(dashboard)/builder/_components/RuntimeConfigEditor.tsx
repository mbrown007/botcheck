"use client";

import React from "react";
import type {
  FieldErrors,
  UseFormRegister,
  UseFormSetValue,
  UseFormWatch,
} from "react-hook-form";
import type { SpeechCapabilities } from "@/lib/api";
import { getScenarioSchemaHint } from "@/lib/scenario-schema-hints";
import { cn } from "@/lib/utils";
import type { ScenarioMetaFormValues } from "@/lib/schemas/scenario-meta";
import {
  deriveSttAuthoringState,
  OPENAI_TTS_VOICE_OPTIONS,
  buildCanonicalTtsVoice,
  deriveTtsAuthoringState,
  getDefaultModelForSttProvider,
  getDefaultVoiceForTtsProvider,
} from "@/lib/speech-authoring";
import { MetadataFieldLabel } from "./MetadataFieldLabel";
import { SchemaHintText } from "./SchemaHintText";

interface RuntimeConfigEditorProps {
  register: UseFormRegister<ScenarioMetaFormValues>;
  setValue: UseFormSetValue<ScenarioMetaFormValues>;
  watch: UseFormWatch<ScenarioMetaFormValues>;
  errors: FieldErrors<ScenarioMetaFormValues>;
  onFocusField: () => void;
  speechCapabilities?: SpeechCapabilities;
  showTitle?: boolean;
}

export function RuntimeConfigEditor({
  register,
  setValue,
  watch,
  errors,
  onFocusField,
  speechCapabilities,
  showTitle = true,
}: RuntimeConfigEditorProps) {
  const maxTotalTurnsField = register("max_total_turns");
  const turnTimeoutField = register("turn_timeout_s");
  const maxDurationField = register("max_duration_s");
  const botJoinTimeoutField = register("bot_join_timeout_s");
  const transferTimeoutField = register("transfer_timeout_s");
  const initialDrainField = register("initial_drain_s");
  const interTurnPauseField = register("inter_turn_pause_s");
  const transcriptMergeWindowField = register("transcript_merge_window_s");
  const pauseThresholdField = register("pause_threshold_ms");
  const sttEndpointingField = register("stt_endpointing_ms");
  const languageField = register("language");
  const sttProviderField = register("stt_provider");
  const sttModelField = register("stt_model");
  const rawSttProvider = watch("stt_provider");
  const rawSttModel = watch("stt_model");
  const sttAuthoringState = deriveSttAuthoringState(
    rawSttProvider ?? "",
    rawSttModel ?? "",
    speechCapabilities
  );
  const activeSttProvider = sttAuthoringState.activeProvider;
  const unresolvedSttProviderMessage = sttAuthoringState.currentProviderUnavailable
    ? "Speech-to-text provider metadata is unavailable for this deployment."
    : undefined;
  const ttsVoiceField = register("tts_voice");
  const rawTtsVoice = watch("tts_voice");
  const ttsAuthoringState = deriveTtsAuthoringState(rawTtsVoice ?? "", speechCapabilities);
  const activeTtsProvider = ttsAuthoringState.activeProvider;
  const unresolvedTtsVoiceMessage =
    ttsAuthoringState.currentProviderUnavailable
      ? `Current scenario uses an unavailable provider: ${ttsAuthoringState.parsed.canonical || ttsAuthoringState.parsed.raw}`
      : activeTtsProvider?.voice_mode === "freeform_id" &&
          ttsAuthoringState.displayProviderId &&
          ttsAuthoringState.parsed.isIncomplete
        ? "Voice ID is required for this provider."
        : undefined;
  const timingGateP95ResponseGapField = register("timing_gate_p95_response_gap_ms");
  const timingWarnP95ResponseGapField = register("timing_warn_p95_response_gap_ms");
  const timingGateInterruptionsField = register("timing_gate_interruptions_count");
  const timingWarnInterruptionsField = register("timing_warn_interruptions_count");
  const timingGateLongPauseField = register("timing_gate_long_pause_count");
  const timingWarnLongPauseField = register("timing_warn_long_pause_count");
  const timingGateRecoveryField = register("timing_gate_interruption_recovery_pct");
  const timingWarnRecoveryField = register("timing_warn_interruption_recovery_pct");
  const timingGateEfficiencyField = register("timing_gate_turn_taking_efficiency_pct");
  const timingWarnEfficiencyField = register("timing_warn_turn_taking_efficiency_pct");

  function handleTtsProviderChange(nextProviderId: string) {
    if (!nextProviderId || nextProviderId === "__unavailable__") {
      return;
    }
    const nextVoice =
      ttsAuthoringState.parsed.providerId === nextProviderId &&
      !ttsAuthoringState.currentProviderUnavailable
        ? ttsAuthoringState.parsed.voice
        : getDefaultVoiceForTtsProvider(nextProviderId);
    setValue(
      "tts_voice",
      buildCanonicalTtsVoice(nextProviderId, nextVoice),
      { shouldDirty: true, shouldTouch: true, shouldValidate: true }
    );
  }

  function handleTtsVoiceChange(nextVoice: string) {
    const providerId =
      ttsAuthoringState.displayProviderId || ttsAuthoringState.parsed.providerId;
    if (!providerId) {
      return;
    }
    setValue(
      "tts_voice",
      buildCanonicalTtsVoice(providerId, nextVoice),
      { shouldDirty: true, shouldTouch: true, shouldValidate: true }
    );
  }

  function handleSttProviderChange(nextProviderId: string) {
    if (!nextProviderId || nextProviderId === "__unavailable__") {
      return;
    }

    const normalizedRawProvider = (rawSttProvider ?? "").trim().toLowerCase();
    const nextModel =
      normalizedRawProvider === nextProviderId && (rawSttModel ?? "").trim()
        ? (rawSttModel ?? "").trim()
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
      sttAuthoringState.currentProviderUnavailable
        ? (rawSttProvider ?? "").trim().toLowerCase()
        : sttAuthoringState.displayProviderId;
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
    <div className="rounded-md border border-border bg-bg-surface/40 p-2">
      {showTitle ? (
        <p className="text-[11px] uppercase tracking-wide text-text-muted">Runtime Config</p>
      ) : null}

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Max Total Turns"
            help="Hard stop for the total executed turns. Protects against loops or unexpectedly long flows."
          />
          <input
            {...maxTotalTurnsField}
            data-testid="runtime-max-total-turns-input"
            type="number"
            min={1}
            step={1}
            onFocus={onFocusField}
            placeholder="50"
            aria-invalid={errors.max_total_turns ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.max_total_turns ? "border-fail-border" : null
            )}
          />
          {errors.max_total_turns?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.max_total_turns.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "max_total_turns"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Turn Timeout (s)"
            help="Default time to wait for the bot’s response on a normal turn before marking it timed out."
          />
          <input
            {...turnTimeoutField}
            data-testid="runtime-turn-timeout-input"
            type="number"
            min={1}
            step={1}
            onFocus={onFocusField}
            placeholder="15"
            aria-invalid={errors.turn_timeout_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.turn_timeout_s ? "border-fail-border" : null
            )}
          />
          {errors.turn_timeout_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.turn_timeout_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "turn_timeout_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Max Duration (s)"
            help="Wall-clock cap for the whole scenario. The reaper force-closes runs that exceed this."
          />
          <input
            {...maxDurationField}
            type="number"
            step={0.1}
            onFocus={onFocusField}
            placeholder="300"
            aria-invalid={errors.max_duration_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.max_duration_s ? "border-fail-border" : null
            )}
          />
          {errors.max_duration_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.max_duration_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "max_duration_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Bot Join Timeout (s)"
            help="How long BotCheck waits for the bot participant to join the room before failing startup."
          />
          <input
            {...botJoinTimeoutField}
            type="number"
            min={0.1}
            step={0.1}
            onFocus={onFocusField}
            placeholder="60"
            aria-invalid={errors.bot_join_timeout_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.bot_join_timeout_s ? "border-fail-border" : null
            )}
          />
          {errors.bot_join_timeout_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.bot_join_timeout_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "bot_join_timeout_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Transfer Timeout (s)"
            help="Extended timeout used for transfer-style turns where hold music and agent pickup can take longer."
          />
          <input
            {...transferTimeoutField}
            type="number"
            min={0.1}
            step={0.1}
            onFocus={onFocusField}
            placeholder="35"
            aria-invalid={errors.transfer_timeout_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.transfer_timeout_s ? "border-fail-border" : null
            )}
          />
          {errors.transfer_timeout_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.transfer_timeout_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "transfer_timeout_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Initial Drain (s)"
            help="Audio discarded immediately after connect before the scenario starts. Use to skip IVR intros, disclaimers, or hold music."
          />
          <input
            {...initialDrainField}
            type="number"
            min={0}
            step={0.1}
            onFocus={onFocusField}
            placeholder="2"
            aria-invalid={errors.initial_drain_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.initial_drain_s ? "border-fail-border" : null
            )}
          />
          {errors.initial_drain_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.initial_drain_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "initial_drain_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Inter-turn Pause (s)"
            help="Extra pause inserted between turns to make the caller pacing more natural or to let the bot settle."
          />
          <input
            {...interTurnPauseField}
            type="number"
            min={0}
            step={0.1}
            onFocus={onFocusField}
            placeholder="0"
            aria-invalid={errors.inter_turn_pause_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.inter_turn_pause_s ? "border-fail-border" : null
            )}
          />
          {errors.inter_turn_pause_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.inter_turn_pause_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "inter_turn_pause_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Merge Window (s)"
            help="How long transcript segments are merged before a bot utterance is considered complete."
          />
          <input
            {...transcriptMergeWindowField}
            type="number"
            min={0.1}
            step={0.1}
            onFocus={onFocusField}
            placeholder="1.5"
            aria-invalid={errors.transcript_merge_window_s ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.transcript_merge_window_s ? "border-fail-border" : null
            )}
          />
          {errors.transcript_merge_window_s?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.transcript_merge_window_s.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "transcript_merge_window_s"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="Pause Threshold (ms)"
            help="A gap above this threshold is counted as a long pause in reliability/timing scoring."
          />
          <input
            {...pauseThresholdField}
            type="number"
            min={0}
            step={1}
            onFocus={onFocusField}
            placeholder="2000"
            aria-invalid={errors.pause_threshold_ms ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.pause_threshold_ms ? "border-fail-border" : null
            )}
          />
          {errors.pause_threshold_ms?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.pause_threshold_ms.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "pause_threshold_ms"])} />
        </label>

        <label className="block text-[11px] uppercase tracking-wide text-text-muted">
          <MetadataFieldLabel
            label="STT Endpointing (ms)"
            help="Silence duration used by STT to decide that an utterance has finished."
          />
          <input
            {...sttEndpointingField}
            type="number"
            min={0}
            step={1}
            onFocus={onFocusField}
            placeholder="2000"
            aria-invalid={errors.stt_endpointing_ms ? "true" : "false"}
            className={cn(
              "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
              errors.stt_endpointing_ms ? "border-fail-border" : null
            )}
          />
          {errors.stt_endpointing_ms?.message ? (
            <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
              {errors.stt_endpointing_ms.message}
            </p>
          ) : null}
          <SchemaHintText hint={getScenarioSchemaHint(["config", "stt_endpointing_ms"])} />
        </label>
      </div>

      <div className="mt-3 rounded-md border border-border bg-bg-base/60 p-2">
        <div className="flex flex-col gap-1">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Speech Runtime</p>
          <p className="text-[10px] normal-case tracking-normal text-text-muted">
            Language, STT, and TTS are grouped here because the Builder side panel is narrow. This keeps provider controls readable instead of forcing them into a single viewport-wide grid.
          </p>
        </div>

        <div className="mt-3 space-y-3">
          <label className="block max-w-sm text-[11px] text-text-muted">
            <MetadataFieldLabel
              label="Language"
              help="BCP-47 language tag applied to ASR and TTS. Example: en-US."
            />
            <input
              {...languageField}
              onFocus={onFocusField}
              placeholder="en-US"
              aria-invalid={errors.language ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.language ? "border-fail-border" : null
              )}
            />
            {errors.language?.message ? (
              <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                {errors.language.message}
              </p>
            ) : null}
            <SchemaHintText hint={getScenarioSchemaHint(["config", "language"])} />
          </label>

          <div className="rounded-md border border-border bg-bg-surface/60 p-2.5">
            <div className="flex flex-col gap-1">
              <p className="text-[11px] uppercase tracking-wide text-text-muted">
                Speech-to-Text
              </p>
              <p className="text-[10px] normal-case tracking-normal text-text-muted">
                Provider availability follows the tenant-assigned provider inventory; the Builder stores the exact pair as `config.stt_provider` and `config.stt_model`.
              </p>
            </div>

            <input {...sttProviderField} type="hidden" />
            <div className="mt-2 grid gap-2">
              <label className="block min-w-0 text-[11px] text-text-muted">
                <MetadataFieldLabel
                  label="STT Provider"
                  help="Speech-to-text provider selection is driven by tenant provider access so only tenant-ready providers appear here."
                />
                <select
                  data-testid="builder-stt-provider-select"
                  value={
                    sttAuthoringState.currentProviderUnavailable
                      ? "__unavailable__"
                      : sttAuthoringState.displayProviderId
                  }
                  onChange={(event) => handleSttProviderChange(event.target.value)}
                  onFocus={onFocusField}
                  aria-invalid={unresolvedSttProviderMessage ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    unresolvedSttProviderMessage ? "border-fail-border" : null
                  )}
                >
                  {sttAuthoringState.currentProviderUnavailable ? (
                    <option value="__unavailable__" disabled>
                      Unavailable: {(rawSttProvider ?? "").trim().toLowerCase() || "stored provider"}
                    </option>
                  ) : null}
                  {sttAuthoringState.availableProviders.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.label}
                    </option>
                  ))}
                </select>
                <SchemaHintText hint={getScenarioSchemaHint(["config", "stt_provider"])} />
              </label>

              <label className="block min-w-0 text-[11px] text-text-muted">
                <MetadataFieldLabel
                  label="STT Model"
                  help="Speech-to-text model used for bot listening. Phone-call tuned models usually work best for telephony."
                />
                <input
                  {...sttModelField}
                  data-testid="builder-stt-model-input"
                  value={rawSttModel ?? ""}
                  onChange={(event) => handleSttModelChange(event.target.value)}
                  onFocus={onFocusField}
                  placeholder={
                    getDefaultModelForSttProvider(
                      sttAuthoringState.displayProviderId || "deepgram"
                    ) || "nova-2-general"
                  }
                  aria-invalid={errors.stt_model ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.stt_model ? "border-fail-border" : null
                  )}
                />
                <SchemaHintText hint={getScenarioSchemaHint(["config", "stt_model"])} />
              </label>
            </div>

            {activeSttProvider ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-text-muted">
                Current STT runtime uses {activeSttProvider.label}; provider-defined model IDs are stored exactly as entered.
              </p>
            ) : null}
            {unresolvedSttProviderMessage ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-fail">
                {unresolvedSttProviderMessage}
              </p>
            ) : null}
            {errors.stt_model?.message ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-fail">
                {errors.stt_model.message}
              </p>
            ) : null}
          </div>

          <div className="rounded-md border border-border bg-bg-surface/60 p-2.5">
            <div className="flex flex-col gap-1">
              <p className="text-[11px] uppercase tracking-wide text-text-muted">
                Text-to-Speech
              </p>
              <p className="text-[10px] normal-case tracking-normal text-text-muted">
                Harness speech stays canonical in YAML as `provider:voice`, but the Builder now lets you edit provider and voice separately.
              </p>
            </div>

            <input {...ttsVoiceField} type="hidden" />
            <div className="mt-2 grid gap-2">
              <label className="block min-w-0 text-[11px] text-text-muted">
                <MetadataFieldLabel
                  label="TTS Provider"
                  help="Provider-aware harness speech selection. BotCheck still saves the canonical value as provider:voice in YAML."
                />
                <select
                  value={
                    ttsAuthoringState.currentProviderUnavailable
                      ? "__unavailable__"
                      : ttsAuthoringState.displayProviderId
                  }
                  onChange={(event) => handleTtsProviderChange(event.target.value)}
                  onFocus={onFocusField}
                  aria-invalid={
                    errors.tts_voice || unresolvedTtsVoiceMessage ? "true" : "false"
                  }
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.tts_voice || unresolvedTtsVoiceMessage ? "border-fail-border" : null
                  )}
                >
                  {ttsAuthoringState.currentProviderUnavailable ? (
                    <option value="__unavailable__" disabled>
                      Unavailable in this deployment
                    </option>
                  ) : null}
                  {ttsAuthoringState.availableProviders.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.label}
                    </option>
                  ))}
                </select>
              </label>

              {activeTtsProvider ? (
                activeTtsProvider.voice_mode === "static_select" ? (
                  <label className="block min-w-0 text-[11px] text-text-muted">
                    <MetadataFieldLabel
                      label="Voice"
                      help="Named voice selection for providers that expose a fixed catalog."
                    />
                    <select
                      value={
                        ttsAuthoringState.displayVoice ||
                        getDefaultVoiceForTtsProvider(activeTtsProvider.id)
                      }
                      onChange={(event) => handleTtsVoiceChange(event.target.value)}
                      onFocus={onFocusField}
                      className="mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      {OPENAI_TTS_VOICE_OPTIONS.map((voice) => (
                        <option key={voice.id} value={voice.id}>
                          {voice.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label className="block min-w-0 text-[11px] text-text-muted">
                    <MetadataFieldLabel
                      label="Voice ID"
                      help="Freeform provider-specific voice identifier. Use preview to validate custom IDs before dispatch."
                    />
                    <input
                      value={ttsAuthoringState.parsed.voice}
                      onChange={(event) => handleTtsVoiceChange(event.target.value)}
                      onFocus={onFocusField}
                      placeholder="voice_id"
                      aria-invalid={unresolvedTtsVoiceMessage ? "true" : "false"}
                      className={cn(
                        "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 font-mono text-xs text-text-primary focus:border-border-focus focus:outline-none",
                        unresolvedTtsVoiceMessage ? "border-fail-border" : null
                      )}
                    />
                  </label>
                )
              ) : (
                <div className="rounded-md border border-dashed border-border px-2 py-2 text-[10px] normal-case tracking-normal text-text-muted">
                  Choose an available provider to replace the current unavailable value.
                </div>
              )}
            </div>

            {activeTtsProvider ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-text-muted">
                Available for{" "}
                {[
                  activeTtsProvider.supports_preview ? "preview" : null,
                  activeTtsProvider.supports_cache_warm ? "cache warm" : null,
                  activeTtsProvider.supports_live_synthesis ? "live runs" : null,
                ]
                  .filter(Boolean)
                  .join(", ")}
                .{" "}
                {activeTtsProvider.supports_live_stream
                  ? "Streaming transport is available."
                  : "Live playback is buffered before publish; transport streaming is not available."}
              </p>
            ) : null}

            {activeTtsProvider?.voice_mode === "freeform_id" ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-text-muted">
                Voice IDs are freeform for this provider. Validate them with turn preview before dispatching a run.
              </p>
            ) : null}

            {errors.tts_voice?.message || unresolvedTtsVoiceMessage ? (
              <p className="mt-2 text-[10px] normal-case tracking-normal text-fail">
                {errors.tts_voice?.message ?? unresolvedTtsVoiceMessage}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-border bg-bg-base/60 p-2">
        <p className="text-[11px] uppercase tracking-wide text-text-muted">
          Advanced Reliability Thresholds
        </p>
        <p className="mt-1 text-[10px] normal-case tracking-normal text-text-muted">
          Optional scenario-level overrides for timing score gates and warnings.
        </p>

        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Gate P95 Gap (ms)"
              help="Reliability gate fails when the 95th percentile response gap exceeds this threshold."
            />
            <input
              {...timingGateP95ResponseGapField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="1200"
              aria-invalid={errors.timing_gate_p95_response_gap_ms ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_gate_p95_response_gap_ms ? "border-fail-border" : null
              )}
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Warn P95 Gap (ms)"
              help="Reliability emits a warning when the 95th percentile response gap exceeds this threshold."
            />
            <input
              {...timingWarnP95ResponseGapField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="800"
              aria-invalid={errors.timing_warn_p95_response_gap_ms ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_warn_p95_response_gap_ms ? "border-fail-border" : null
              )}
            />
          </label>

          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Gate Interruptions"
              help="Reliability gate fails when interruption count rises above this threshold."
            />
            <input
              {...timingGateInterruptionsField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="2"
              aria-invalid={errors.timing_gate_interruptions_count ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_gate_interruptions_count ? "border-fail-border" : null
              )}
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Warn Interruptions"
              help="Reliability emits a warning when interruption count rises above this threshold."
            />
            <input
              {...timingWarnInterruptionsField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="0"
              aria-invalid={errors.timing_warn_interruptions_count ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_warn_interruptions_count ? "border-fail-border" : null
              )}
            />
          </label>

          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Gate Long Pauses"
              help="Reliability gate fails when long-pause count rises above this threshold."
            />
            <input
              {...timingGateLongPauseField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="3"
              aria-invalid={errors.timing_gate_long_pause_count ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_gate_long_pause_count ? "border-fail-border" : null
              )}
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Warn Long Pauses"
              help="Reliability emits a warning when long-pause count rises above this threshold."
            />
            <input
              {...timingWarnLongPauseField}
              type="number"
              min={0}
              step={1}
              onFocus={onFocusField}
              placeholder="1"
              aria-invalid={errors.timing_warn_long_pause_count ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_warn_long_pause_count ? "border-fail-border" : null
              )}
            />
          </label>

          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Gate Recovery (%)"
              help="Reliability gate fails when interruption recovery percentage drops below this threshold."
            />
            <input
              {...timingGateRecoveryField}
              type="number"
              min={0}
              step={0.1}
              onFocus={onFocusField}
              placeholder="90"
              aria-invalid={errors.timing_gate_interruption_recovery_pct ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_gate_interruption_recovery_pct ? "border-fail-border" : null
              )}
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Warn Recovery (%)"
              help="Reliability emits a warning when interruption recovery percentage drops below this threshold."
            />
            <input
              {...timingWarnRecoveryField}
              type="number"
              min={0}
              step={0.1}
              onFocus={onFocusField}
              placeholder="85"
              aria-invalid={errors.timing_warn_interruption_recovery_pct ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_warn_interruption_recovery_pct ? "border-fail-border" : null
              )}
            />
          </label>

          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Gate Efficiency (%)"
              help="Reliability gate fails when turn-taking efficiency drops below this threshold."
            />
            <input
              {...timingGateEfficiencyField}
              type="number"
              min={0}
              step={0.1}
              onFocus={onFocusField}
              placeholder="95"
              aria-invalid={errors.timing_gate_turn_taking_efficiency_pct ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_gate_turn_taking_efficiency_pct ? "border-fail-border" : null
              )}
            />
          </label>
          <label className="block text-[11px] uppercase tracking-wide text-text-muted">
            <MetadataFieldLabel
              label="Warn Efficiency (%)"
              help="Reliability emits a warning when turn-taking efficiency drops below this threshold."
            />
            <input
              {...timingWarnEfficiencyField}
              type="number"
              min={0}
              step={0.1}
              onFocus={onFocusField}
              placeholder="90"
              aria-invalid={errors.timing_warn_turn_taking_efficiency_pct ? "true" : "false"}
              className={cn(
                "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                errors.timing_warn_turn_taking_efficiency_pct ? "border-fail-border" : null
              )}
            />
          </label>
        </div>
      </div>
    </div>
  );
}
