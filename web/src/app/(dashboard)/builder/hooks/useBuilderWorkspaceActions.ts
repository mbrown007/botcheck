"use client";

import YAML from "yaml";
import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";

import { mapApiError, rebuildScenarioCache } from "@/lib/api";
import type { ScenarioSummary } from "@/lib/api/types";

import type { PushToast } from "./useBuilderToast";

type UseBuilderWorkspaceActionsArgs = {
  activeScenarioId: string | null;
  isDirty: boolean;
  loadDraftYaml: (yaml: string, status: string, nextFocusField?: "metadata-id") => void;
  mutateCacheState: () => Promise<unknown>;
  scenarioLibrary: readonly ScenarioSummary[] | null | undefined;
  setSaveError: (message: string) => void;
  ttsPreviewEnabled: boolean;
  yamlCanonical: string;
  yamlDraft: string;
  pushToast: PushToast;
};

export function useBuilderWorkspaceActions({
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
}: UseBuilderWorkspaceActionsArgs) {
  const router = useRouter();
  const [rebuildingCache, setRebuildingCache] = useState(false);

  const handleBackToScenarios = useCallback(() => {
    if (isDirty && !window.confirm("Discard unsaved changes and leave builder?")) {
      return;
    }
    router.push("/scenarios" as Route);
  }, [isDirty, router]);

  const handleSelectScenario = useCallback(
    (targetScenarioId: string | null) => {
      if (targetScenarioId === activeScenarioId) {
        return;
      }
      if (isDirty && !window.confirm("Discard unsaved changes and switch scenario?")) {
        return;
      }
      if (targetScenarioId) {
        const targetScenario =
          (scenarioLibrary ?? []).find((scenario) => scenario.id === targetScenarioId) ?? null;
        if (targetScenario?.scenario_kind === "ai") {
          pushToast("AI scenarios are edited from AI Scenarios.", "warn");
          router.push("/ai-scenarios" as Route);
          return;
        }
        router.push(`/builder?id=${encodeURIComponent(targetScenarioId)}` as Route);
        return;
      }
      router.push("/builder" as Route);
    },
    [activeScenarioId, isDirty, pushToast, router, scenarioLibrary],
  );

  const handleExportYaml = useCallback(() => {
    const yamlForExport = yamlDraft || yamlCanonical;
    if (!yamlForExport.trim()) {
      return;
    }
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = YAML.parse(yamlForExport) as Record<string, unknown> | null;
    } catch {
      parsed = null;
    }
    const rawId =
      typeof parsed?.id === "string" ? parsed.id : activeScenarioId ?? "scenario-draft";
    const safeId = rawId.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/-+/g, "-");
    const filename = `${safeId || "scenario-draft"}.yaml`;
    const blob = new Blob([yamlForExport], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, [activeScenarioId, yamlCanonical, yamlDraft]);

  const handleImportYamlFile = useCallback(
    async (file: File) => {
      try {
        const importedYaml = await file.text();
        if (!importedYaml.trim()) {
          setSaveError("Imported file is empty.");
          return;
        }
        loadDraftYaml(importedYaml, `Imported ${file.name} as draft`);
      } catch (error) {
        setSaveError(error instanceof Error ? error.message : "Failed to import YAML file.");
      }
    },
    [loadDraftYaml, setSaveError],
  );

  const handleRebuildCache = useCallback(async () => {
    if (!activeScenarioId || !ttsPreviewEnabled) {
      return;
    }
    setRebuildingCache(true);
    try {
      await rebuildScenarioCache(activeScenarioId);
      await mutateCacheState();
      pushToast("Cache rebuild queued.", "info");
    } catch (error) {
      const { message, tone } = mapApiError(error, "Failed to rebuild cache.");
      pushToast(message, tone);
    } finally {
      setRebuildingCache(false);
    }
  }, [activeScenarioId, mutateCacheState, pushToast, ttsPreviewEnabled]);

  return {
    handleBackToScenarios,
    handleExportYaml,
    handleImportYamlFile,
    handleRebuildCache,
    handleSelectScenario,
    rebuildingCache,
  };
}
