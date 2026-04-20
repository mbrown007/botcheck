"use client";

import { useEffect, useRef, useState } from "react";
import type { SpeechCapabilities } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getScenarioSchemaHint } from "@/lib/scenario-schema-hints";
import { cn } from "@/lib/utils";
import {
  BOT_PROTOCOL_OPTIONS,
  PERSONA_MOOD_OPTIONS,
  RESPONSE_STYLE_OPTIONS,
  SCENARIO_TYPE_OPTIONS,
} from "@/lib/schemas/scenario-meta";
import { useMetadataForm } from "../hooks/useMetadataForm";
import { RuntimeConfigEditor } from "./RuntimeConfigEditor";
import { ScoringRubricEditor } from "./ScoringRubricEditor";
import { MetadataFieldLabel } from "./MetadataFieldLabel";
import { SchemaHintText } from "./SchemaHintText";

interface MetadataPanelProps {
  open: boolean;
  onToggle: () => void;
  focusField: "metadata-id" | null;
  onFocusConsumed: () => void;
  speechCapabilities?: SpeechCapabilities;
}

type MetadataSectionKey =
  | "botConnection"
  | "callerPersona"
  | "scoring"
  | "runtimeConfig"
  | "description";

interface MetadataSubsectionProps {
  title: string;
  description: string;
  open: boolean;
  onToggle: () => void;
  testId: string;
}

function MetadataSubsectionHeader({
  title,
  description,
  open,
  onToggle,
  testId,
}: MetadataSubsectionProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      data-testid={testId}
      aria-expanded={open}
      className="flex w-full items-start justify-between gap-3 rounded-md border border-border bg-bg-surface/20 px-2.5 py-2 text-left transition-colors duration-200 hover:bg-bg-surface/35"
    >
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-text-muted">{title}</p>
        <p className="mt-1 text-[10px] normal-case tracking-normal text-text-muted">
          {description}
        </p>
      </div>
      <span className="pt-0.5 text-xs text-text-muted">{open ? "▾" : "▸"}</span>
    </button>
  );
}

