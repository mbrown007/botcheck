"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ExternalLink,
  ChevronDown,
  ChevronRight,
  PencilLine,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";

import {
  availableProviderItems,
  useAIPersonas,
  useAvailableProviders,
  useFeatures,
  usePlaygroundAIScenarios,
  usePlaygroundGraphScenarios,
  usePlaygroundPresets,
  useRun,
  useScenario,
  useTransportProfiles,
} from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";
import {
  describePlaygroundStreamEvent,
  usePlaygroundEventStream,
} from "@/lib/playground-stream";
import { derivePlaygroundDebugEntries } from "@/lib/playground-debug";
import { derivePlaygroundProgressNodes } from "@/lib/playground-progress";
import { AccessPanel } from "@/components/auth/access-panel";
import { ScenarioEditDialog } from "@/components/scenarios/edit-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import { isPlaygroundRunActive } from "@/lib/playground";
import { TenantProviderAccessCard } from "@/components/providers/tenant-provider-access-card";
import { PlaygroundDebugCard } from "./_components/PlaygroundDebugCard";
import { PlaygroundLaunchControlsCard } from "./_components/PlaygroundLaunchControlsCard";
import { PlaygroundLiveActivityCard } from "./_components/PlaygroundLiveActivityCard";
import { PlaygroundProgressCard } from "./_components/PlaygroundProgressCard";
import { usePlaygroundLaunchState } from "./_hooks/usePlaygroundLaunchState";

