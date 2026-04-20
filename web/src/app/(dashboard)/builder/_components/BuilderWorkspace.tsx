"use client";

import Link from "next/link";
import type { Route } from "next";
import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import {
  buildScenarioCacheTurnLookup,
  scenarioCacheCoverageLabel,
} from "@/lib/scenario-cache";
import {
  buildLayoutStorageKey,
  getOrCreateDraftLayoutSessionId,
} from "@/lib/flow-layout-storage";
import { useBuilderStore } from "@/lib/builder-store";
import { computeNodeStructuralErrors } from "@/lib/builder-validation";
import type { BuilderDraftSeedPayload, BuilderFocusField } from "@/lib/builder-draft-seed";
import type { ScenarioSummary } from "@/lib/api/types";
import {
  useScenarioCacheState,
  useFeatures,
} from "@/lib/api";
import { buildSpeechCapabilitiesFromAvailableProviders } from "@/lib/provider-availability";
import { resolveBuilderScenarioAccess } from "@/lib/builder-scenario-access";

import { useBuilderToast } from "../hooks/useBuilderToast";
import { useBuilderSync } from "../hooks/useBuilderSync";
import { useBuilderLoad } from "../hooks/useBuilderLoad";
import { useBuilderSave } from "../hooks/useBuilderSave";
import { useBuilderKeyboard } from "../hooks/useBuilderKeyboard";
import { useBuilderCanvasInteractions } from "../hooks/useBuilderCanvasInteractions";
import { useBuilderWorkspaceLayout } from "../hooks/useBuilderWorkspaceLayout";
import { useBuilderWorkspaceActions } from "../hooks/useBuilderWorkspaceActions";
import { BuilderToolbar } from "./BuilderToolbar";
import { BuilderCanvas, type ClipboardTurn } from "./BuilderCanvas";
import { MetadataPanel } from "./MetadataPanel";
import { BuilderWorkspaceFeedback } from "./BuilderWorkspaceFeedback";
import { YAMLEditorPanel } from "./YAMLEditorPanel";
import { CollapsedTurnBlocksRail, TurnBlocksPalette } from "./TurnBlocksPalette";
import { ScenarioLibrary } from "./ScenarioLibrary";

type BuilderWorkspaceProps = {
  scenarioAccess: ReturnType<typeof resolveBuilderScenarioAccess>;
  scenarioId: string | null;
  tenantId: string;
  features: ReturnType<typeof useFeatures>["data"];
  speechCapabilities: ReturnType<typeof buildSpeechCapabilitiesFromAvailableProviders>;
  scenarioLibrary: readonly ScenarioSummary[] | null | undefined;
  scenariosResolved: boolean;
  pendingSeed: BuilderDraftSeedPayload | null;
};