export function MetadataPanel({
  open,
  onToggle,
  focusField,
  onFocusConsumed,
  speechCapabilities,
}: MetadataPanelProps) {
  const {
    form: {
      control,
      register,
      setValue,
      formState: { errors },
      watch,
    },
    onMetadataFieldFocus,
  } = useMetadataForm();

  const metadataIdInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (focusField !== "metadata-id" || !open) {
      return;
    }
    const timer = window.setTimeout(() => {
      metadataIdInputRef.current?.focus();
      metadataIdInputRef.current?.select();
      onFocusConsumed();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [focusField, onFocusConsumed, open]);

  const nameField = register("name");
  const idField = register("id");
  const namespaceField = register("namespace");
  const typeField = register("type");
  const versionField = register("version");
  const tagsField = register("tags_csv");
  const botEndpointField = register("bot_endpoint");
  const botProtocolField = register("bot_protocol");
  const botTrunkIdField = register("bot_trunk_id");
  const botCallerIdField = register("bot_caller_id");
  const botHeadersTextField = register("bot_headers_text");
  const personaMoodField = register("persona_mood");
  const personaResponseStyleField = register("persona_response_style");
  const scoringOverallGateField = register("scoring_overall_gate");
  const descriptionField = register("description");
  const [openSections, setOpenSections] = useState<Record<MetadataSectionKey, boolean>>({
    botConnection: false,
    callerPersona: false,
    scoring: false,
    runtimeConfig: false,
    description: false,
  });

  function toggleSection(section: MetadataSectionKey) {
    setOpenSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  }

  return (
    <div className="rounded-md border border-border bg-bg-elevated">
      <button
        type="button"
        onClick={onToggle}
        data-testid="metadata-toggle-btn"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <h2 className="text-sm font-semibold text-text-primary">Scenario Metadata</h2>
        <span className="text-xs text-text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <TooltipProvider delayDuration={150}>
        <div className="border-t border-border px-3 pb-3 pt-2">
          <div className="space-y-2">
            <label className="block text-[11px] uppercase tracking-wide text-text-muted">
              <MetadataFieldLabel
                label="Name"
                help="Human-readable scenario title shown in the dashboard and builder."
              />
              <input
                {...nameField}
                onFocus={onMetadataFieldFocus}
                data-testid="metadata-name-input"
                placeholder="Scenario name"
                aria-invalid={errors.name ? "true" : "false"}
                className={cn(
                  "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                  errors.name ? "border-fail-border" : null
                )}
              />
              {errors.name?.message ? (
                <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                  {errors.name.message}
                </p>
              ) : null}
              <SchemaHintText hint={getScenarioSchemaHint(["name"])} />
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="ID"
                  help="Stable scenario identifier used in YAML, scheduling, and run history. Keep it slug-like."
                />
                <input
                  {...idField}
                  ref={(element) => {
                    idField.ref(element);
                    metadataIdInputRef.current = element;
                  }}
                  onFocus={onMetadataFieldFocus}
                  data-testid="metadata-id-input"
                  placeholder="scenario-id"
                  aria-invalid={errors.id ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 font-mono text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.id ? "border-fail-border" : null
                  )}
                />
                {errors.id?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                    {errors.id.message}
                  </p>
                ) : null}
                <SchemaHintText hint={getScenarioSchemaHint(["id"])} />
              </label>
              <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="Type"
                  help="High-level scenario category. This influences default scoring expectations and how the run is interpreted."
                />
                <select
                  {...typeField}
                  onFocus={onMetadataFieldFocus}
                  data-testid="metadata-type-select"
                  aria-invalid={errors.type ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.type ? "border-fail-border" : null
                  )}
                >
                  {SCENARIO_TYPE_OPTIONS.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
                {errors.type?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                    {errors.type.message}
                  </p>
                ) : null}
                <SchemaHintText hint={getScenarioSchemaHint(["type"])} />
              </label>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="Namespace"
                  help="Catalog path used to group scenarios in the UI, for example billing or support/refunds."
                />
                <input
                  {...namespaceField}
                  onFocus={onMetadataFieldFocus}
                  data-testid="metadata-namespace-input"
                  placeholder="support/refunds"
                  aria-invalid={errors.namespace ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.namespace ? "border-fail-border" : null
                  )}
                />
                {errors.namespace?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                    {errors.namespace.message}
                  </p>
                ) : null}
                <SchemaHintText hint={getScenarioSchemaHint(["namespace"])} />
              </label>
              <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="Version"
                  help="Scenario content version. Update this when the intent or flow meaningfully changes."
                />
                <input
                  {...versionField}
                  onFocus={onMetadataFieldFocus}
                  data-testid="metadata-version-input"
                  placeholder="1.0"
                  aria-invalid={errors.version ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.version ? "border-fail-border" : null
                  )}
                />
                {errors.version?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                    {errors.version.message}
                  </p>
                ) : null}
                <SchemaHintText hint={getScenarioSchemaHint(["version"])} />
              </label>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="Tags (comma-separated)"
                  help="Free-form labels used for filtering, grouping, and smoke/regression organization."
                />
                <input
                  {...tagsField}
                  onFocus={onMetadataFieldFocus}
                  placeholder="smoke, sip, regression"
                  aria-invalid={errors.tags_csv ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.tags_csv ? "border-fail-border" : null
                  )}
                />
                {errors.tags_csv?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                    {errors.tags_csv.message}
                  </p>
                ) : null}
              </label>
            </div>
            <MetadataSubsectionHeader
              title="Description"
              description="Operator-facing summary of what this scenario is intended to test."
              open={openSections.description}
              onToggle={() => toggleSection("description")}
              testId="metadata-description-toggle"
            />
            {openSections.description ? (
            <label className="block text-[11px] uppercase tracking-wide text-text-muted">
              <MetadataFieldLabel
                label="Description"
                help="Short operator-facing summary of the scenario's intent and what it is testing."
              />
              <textarea
                {...descriptionField}
                onFocus={onMetadataFieldFocus}
                data-testid="metadata-description-input"
                rows={3}
                placeholder="Describe the scenario intent"
                aria-invalid={errors.description ? "true" : "false"}
                className={cn(
                  "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                  errors.description ? "border-fail-border" : null
                )}
              />
              {errors.description?.message ? (
                <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                  {errors.description.message}
                </p>
              ) : null}
              <SchemaHintText hint={getScenarioSchemaHint(["description"])} />
            </label>
            ) : null}
            <MetadataSubsectionHeader
              title="Bot Connection"
              description="Inline bot fields are scenario defaults. Destination is selected at dispatch time."
              open={openSections.botConnection}
              onToggle={() => toggleSection("botConnection")}
              testId="metadata-bot-connection-toggle"
            />
            {openSections.botConnection ? (
            <div className="rounded-md border border-border bg-bg-surface/40 p-2">
              <fieldset className="grid gap-2 sm:grid-cols-2">
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Endpoint"
                    help="Scenario-level default SIP URI or WebRTC URL for the bot under test. Dispatch-time transport settings can override this."
                  />
                  <input
                    {...botEndpointField}
                    onFocus={onMetadataFieldFocus}
                    placeholder="sip:bot@example.com"
                    aria-invalid={errors.bot_endpoint ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.bot_endpoint ? "border-fail-border" : null
                    )}
                  />
                  {errors.bot_endpoint?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.bot_endpoint.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["bot", "endpoint"])} />
                </label>
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Protocol"
                    help="How the harness reaches the bot: SIP, WebRTC, or mock. SIP is the normal production path."
                  />
                  <select
                    {...botProtocolField}
                    onFocus={onMetadataFieldFocus}
                    data-testid="metadata-bot-protocol-select"
                    aria-invalid={errors.bot_protocol ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.bot_protocol ? "border-fail-border" : null
                    )}
                  >
                    {BOT_PROTOCOL_OPTIONS.map((protocol) => (
                      <option key={protocol} value={protocol}>
                        {protocol}
                      </option>
                    ))}
                  </select>
                  {errors.bot_protocol?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.bot_protocol.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["bot", "protocol"])} />
                </label>
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Trunk ID"
                    help="Scenario-level LiveKit SIP trunk override. Usually leave blank and choose the transport profile at dispatch time."
                  />
                  <input
                    {...botTrunkIdField}
                    onFocus={onMetadataFieldFocus}
                    placeholder="LK SIP trunk id"
                    aria-invalid={errors.bot_trunk_id ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.bot_trunk_id ? "border-fail-border" : null
                    )}
                  />
                  {errors.bot_trunk_id?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.bot_trunk_id.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["bot", "trunk_id"])} />
                </label>
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Caller ID"
                    help="Default outbound caller ID presented on the call when the selected trunk allows it."
                  />
                  <input
                    {...botCallerIdField}
                    onFocus={onMetadataFieldFocus}
                    placeholder="+15551234567"
                    aria-invalid={errors.bot_caller_id ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.bot_caller_id ? "border-fail-border" : null
                    )}
                  />
                  {errors.bot_caller_id?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.bot_caller_id.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["bot", "caller_id"])} />
                </label>
              </fieldset>
              <label className="mt-2 block text-[11px] uppercase tracking-wide text-text-muted">
                <MetadataFieldLabel
                  label="SIP Headers"
                  help="Optional custom SIP INVITE headers. Use one 'Header: value' pair per line for carrier or routing integrations."
                />
                <textarea
                  {...botHeadersTextField}
                  onFocus={onMetadataFieldFocus}
                  rows={3}
                  placeholder={"X-Tenant-ID: acme\nX-Campaign: smoke"}
                  aria-invalid={errors.bot_headers_text ? "true" : "false"}
                  className={cn(
                    "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 font-mono text-xs text-text-primary focus:border-border-focus focus:outline-none",
                    errors.bot_headers_text ? "border-fail-border" : null
                  )}
                />
                <p className="mt-1 text-[10px] normal-case tracking-normal text-text-muted">
                  One <code className="font-mono">Header: value</code> per line.
                </p>
                {errors.bot_headers_text?.message ? (
                  <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                  {errors.bot_headers_text.message}
                </p>
              ) : null}
              <SchemaHintText hint={getScenarioSchemaHint(["bot", "headers"])} />
            </label>
            </div>
            ) : null}
            <MetadataSubsectionHeader
              title="Caller Persona"
              description="Caller mood and response style used to shape harness tone."
              open={openSections.callerPersona}
              onToggle={() => toggleSection("callerPersona")}
              testId="metadata-caller-persona-toggle"
            />
            {openSections.callerPersona ? (
            <div className="rounded-md border border-border bg-bg-surface/40 p-2">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Persona Mood"
                    help="Overall caller mood used to shape harness wording and tone."
                  />
                  <select
                    {...personaMoodField}
                    onFocus={onMetadataFieldFocus}
                    aria-invalid={errors.persona_mood ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.persona_mood ? "border-fail-border" : null
                    )}
                  >
                    {PERSONA_MOOD_OPTIONS.map((mood) => (
                      <option key={mood} value={mood}>
                        {mood}
                      </option>
                    ))}
                  </select>
                  {errors.persona_mood?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.persona_mood.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["persona", "mood"])} />
                </label>
                <label className="block text-[11px] uppercase tracking-wide text-text-muted">
                  <MetadataFieldLabel
                    label="Persona Style"
                    help="How verbose or direct the harness should sound when speaking."
                  />
                  <select
                    {...personaResponseStyleField}
                    onFocus={onMetadataFieldFocus}
                    aria-invalid={errors.persona_response_style ? "true" : "false"}
                    className={cn(
                      "mt-1 w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-xs text-text-primary focus:border-border-focus focus:outline-none",
                      errors.persona_response_style ? "border-fail-border" : null
                    )}
                  >
                    {RESPONSE_STYLE_OPTIONS.map((style) => (
                      <option key={style} value={style}>
                        {style}
                      </option>
                    ))}
                  </select>
                  {errors.persona_response_style?.message ? (
                    <p className="mt-1 text-[10px] normal-case tracking-normal text-fail">
                      {errors.persona_response_style.message}
                    </p>
                  ) : null}
                  <SchemaHintText hint={getScenarioSchemaHint(["persona", "response_style"])} />
                </label>
              </div>
            </div>
            ) : null}
            <MetadataSubsectionHeader
              title="Scoring"
              description="Pass/fail gate and per-dimension score thresholds for this scenario."
              open={openSections.scoring}
              onToggle={() => toggleSection("scoring")}
              testId="metadata-scoring-toggle"
            />
            {openSections.scoring ? (
            <div className="space-y-2">
              <label className="flex items-center gap-2 rounded-md border border-border bg-bg-surface/40 px-3 py-2 text-[11px] uppercase tracking-wide text-text-muted">
                <input
                  {...scoringOverallGateField}
                  type="checkbox"
                  onFocus={onMetadataFieldFocus}
                  className="h-3.5 w-3.5 rounded border border-border bg-bg-base accent-brand"
                />
                <MetadataFieldLabel
                  label="Overall Gate Enabled"
                  help="If enabled, this scenario participates in the overall pass/fail gate rather than acting as informational only."
                />
              </label>
              <ScoringRubricEditor
                control={control}
                register={register}
                errors={errors}
                onFocusField={onMetadataFieldFocus}
                showTitle={false}
              />
            </div>
            ) : null}
            <MetadataSubsectionHeader
              title="Runtime Config"
              description="Turn limits, timing controls, and speech runtime defaults for this scenario."
              open={openSections.runtimeConfig}
              onToggle={() => toggleSection("runtimeConfig")}
              testId="metadata-runtime-config-toggle"
            />
            {openSections.runtimeConfig ? (
            <RuntimeConfigEditor
              register={register}
              setValue={setValue}
              watch={watch}
              errors={errors}
              onFocusField={onMetadataFieldFocus}
              speechCapabilities={speechCapabilities}
              showTitle={false}
            />
            ) : null}
          </div>
        </div>
        </TooltipProvider>
      )}
    </div>
  );
}