export default function PlaygroundPage() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const {
    roleResolved,
    canUsePlayground,
  } = useDashboardAccess();

  const { data: features } = useFeatures();
  const {
    data: availableProvidersResponse,
    error: availableProvidersError,
  } = useAvailableProviders(canUsePlayground);
  const aiEnabled = features?.ai_scenarios_enabled === true;
  const destinationsEnabled = features?.destinations_enabled === true;
  const availableProviders = availableProviderItems(availableProvidersResponse);
  const { data: graphScenarios, error: graphScenariosError, mutate: mutateGraphScenarios } =
    usePlaygroundGraphScenarios(true);
  const { data: aiScenarios } = usePlaygroundAIScenarios(aiEnabled);
  const { data: personas } = useAIPersonas(aiEnabled);
  const { data: transportProfiles } = useTransportProfiles(destinationsEnabled);
  const { data: presets, mutate: mutatePresets } = usePlaygroundPresets(canUsePlayground);

  const [autoScroll, setAutoScroll] = useState(true);
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [launchControlsOpen, setLaunchControlsOpen] = useState(true);
  const [editingScenarioId, setEditingScenarioId] = useState<string | null>(null);
  const feedViewportRef = useRef<HTMLDivElement | null>(null);

  const {
    canPersistPreset,
    deletingPreset,
    error,
    extractedTools,
    extractingTools,
    generatingStubs,
    handleCreatePreset,
    handleDeletePreset,
    handleDuplicatePreset,
    handleExtractTools,
    handleGenerateStubs,
    handleLoadPersonaPrompt,
    handleLoadPreset,
    handleRunPlayground,
    handleSelectPreset,
    handleUpdatePreset,
    hasInvalidStubs,
    httpTransportProfiles,
    invalidStubNames,
    loadingPersonaPrompt,
    loadingPreset,
    mode,
    personaId,
    presetDescription,
    presetLoaded,
    presetName,
    runId,
    savingPreset,
    savingPresetAction,
    selectedAIScenario,
    selectedGraphScenario,
    selectedPresetId,
    selectedPresetSummary,
    selectedTransport,
    setMode,
    setPersonaId,
    setPresetDescription,
    setPresetName,
    notifySuccess,
    setStubEditorJson,
    setSystemPrompt,
    setTargetChoice,
    setTransportProfileId,
    stubEditorJson,
    stubError,
    submitting,
    success,
    systemPrompt,
    targetChoice,
    transportProfileId,
  } = usePlaygroundLaunchState({
    pathname,
    searchParams,
    graphScenarios,
    aiScenarios,
    transportProfiles,
    presets,
    mutatePresets,
  });

  const { data: activeRun } = useRun(runId);
  const { data: activeScenario } = useScenario(activeRun?.scenario_id ?? null);
  const stream = usePlaygroundEventStream(runId);
  const runActive = isPlaygroundRunActive(activeRun);
  const feedItems = useMemo(
    () =>
      stream.events
        .map((event) => ({
          event,
          descriptor: describePlaygroundStreamEvent(event, selectedGraphScenario),
        }))
        .filter(
          (
            item
          ): item is {
            event: (typeof stream.events)[number];
            descriptor: NonNullable<ReturnType<typeof describePlaygroundStreamEvent>>;
          } => item.descriptor !== null
        ),
    [selectedGraphScenario, stream.events]
  );
  const completionEvent = useMemo(
    () => stream.events.findLast((event) => event.event_type === "run.complete") ?? null,
    [stream.events]
  );
  const progressScenario = activeScenario ?? selectedGraphScenario;
  const progressNodes = useMemo(
    () => derivePlaygroundProgressNodes(progressScenario, stream.events),
    [progressScenario, stream.events]
  );
  const debugEntries = useMemo(
    () => derivePlaygroundDebugEntries(stream.events),
    [stream.events]
  );
  const showAIDebugPanel = targetChoice?.kind === "ai";

  useEffect(() => {
    if (!autoScroll) {
      return;
    }
    const viewport = feedViewportRef.current;
    if (!viewport) {
      return;
    }
    viewport.scrollTop = viewport.scrollHeight;
  }, [autoScroll, feedItems.length]);

  useEffect(() => {
    try {
      setDebugPanelOpen(localStorage.getItem("playground-debug-panel-open") === "true");
    } catch {
      setDebugPanelOpen(false);
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("playground-debug-panel-open", debugPanelOpen ? "true" : "false");
    } catch {
      // ignore storage failures
    }
  }, [debugPanelOpen]);

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading playground permissions…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canUsePlayground) {
    return (
      <AccessPanel
        title="Playground"
        message="Playground access is restricted to editor role or above."
      />
    );
  }

  const noTargets =
    (graphScenarios?.length ?? 0) === 0 && (aiScenarios?.length ?? 0) === 0;
  const launchButtonLabel =
    runId || presetLoaded ? "Relaunch Current Setup" : "Run Playground";
  const canEditScenarioYaml =
    targetChoice?.kind === "graph" && Boolean(selectedGraphScenario);
  const runButtonDisabled =
    submitting ||
    runActive ||
    !targetChoice ||
    (mode === "mock" && !systemPrompt.trim()) ||
    (mode === "direct_http" && !transportProfileId) ||
    hasInvalidStubs;
  const mainPaneGridClass = launchControlsOpen
    ? "grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]"
    : showAIDebugPanel
      ? "grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_320px_320px]"
      : "grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Playground</h1>
          <p className="mt-0.5 max-w-3xl text-sm text-text-secondary">
            Run graph or AI scenarios against a mock agent or a direct HTTP bot
            endpoint before you expose them to production telephony.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {canEditScenarioYaml ? (
            <Button
              type="button"
              variant="secondary"
              data-testid="playground-edit-yaml-button"
              onClick={() => setEditingScenarioId(selectedGraphScenario?.id ?? null)}
            >
              <PencilLine className="h-4 w-4" />
              Edit Scenario YAML
            </Button>
          ) : null}
          {runId ? (
            <Link
              href={`/runs/${runId}`}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-bg-base"
            >
              Open Run
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            data-testid="playground-launch-controls-toggle"
            onClick={() => setLaunchControlsOpen((current) => !current)}
          >
            {launchControlsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {launchControlsOpen ? "Hide Launch Controls" : "Configure Playground"}
          </Button>
          <Button
            data-testid="playground-run-button"
            onClick={() => void handleRunPlayground()}
            disabled={runButtonDisabled}
          >
            {submitting ? "Launching…" : runActive ? "Run In Progress" : launchButtonLabel}
          </Button>
        </div>
      </div>

      {error ? <p className="text-sm text-fail">{error}</p> : null}
      {success ? <p className="text-sm text-pass">{success}</p> : null}
      {graphScenariosError ? (
        <p className="text-sm text-fail">{graphScenariosError.message}</p>
      ) : null}

      <div className={launchControlsOpen ? "grid gap-6 xl:grid-cols-[minmax(0,520px)_minmax(0,1fr)]" : "space-y-0"}>
        {launchControlsOpen ? (
          <div className="space-y-6">
            <PlaygroundLaunchControlsCard
              noTargets={noTargets}
              presets={presets ?? []}
              selectedPresetId={selectedPresetId}
              selectedPresetSummary={selectedPresetSummary}
              loadingPreset={loadingPreset}
              presetName={presetName}
              presetDescription={presetDescription}
              onSelectPreset={handleSelectPreset}
              onChangePresetName={setPresetName}
              onChangePresetDescription={setPresetDescription}
              onLoadPreset={() => void handleLoadPreset()}
              canPersistPreset={canPersistPreset}
              savingPreset={savingPreset}
              deletingPreset={deletingPreset}
              savingPresetAction={savingPresetAction}
              onCreatePreset={() => void handleCreatePreset()}
              onUpdatePreset={() => void handleUpdatePreset()}
              onDuplicatePreset={() => void handleDuplicatePreset()}
              onDeletePreset={() => {
                const label = selectedPresetSummary?.name ?? "this preset";
                if (window.confirm(`Delete preset "${label}"? This cannot be undone.`)) {
                  void handleDeletePreset();
                }
              }}
              targetChoice={targetChoice}
              graphScenarios={graphScenarios ?? []}
              aiEnabled={aiEnabled}
              aiScenarios={aiScenarios ?? []}
              onChangeTargetChoice={setTargetChoice}
              mode={mode}
              onChangeMode={setMode}
              systemPrompt={systemPrompt}
              onChangeSystemPrompt={setSystemPrompt}
              personas={personas ?? []}
              personaId={personaId}
              onChangePersonaId={setPersonaId}
              loadingPersonaPrompt={loadingPersonaPrompt}
              onLoadPersonaPrompt={() => void handleLoadPersonaPrompt()}
              extractedTools={extractedTools}
              stubEditorJson={stubEditorJson}
              invalidStubNames={invalidStubNames}
              hasInvalidStubs={hasInvalidStubs}
              extractingTools={extractingTools}
              generatingStubs={generatingStubs}
              stubError={stubError}
              onExtractTools={() => void handleExtractTools()}
              onGenerateStubs={() => void handleGenerateStubs()}
              onChangeStubEditorJson={(name, value) =>
                setStubEditorJson((prev) => ({ ...prev, [name]: value }))
              }
              selectedTransport={selectedTransport}
              transportProfileId={transportProfileId}
              httpTransportProfiles={httpTransportProfiles}
              onChangeTransportProfileId={setTransportProfileId}
              runId={runId}
              runActive={runActive}
              presetLoaded={presetLoaded}
            />
            <TenantProviderAccessCard
              testId="playground-provider-access-card"
              title="Tenant provider access"
              description="Scenario speech overrides, AI caller flows, and eval-side reasoning all resolve from the providers assigned to this tenant."
              providers={availableProviders}
              capabilities={["tts", "stt", "llm", "judge"]}
              loading={!availableProvidersResponse && !availableProvidersError}
              errorMessage={availableProvidersError?.message ?? null}
            />
          </div>
        ) : null}

        <div className={mainPaneGridClass}>
          <PlaygroundLiveActivityCard
            runId={runId}
            completionEvent={completionEvent}
            stream={stream}
            feedItems={feedItems}
            feedViewportRef={feedViewportRef}
            autoScroll={autoScroll}
            onToggleAutoScroll={() => setAutoScroll((current) => !current)}
            mode={mode}
            debugPanel={
              launchControlsOpen && showAIDebugPanel ? (
                <PlaygroundDebugCard
                  debugEntries={debugEntries}
                  debugPanelOpen={debugPanelOpen}
                  onToggle={() => setDebugPanelOpen((current) => !current)}
                />
              ) : null
            }
          />

          <PlaygroundProgressCard
            progressScenario={progressScenario}
            selectedAIScenario={selectedAIScenario}
            progressNodes={progressNodes}
            completionRunId={completionEvent && runId ? runId : null}
          />

          {!launchControlsOpen && showAIDebugPanel ? (
            <PlaygroundDebugCard
              debugEntries={debugEntries}
              debugPanelOpen={debugPanelOpen}
              onToggle={() => setDebugPanelOpen((current) => !current)}
              className="min-h-[640px] xl:sticky xl:top-6"
            />
          ) : null}
        </div>
      </div>

      <ScenarioEditDialog
        scenarioId={editingScenarioId}
        onClose={() => setEditingScenarioId(null)}
        onSuccess={() => {
          void mutateGraphScenarios();
          notifySuccess("Scenario YAML updated.");
        }}
      />
    </div>
  );
}