export function BuilderWorkspace({
  scenarioAccess,
  scenarioId,
  tenantId,
  features,
  speechCapabilities,
  scenarioLibrary,
  scenariosResolved,
  pendingSeed,
}: BuilderWorkspaceProps) {
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(scenarioId);
  const [focusField, setFocusField] = useState<BuilderFocusField | null>(null);
  const [clipboardTurn, setClipboardTurn] = useState<ClipboardTurn | null>(null);

  useEffect(() => {
    setActiveScenarioId(scenarioId);
  }, [scenarioId]);

  const nodes = useBuilderStore((state) => state.nodes);
  const edges = useBuilderStore((state) => state.edges);
  const parseError = useBuilderStore((state) => state.parseError);
  const isDirty = useBuilderStore((state) => state.isDirty);
  const syncSource = useBuilderStore((state) => state.syncSource);
  const statusMessage = useBuilderStore((state) => state.statusMessage);
  const yamlDraft = useBuilderStore((state) => state.yamlDraft);
  const yamlCanonical = useBuilderStore((state) => state.yamlCanonical);
  const undo = useBuilderStore((state) => state.undo);
  const redo = useBuilderStore((state) => state.redo);

  const sessionId = useMemo(() => {
    if (activeScenarioId) {
      return "scenario";
    }
    return getOrCreateDraftLayoutSessionId();
  }, [activeScenarioId]);
  const layoutKey = useMemo(
    () => buildLayoutStorageKey({ tenantId, scenarioId: activeScenarioId, sessionId }),
    [activeScenarioId, sessionId, tenantId],
  );

  const ttsPreviewEnabled = features?.tts_cache_enabled === true;
  const { data: cacheState, mutate: mutateCacheState } = useScenarioCacheState(
    activeScenarioId,
    ttsPreviewEnabled && activeScenarioId !== null,
  );
  const turnCacheById = useMemo(() => buildScenarioCacheTurnLookup(cacheState), [cacheState]);
  const cacheCoverage = useMemo(() => scenarioCacheCoverageLabel(cacheState), [cacheState]);

  const nodeStructuralErrors = useMemo(
    () => computeNodeStructuralErrors(nodes, edges),
    [edges, nodes],
  );
  const structuralErrorCount = Object.keys(nodeStructuralErrors).length;
  const hasStructuralErrors = structuralErrorCount > 0;

  const {
    collapsePanel,
    expandPanel,
    handleStartPanelResize,
    isResizingPanel,
    layoutGridRef,
    libraryOpen,
    metadataOpen,
    mobilePane,
    panelGridStyle,
    panelOpen,
    setMobilePane,
    toggleLibraryOpen,
    toggleMetadataOpen,
    toggleTurnBlocksOpen,
    toggleYamlOpen,
    turnBlocksOpen,
    yamlOpen,
  } = useBuilderWorkspaceLayout({
    focusField,
    hasStructuralErrors,
    parseError,
  });

  useEffect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent) {
      if (!isDirty) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [isDirty]);

  const { toasts, pushToast } = useBuilderToast();
  const { handleApplyYaml } = useBuilderSync(layoutKey);
  const {
    canvasRef,
    handleCopySelectedBlock,
    handleDeleteSelectedBlocks,
    handleInsertBlock,
    handlePasteCopiedBlock,
  } = useBuilderCanvasInteractions();
  const selectedNodeIds = useMemo(
    () => nodes.filter((node) => node.selected).map((node) => node.id),
    [nodes],
  );
  const hasSelection = selectedNodeIds.length > 0;
  const selectedNodeCount = selectedNodeIds.length;

  const { loading, loadError, loadDraftYaml } = useBuilderLoad(
    activeScenarioId,
    layoutKey,
    pushToast,
    setFocusField,
    scenarioLibrary,
    scenariosResolved,
    pendingSeed,
  );
  const {
    saveState,
    saveError,
    setSaveError,
    validationNodeErrors,
    canSave,
    copyingScenarioId,
    handleSave,
    handleCopyScenario,
  } = useBuilderSave(
    activeScenarioId,
    (id) => setActiveScenarioId(id),
    layoutKey,
    pushToast,
    loadDraftYaml,
  );
  const {
    handleBackToScenarios,
    handleExportYaml,
    handleImportYamlFile,
    handleRebuildCache,
    handleSelectScenario,
    rebuildingCache,
  } = useBuilderWorkspaceActions({
    activeScenarioId,
    isDirty,
    loadDraftYaml,
    mutateCacheState,
    scenarioLibrary,
    setSaveError,
    ttsPreviewEnabled,
    yamlCanonical,
    yamlDraft,
    pushToast,
  });

  useBuilderKeyboard({
    canSave,
    handleSave,
    handleCopySelectedBlock,
    handlePasteCopiedBlock,
    handleDeleteSelectedBlocks,
    undo,
    redo,
  });

  return (
    <div className="flex h-full min-h-[calc(100vh-7rem)] flex-col gap-4">
      <BuilderToolbar
        scenarioId={activeScenarioId}
        loading={loading}
        saveState={saveState}
        canSave={canSave}
        cacheStatus={cacheState?.cache_status ?? null}
        cacheCoverage={cacheCoverage}
        canRebuildCache={ttsPreviewEnabled && activeScenarioId !== null}
        rebuildingCache={rebuildingCache}
        onSave={() => void handleSave()}
        onBack={handleBackToScenarios}
        onApplyYaml={handleApplyYaml}
        onExportYaml={handleExportYaml}
        onImportYaml={(file) => void handleImportYamlFile(file)}
        onNewScenario={() => handleSelectScenario(null)}
        onRebuildCache={() => void handleRebuildCache()}
      />

      <div className="lg:hidden">
        <div className="inline-flex rounded-md border border-border bg-bg-surface p-1">
          <button
            type="button"
            onClick={() => setMobilePane("visual")}
            className={cn(
              "rounded px-3 py-1 text-xs",
              mobilePane === "visual" ? "bg-brand-muted text-brand" : "text-text-secondary",
            )}
          >
            Visual
          </button>
          <button
            type="button"
            onClick={() => setMobilePane("yaml")}
            className={cn(
              "rounded px-3 py-1 text-xs",
              mobilePane === "yaml" ? "bg-brand-muted text-brand" : "text-text-secondary",
            )}
          >
            YAML
          </button>
        </div>
      </div>

      <BuilderWorkspaceFeedback
        loadError={loadError || null}
        parseError={parseError}
        redirectToAIScenarios={scenarioAccess.shouldRedirectToAIScenarios}
        saveError={saveError || null}
        statusMessage={statusMessage}
        structuralErrorCount={structuralErrorCount}
        toasts={toasts}
      />

      <div
        ref={layoutGridRef}
        style={panelGridStyle}
        className="grid min-h-0 flex-1 gap-4 transition-[grid-template-columns] duration-150 lg:grid-cols-[minmax(0,1fr)_var(--builder-panel-width)]"
      >
        <div className={cn("flex h-full min-h-0 flex-col", mobilePane !== "visual" && "hidden lg:block")}>
          <BuilderCanvas
            ref={canvasRef}
            scenarioId={activeScenarioId}
            cacheBucketName={cacheState?.bucket_name ?? null}
            turnCacheById={turnCacheById}
            validationNodeErrors={validationNodeErrors}
            layoutKey={layoutKey}
            clipboardTurn={clipboardTurn}
            setClipboardTurn={setClipboardTurn}
            onToast={pushToast}
          />
        </div>

        {!panelOpen ? (
          <CollapsedTurnBlocksRail
            clipboardTurn={clipboardTurn}
            hasSelection={hasSelection}
            selectedNodeCount={selectedNodeCount}
            onExpand={expandPanel}
            onInsertBlock={handleInsertBlock}
            onCopy={handleCopySelectedBlock}
            onPaste={handlePasteCopiedBlock}
            onDelete={handleDeleteSelectedBlocks}
          />
        ) : (
          <div
            data-testid="builder-right-panel"
            className={cn(
              "relative flex flex-col rounded-lg border border-border bg-bg-surface",
              mobilePane !== "yaml" && "hidden lg:flex",
            )}
          >
            <button
              type="button"
              onMouseDown={handleStartPanelResize}
              data-testid="panel-resize-handle"
              className={cn(
                "absolute inset-y-0 left-0 z-10 hidden w-2 -translate-x-1/2 cursor-col-resize rounded-full bg-transparent transition hover:bg-brand/20 lg:block",
                isResizingPanel && "bg-brand/30",
              )}
              title="Resize panel"
              aria-label="Resize panel"
            />
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                Panel
              </span>
              <button
                type="button"
                onClick={collapsePanel}
                title="Collapse panel"
                className="text-sm text-text-muted hover:text-text-primary"
              >
                ‹
              </button>
            </div>

            <div className="flex flex-col gap-3 overflow-y-auto p-3">
              <TurnBlocksPalette
                open={turnBlocksOpen}
                onToggle={toggleTurnBlocksOpen}
                clipboardTurn={clipboardTurn}
                selectedNodeIds={selectedNodeIds}
                hasSelection={hasSelection}
                onInsertBlock={handleInsertBlock}
                onCopy={handleCopySelectedBlock}
                onPaste={handlePasteCopiedBlock}
                onDelete={handleDeleteSelectedBlocks}
              />

              <ScenarioLibrary
                open={libraryOpen}
                onToggle={toggleLibraryOpen}
                scenarioId={activeScenarioId}
                copyingScenarioId={copyingScenarioId}
                onSelect={handleSelectScenario}
                onCopy={(id) => void handleCopyScenario(id)}
              />

              <MetadataPanel
                open={metadataOpen}
                onToggle={toggleMetadataOpen}
                focusField={focusField}
                onFocusConsumed={() => setFocusField(null)}
                speechCapabilities={speechCapabilities}
              />

              <YAMLEditorPanel
                open={yamlOpen}
                onToggle={toggleYamlOpen}
                loading={loading}
                saveState={saveState}
                onApplyYaml={handleApplyYaml}
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>
          Sync source: <span className="font-mono">{syncSource}</span>
        </span>
        <Link href={"/scenarios" as Route} className="hover:text-text-secondary">
          Scenario library
        </Link>
      </div>
    </div>
  );
}
