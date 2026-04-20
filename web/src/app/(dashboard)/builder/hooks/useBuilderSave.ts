"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import {
  getScenarioSource,
  mapApiError,
  updateScenario,
  uploadScenario,
  validateScenarioYaml,
  useScenarios,
} from "@/lib/api";
import { flowToYaml } from "@/lib/flow-translator";
import { readLayoutPositions } from "@/lib/flow-layout-storage";
import { useBuilderStore } from "@/lib/builder-store";
import {
  computeNodeStructuralErrors,
  describeScenarioValidationErrors,
  type NodeStructuralErrors,
} from "@/lib/builder-validation";
import { createCopiedScenarioYaml } from "@/lib/builder-draft";
import type { PushToast } from "./useBuilderToast";

export function useBuilderSave(
  scenarioId: string | null,
  setScenarioId: (id: string) => void,
  layoutKey: string,
  pushToast: PushToast,
  loadDraftYaml: (yaml: string, status: string, nextFocusField?: "metadata-id") => void
) {
  const router = useRouter();
  const { data: scenarioLibrary } = useScenarios();
  const [saveState, setSaveState] = useState<"idle" | "saving">("idle");
  const [saveError, setSaveError] = useState<string>("");
  const [validationNodeErrors, setValidationNodeErrors] = useState<NodeStructuralErrors>({});
  const [copyingScenarioId, setCopyingScenarioId] = useState<string | null>(null);
  const saveInFlightRef = useRef(false);

  const nodes = useBuilderStore((state) => state.nodes);
  const edges = useBuilderStore((state) => state.edges);
  const yamlDraft = useBuilderStore((state) => state.yamlDraft);
  const yamlCanonical = useBuilderStore((state) => state.yamlCanonical);
  const parseError = useBuilderStore((state) => state.parseError);
  const isDirty = useBuilderStore((state) => state.isDirty);
  const applyYamlDraft = useBuilderStore((state) => state.applyYamlDraft);
  const markSaved = useBuilderStore((state) => state.markSaved);
  const setCanvasCanonicalYaml = useBuilderStore((state) => state.setCanvasCanonicalYaml);
  const setStatusMessage = useBuilderStore((state) => state.setStatusMessage);

  const nodeStructuralErrors = computeNodeStructuralErrors(nodes, edges);
  const hasStructuralErrors = Object.keys(nodeStructuralErrors).length > 0;

  // When the canonical YAML changes outside of an active save (e.g. the user
  // applies a YAML draft in the editor), any previously-stored API validation
  // node errors are stale and must be cleared so they don't linger on nodes
  // that the user has already corrected.
  const prevYamlCanonicalRef = useRef(yamlCanonical);
  useEffect(() => {
    if (
      yamlCanonical !== prevYamlCanonicalRef.current &&
      !saveInFlightRef.current
    ) {
      setValidationNodeErrors({});
    }
    prevYamlCanonicalRef.current = yamlCanonical;
  }, [yamlCanonical]);

  const canSave =
    !saveState || saveState !== "saving"
      ? isDirty && !parseError && !hasStructuralErrors
      : false;

  const handleSave = useCallback(async () => {
    if (saveInFlightRef.current) {
      pushToast("Save already in progress.", "warn");
      return;
    }
    setSaveError("");
    setValidationNodeErrors({});
    setStatusMessage(null);

    if (hasStructuralErrors) {
      setSaveError("Resolve structural node issues before saving.");
      pushToast("Resolve structural node issues before saving.", "warn");
      return;
    }

    if (yamlDraft !== yamlCanonical) {
      const savedPositions = readLayoutPositions(layoutKey);
      const ok = applyYamlDraft(savedPositions);
      if (!ok) {
        setSaveError("Fix YAML parse errors before saving.");
        pushToast("Fix YAML parse errors before saving.", "warn");
        return;
      }
    }

    const currentState = useBuilderStore.getState();
    const currentYaml =
      currentState.syncSource === "canvas"
        ? flowToYaml({
            nodes: currentState.nodes,
            edges: currentState.edges,
            meta: currentState.meta,
          })
        : currentState.yamlCanonical;

    if (currentYaml !== currentState.yamlCanonical) {
      setCanvasCanonicalYaml(currentYaml);
    }

    saveInFlightRef.current = true;
    setSaveState("saving");
    try {
      const validation = await validateScenarioYaml(currentYaml);
      if (!validation.valid) {
        const described = describeScenarioValidationErrors(validation.errors, currentYaml);
        setValidationNodeErrors(described.nodeErrors);
        setSaveError(described.saveError);
        pushToast(described.saveError.split("\n")[0] ?? "Validation failed.", "warn");
        return;
      }

      setValidationNodeErrors({});
      if (scenarioId) {
        await updateScenario(scenarioId, currentYaml);
      } else {
        const created = await uploadScenario(currentYaml);
        setScenarioId(created.id);
        router.replace(`/builder?id=${encodeURIComponent(created.id)}` as Route);
      }
      markSaved();
      setStatusMessage("Scenario saved");
      pushToast("Scenario saved.", "info");
    } catch (error) {
      setValidationNodeErrors({});
      const { message, tone } = mapApiError(error, "Save failed.");
      setSaveError(message);
      pushToast(message, tone);
    } finally {
      setSaveState("idle");
      saveInFlightRef.current = false;
    }
  }, [
    applyYamlDraft,
    hasStructuralErrors,
    layoutKey,
    markSaved,
    pushToast,
    router,
    scenarioId,
    setCanvasCanonicalYaml,
    setScenarioId,
    setStatusMessage,
    yamlCanonical,
    yamlDraft,
  ]);

  const handleCopyScenario = useCallback(
    async (sourceId: string) => {
      setCopyingScenarioId(sourceId);
      setSaveError("");
      try {
        const source = await getScenarioSource(sourceId);
        const existingIds = new Set((scenarioLibrary ?? []).map((scenario) => scenario.id));
        const copied = createCopiedScenarioYaml(source.yaml_content, existingIds);
        loadDraftYaml(copied.yaml, `Copied ${sourceId} to ${copied.copiedId}`, "metadata-id");
        pushToast(`Copied ${sourceId} to ${copied.copiedId}.`, "info");
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to copy scenario.";
        setSaveError(message);
        pushToast(message, "error");
      } finally {
        setCopyingScenarioId((current) => (current === sourceId ? null : current));
      }
    },
    [loadDraftYaml, pushToast, scenarioLibrary]
  );

  return {
    saveState,
    saveError,
    setSaveError,
    validationNodeErrors,
    canSave,
    copyingScenarioId,
    handleSave,
    handleCopyScenario,
  };
}
