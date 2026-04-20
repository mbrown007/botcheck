import { Bot, Globe, Wand2, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import {
  buildHttpTransportOptionLabel,
  buildPlaygroundAIScenarioOptionLabel,
  buildPlaygroundGraphOptionLabel,
  playgroundPromptSoftLimitWarning,
  type PlaygroundMode,
} from "@/lib/playground";
import {
  summarizePlaygroundPresetTarget,
} from "@/lib/playground-presets";
import type {
  AIScenarioSummary,
  AIPersonaSummary,
  BotDestinationSummary,
  PlaygroundPresetSummary,
  ScenarioDefinition,
} from "@/lib/api/types";
import type { PlaygroundExtractedTool } from "@/lib/api";
import {
  parseTargetValue,
  targetValueFromChoice,
  type TargetChoice,
} from "./playground-types";

export function PlaygroundLaunchControlsCard({
  noTargets,
  presets,
  selectedPresetId,
  selectedPresetSummary,
  loadingPreset,
  presetName,
  presetDescription,
  onSelectPreset,
  onChangePresetName,
  onChangePresetDescription,
  onLoadPreset,
  canPersistPreset,
  savingPreset,
  deletingPreset,
  savingPresetAction,
  onCreatePreset,
  onUpdatePreset,
  onDuplicatePreset,
  onDeletePreset,
  targetChoice,
  graphScenarios,
  aiEnabled,
  aiScenarios,
  onChangeTargetChoice,
  mode,
  onChangeMode,
  systemPrompt,
  onChangeSystemPrompt,
  personas,
  personaId,
  onChangePersonaId,
  loadingPersonaPrompt,
  onLoadPersonaPrompt,
  extractedTools,
  stubEditorJson,
  invalidStubNames,
  hasInvalidStubs,
  extractingTools,
  generatingStubs,
  stubError,
  onExtractTools,
  onGenerateStubs,
  onChangeStubEditorJson,
  selectedTransport,
  transportProfileId,
  httpTransportProfiles,
  onChangeTransportProfileId,
  runId,
  runActive,
  presetLoaded,
}: {
  noTargets: boolean;
  presets: PlaygroundPresetSummary[];
  selectedPresetId: string;
  selectedPresetSummary: PlaygroundPresetSummary | null;
  loadingPreset: boolean;
  presetName: string;
  presetDescription: string;
  onSelectPreset: (presetId: string) => void;
  onChangePresetName: (value: string) => void;
  onChangePresetDescription: (value: string) => void;
  onLoadPreset: () => void;
  canPersistPreset: boolean;
  savingPreset: boolean;
  deletingPreset: boolean;
  savingPresetAction: "create" | "update" | "duplicate" | null;
  onCreatePreset: () => void;
  onUpdatePreset: () => void;
  onDuplicatePreset: () => void;
  onDeletePreset: () => void;
  targetChoice: TargetChoice;
  graphScenarios: ScenarioDefinition[];
  aiEnabled: boolean;
  aiScenarios: AIScenarioSummary[];
  onChangeTargetChoice: (choice: TargetChoice) => void;
  mode: PlaygroundMode;
  onChangeMode: (mode: PlaygroundMode) => void;
  systemPrompt: string;
  onChangeSystemPrompt: (value: string) => void;
  personas: AIPersonaSummary[];
  personaId: string;
  onChangePersonaId: (value: string) => void;
  loadingPersonaPrompt: boolean;
  onLoadPersonaPrompt: () => void;
  extractedTools: PlaygroundExtractedTool[];
  stubEditorJson: Record<string, string>;
  invalidStubNames: string[];
  hasInvalidStubs: boolean;
  extractingTools: boolean;
  generatingStubs: boolean;
  stubError: string;
  onExtractTools: () => void;
  onGenerateStubs: () => void;
  onChangeStubEditorJson: (name: string, value: string) => void;
  selectedTransport: BotDestinationSummary | null;
  transportProfileId: string;
  httpTransportProfiles: BotDestinationSummary[];
  onChangeTransportProfileId: (value: string) => void;
  runId: string | null;
  runActive: boolean;
  presetLoaded: boolean;
}) {
  const promptWarning = playgroundPromptSoftLimitWarning(systemPrompt);

  return (
    <Card className="min-h-[640px]" data-testid="playground-launch-controls-card">
      <CardHeader>
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
            Launch Controls
          </p>
          <h2 className="mt-1 text-base font-semibold text-text-primary">
            Configure Playground Run
          </h2>
        </div>
      </CardHeader>
      <CardBody className="space-y-5">
        {noTargets ? (
          <TableState
            kind="empty"
            title="No playground-compatible scenarios"
            message="Create a mock or direct HTTP scenario first, or add an AI scenario to launch from the playground."
            columns={1}
          />
        ) : (
          <>
            <div className="space-y-4 rounded-xl border border-border bg-bg-base/40 px-4 py-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                  Saved Setups
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  Save this playground configuration and reload it later instead of recreating the same test setup.
                </p>
              </div>

              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
                <select
                  data-testid="playground-preset-select"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  value={selectedPresetId}
                  onChange={(event) => onSelectPreset(event.target.value)}
                >
                  <option value="">Select a saved setup</option>
                  {presets.map((preset) => (
                    <option key={preset.preset_id} value={preset.preset_id}>
                      {preset.name} · {preset.playground_mode === "mock" ? "Mock" : "HTTP"} ·{" "}
                      {summarizePlaygroundPresetTarget(preset)}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onLoadPreset}
                  disabled={!selectedPresetId || loadingPreset}
                >
                  {loadingPreset ? "Loading…" : "Load Setup"}
                </Button>
              </div>

              {selectedPresetSummary ? (
                <div className="rounded-lg border border-border bg-bg-surface px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                    Selected Preset
                  </p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {selectedPresetSummary.name}
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    {selectedPresetSummary.description?.trim()
                      ? selectedPresetSummary.description
                      : `${selectedPresetSummary.playground_mode === "mock" ? "Mock" : "HTTP"} mode · ${summarizePlaygroundPresetTarget(
                          selectedPresetSummary
                        )}`}
                  </p>
                </div>
              ) : null}

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                    Preset Name
                  </label>
                  <input
                    data-testid="playground-preset-name"
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    value={presetName}
                    onChange={(event) => onChangePresetName(event.target.value)}
                    placeholder="Billing mock smoke"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                    Description
                  </label>
                  <input
                    data-testid="playground-preset-description"
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    value={presetDescription}
                    onChange={(event) => onChangePresetDescription(event.target.value)}
                    placeholder="Optional notes for the rest of the team"
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onCreatePreset}
                  disabled={!canPersistPreset || savingPreset || deletingPreset}
                >
                  {savingPresetAction === "create" ? "Saving…" : "Save as New"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onUpdatePreset}
                  disabled={!selectedPresetId || !canPersistPreset || savingPreset || deletingPreset}
                >
                  {savingPresetAction === "update" ? "Updating…" : "Update Selected"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onDuplicatePreset}
                  disabled={!canPersistPreset || savingPreset || deletingPreset}
                >
                  {savingPresetAction === "duplicate" ? "Saving…" : "Duplicate as New"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={onDeletePreset}
                  disabled={!selectedPresetId || deletingPreset}
                  className="text-fail hover:text-fail"
                >
                  {deletingPreset ? "Deleting…" : "Delete Selected"}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                Scenario
              </label>
              <select
                data-testid="playground-scenario-select"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                value={targetValueFromChoice(targetChoice)}
                onChange={(event) => onChangeTargetChoice(parseTargetValue(event.target.value))}
              >
                {graphScenarios.length > 0 ? (
                  <optgroup label="Graph Scenarios">
                    {graphScenarios.map((scenario) => (
                      <option key={scenario.id} value={`graph:${scenario.id}`}>
                        {buildPlaygroundGraphOptionLabel(scenario)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {aiEnabled && aiScenarios.length > 0 ? (
                  <optgroup label="AI Scenarios">
                    {aiScenarios.map((scenario) => (
                      <option key={scenario.ai_scenario_id} value={`ai:${scenario.ai_scenario_id}`}>
                        {buildPlaygroundAIScenarioOptionLabel(scenario)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
              <p className="text-xs text-text-muted">
                Graph scenarios are filtered to mock and direct HTTP profiles only. AI scenarios use their bound runtime scenario.
              </p>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                Mode
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <button
                  type="button"
                  className={`rounded-xl border px-4 py-4 text-left transition-colors ${
                    mode === "mock"
                      ? "border-brand bg-brand/5"
                      : "border-border bg-bg-elevated hover:bg-bg-base"
                  }`}
                  onClick={() => onChangeMode("mock")}
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                    <Bot className="h-4 w-4" />
                    Mock Agent
                  </div>
                  <p className="mt-2 text-xs text-text-muted">
                    Use the tenant default LLM with your supplied system prompt and optional persona prompt bootstrapping.
                  </p>
                </button>
                <button
                  type="button"
                  className={`rounded-xl border px-4 py-4 text-left transition-colors ${
                    mode === "direct_http"
                      ? "border-brand bg-brand/5"
                      : "border-border bg-bg-elevated hover:bg-bg-base"
                  }`}
                  onClick={() => onChangeMode("direct_http")}
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                    <Globe className="h-4 w-4" />
                    Direct HTTP
                  </div>
                  <p className="mt-2 text-xs text-text-muted">
                    Send turns to a real HTTP transport profile with the same request mapping you configured in Settings.
                  </p>
                </button>
              </div>
            </div>

            {mode === "mock" ? (
              <div className="space-y-4 rounded-xl border border-border bg-bg-base/40 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                      System Prompt
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      Define the mock bot behavior for this one playground run.
                    </p>
                  </div>
                  <p className="text-xs text-text-muted">
                    {systemPrompt.length.toLocaleString()} chars
                  </p>
                </div>

                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
                  <select
                    data-testid="playground-persona-select"
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    value={personaId}
                    onChange={(event) => onChangePersonaId(event.target.value)}
                  >
                    <option value="">No persona prompt</option>
                    {personas.map((persona) => (
                      <option key={persona.persona_id} value={persona.persona_id}>
                        {persona.display_name}
                      </option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={onLoadPersonaPrompt}
                    disabled={!personaId || loadingPersonaPrompt}
                  >
                    {loadingPersonaPrompt ? "Loading…" : "Load Persona Prompt"}
                  </Button>
                </div>

                <textarea
                  data-testid="playground-system-prompt"
                  className="min-h-[240px] w-full rounded-md border border-border bg-bg-elevated px-3 py-3 text-sm text-text-primary"
                  value={systemPrompt}
                  onChange={(event) => onChangeSystemPrompt(event.target.value)}
                  placeholder="Describe the behavior of the mock bot you want to exercise."
                />
                {promptWarning ? (
                  <p className="text-xs text-warn">{promptWarning}</p>
                ) : (
                  <p className="text-xs text-text-muted">
                    Soft guidance only. The prompt is not truncated.
                  </p>
                )}

                <div className="space-y-3 border-t border-border pt-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Wrench className="h-3.5 w-3.5 text-text-muted" />
                        <p className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                          Tool Stubs
                        </p>
                      </div>
                      <p className="mt-1 text-xs text-text-muted">
                        Optionally configure stub return values for tools defined in the system prompt.
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {extractedTools.length > 0 ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-2.5 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-base disabled:opacity-50"
                          onClick={onGenerateStubs}
                          disabled={generatingStubs || extractingTools}
                        >
                          <Wand2 className="h-3.5 w-3.5" />
                          {generatingStubs ? "Generating…" : "Generate Values"}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-2.5 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-base disabled:opacity-50"
                        onClick={onExtractTools}
                        disabled={extractingTools || generatingStubs || !systemPrompt.trim()}
                      >
                        {extractingTools ? "Extracting…" : "Extract Tools"}
                      </button>
                    </div>
                  </div>

                  {stubError ? <p className="text-xs text-fail">{stubError}</p> : null}
                  {hasInvalidStubs ? (
                    <p className="text-xs text-fail">
                      Tool stub must be a JSON object &#123;…&#125; in: {invalidStubNames.join(", ")}. Fix before running.
                    </p>
                  ) : null}

                  {extractedTools.length === 0 ? (
                    <p className="text-xs text-text-muted">
                      Click "Extract Tools" to scan the system prompt for callable tools.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {extractedTools.map((tool) => {
                        const raw = stubEditorJson[tool.name] ?? "{}";
                        let parseError = false;
                        try {
                          JSON.parse(raw);
                        } catch {
                          parseError = true;
                        }
                        return (
                          <div
                            key={tool.name}
                            data-testid={`playground-stub-card-${tool.name}`}
                            className={`rounded-xl border px-3 py-3 ${parseError ? "border-fail-border bg-fail/5" : "border-border bg-bg-elevated"}`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="font-mono text-xs font-semibold text-text-primary">{tool.name}</p>
                                {tool.description ? (
                                  <p className="mt-0.5 text-xs text-text-muted">{tool.description}</p>
                                ) : null}
                              </div>
                              {parseError ? (
                                <span className="shrink-0 rounded-full bg-fail/10 px-2 py-0.5 text-[11px] font-medium text-fail">
                                  Must be JSON object
                                </span>
                              ) : null}
                            </div>
                            <textarea
                              data-testid={`playground-stub-editor-${tool.name}`}
                              className={`mt-2 min-h-[80px] w-full rounded-md border px-2.5 py-2 font-mono text-xs ${
                                parseError
                                  ? "border-fail-border bg-fail/5 text-fail"
                                  : "border-border bg-bg-base text-text-primary"
                              }`}
                              value={raw}
                              onChange={(event) => onChangeStubEditorJson(tool.name, event.target.value)}
                              spellCheck={false}
                            />
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-4 rounded-xl border border-border bg-bg-base/40 px-4 py-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">
                    HTTP Transport Profile
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    Direct HTTP mode requires an explicit transport profile.
                  </p>
                </div>

                <select
                  data-testid="playground-http-profile-select"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                  value={transportProfileId}
                  onChange={(event) => onChangeTransportProfileId(event.target.value)}
                >
                  <option value="">Select an HTTP transport profile</option>
                  {httpTransportProfiles.map((profile) => (
                    <option key={profile.destination_id} value={profile.destination_id}>
                      {buildHttpTransportOptionLabel(profile)}
                    </option>
                  ))}
                </select>

                {selectedTransport ? (
                  <div className="rounded-lg border border-border bg-bg-surface px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                      Selected Endpoint
                    </p>
                    <p className="mt-1 text-sm text-text-primary">
                      {selectedTransport.default_dial_target ??
                        selectedTransport.endpoint ??
                        "Endpoint unavailable"}
                    </p>
                    <p className="mt-2 text-xs text-text-muted">
                      Auth headers and request mapping are inherited from the transport profile.
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-text-muted">
                    Choose a profile from Settings → Transport Profiles. Only active HTTP profiles are shown here.
                  </p>
                )}
              </div>
            )}

            <div className="rounded-xl border border-border bg-bg-elevated px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                Launch State
              </p>
              {runId ? (
                <>
                  <p className="mt-1 font-mono text-xs text-text-primary">{runId}</p>
                  <p className="mt-2 text-xs text-text-muted">
                    {runActive
                      ? "Run is active. Live event panes connect in the next playground slice."
                      : "Last playground run is complete. You can launch another run now."}
                  </p>
                </>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  No playground run launched yet.
                </p>
              )}
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
              <div className="space-y-1 text-xs text-text-muted">
                <p>
                  Playground runs reuse the normal run pipeline and count toward the standard run quota.
                </p>
                {(runId || presetLoaded) ? (
                  <p data-testid="playground-relaunch-note">
                    Relaunch always uses the current visible setup, including any unsaved preset edits.
                  </p>
                ) : null}
              </div>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
