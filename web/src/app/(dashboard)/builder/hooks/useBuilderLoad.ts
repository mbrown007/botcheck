"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { getScenarioSource } from "@/lib/api";
import type { ScenarioSummary } from "@/lib/api/types";
import { resolveBuilderScenarioAccess } from "@/lib/builder-scenario-access";
import {
  buildSeededBuilderDraftYaml,
  type BuilderDraftSeedPayload,
  type BuilderFocusField,
  BUILDER_DRAFT_SEED_KEY,
  BUILDER_FOCUS_FIELD_KEY,
  BUILDER_NEW_SENTINEL_QUERY,
  writeBuilderDraftSeed,
} from "@/lib/builder-draft-seed";
import { readLayoutPositions, writeLayoutPositions } from "@/lib/flow-layout-storage";
import { useBuilderStore } from "@/lib/builder-store";
import type { PushToast } from "./useBuilderToast";

export { BUILDER_DRAFT_SEED_KEY, BUILDER_FOCUS_FIELD_KEY };

export function useBuilderLoad(
  scenarioId: string | null,
  layoutKey: string,
  pushToast: PushToast,
  setFocusField: (field: BuilderFocusField | null) => void,
  scenarios: readonly ScenarioSummary[] | null | undefined,
  scenariosResolved: boolean,
  pendingSeed: BuilderDraftSeedPayload | null
) {
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string>("");
  // Track which seed yaml has been applied so re-fires after router.replace don't
  // double-hydrate the store with the same payload.
  const appliedSeedRef = useRef<string | null>(null);

  const hydrateFromYaml = useBuilderStore((state) => state.hydrateFromYaml);
  const isDirty = useBuilderStore((state) => state.isDirty);
  const reset = useBuilderStore((state) => state.reset);
  const setStatusMessage = useBuilderStore((state) => state.setStatusMessage);
  const updateMeta = useBuilderStore((state) => state.updateMeta);

  const handleLoadYaml = useCallback(
    (yaml: string) => {
      const savedPositions = readLayoutPositions(layoutKey);
      hydrateFromYaml(yaml, savedPositions);
      if (!savedPositions || Object.keys(savedPositions).length === 0) {
        const freshNodes = useBuilderStore.getState().nodes;
        writeLayoutPositions(layoutKey, freshNodes);
      }
    },
    [hydrateFromYaml, layoutKey]
  );

  const canDiscardForDraftLoad = useCallback(() => {
    if (!isDirty) {
      return true;
    }
    const confirmed = window.confirm("Discard unsaved changes and replace current draft?");
    if (!confirmed) {
      pushToast("Load cancelled; kept current draft.", "info");
    }
    return confirmed;
  }, [isDirty, pushToast]);

  const loadDraftYaml = useCallback(
    (yaml: string, status: string, nextFocusField?: BuilderFocusField) => {
      if (!canDiscardForDraftLoad()) {
        return;
      }
      if (scenarioId) {
        writeBuilderDraftSeed({
          yaml,
          focusField: nextFocusField,
        });
        pushToast("Opening new draft workspace…", "info");
        router.push(`/builder?${BUILDER_NEW_SENTINEL_QUERY}` as Route);
        return;
      }
      handleLoadYaml(yaml);
      if (nextFocusField) {
        setFocusField(nextFocusField);
      }
      setStatusMessage(status);
      pushToast(status, "info");
    },
    [
      canDiscardForDraftLoad,
      handleLoadYaml,
      pushToast,
      router,
      scenarioId,
      setFocusField,
      setStatusMessage,
    ]
  );

  useEffect(() => {
    let cancelled = false;
    setLoadError("");
    setLoading(true);
    reset();

    const access = resolveBuilderScenarioAccess({
      scenarioId,
      scenarios,
      scenariosResolved,
    });

    if (!scenarioId) {
      try {
        if (pendingSeed?.yaml && appliedSeedRef.current !== pendingSeed.yaml) {
          appliedSeedRef.current = pendingSeed.yaml;
          if (pendingSeed.focusField === "metadata-id") {
            setFocusField("metadata-id");
          }
          handleLoadYaml(pendingSeed.yaml);
          setStatusMessage("Loaded seeded draft");
          router.replace("/builder" as Route);
        } else {
          handleLoadYaml(
            buildSeededBuilderDraftYaml({
              name: "Draft Scenario",
              templateKey: "blank",
              startMode: "caller_opens",
            })
          );
        }
      } catch (error) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Failed to hydrate draft scenario.";
          setLoadError(message);
          pushToast(message, "error");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
      return () => {
        cancelled = true;
      };
    }

    if (access.shouldDeferLoad) {
      return () => {
        cancelled = true;
      };
    }

    if (access.shouldRedirectToAIScenarios) {
      setLoading(false);
      pushToast("AI scenarios are edited from AI Scenarios.", "warn");
      router.replace("/ai-scenarios" as Route);
      return () => {
        cancelled = true;
      };
    }

    getScenarioSource(scenarioId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        handleLoadYaml(response.yaml_content);
        const scenarioSummary =
          (scenarios ?? []).find((scenario) => scenario.id === scenarioId) ?? null;
        if (scenarioSummary?.namespace) {
          const currentMeta = useBuilderStore.getState().meta;
          const currentNamespace =
            typeof currentMeta.namespace === "string" ? currentMeta.namespace.trim() : "";
          if (!currentNamespace) {
            updateMeta({
              ...currentMeta,
              namespace: scenarioSummary.namespace,
            });
          }
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "Failed to load scenario YAML.";
        setLoadError(message);
        pushToast(message, "error");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    handleLoadYaml,
    pushToast,
    reset,
    router,
    scenarioId,
    scenarios,
    scenariosResolved,
    setFocusField,
    setStatusMessage,
    updateMeta,
    pendingSeed,
  ]);

  return { loading, loadError, handleLoadYaml, loadDraftYaml };
}
