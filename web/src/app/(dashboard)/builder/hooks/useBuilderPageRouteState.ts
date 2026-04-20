"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";

import { filterGraphScenarios, resolveBuilderScenarioAccess } from "@/lib/builder-scenario-access";
import {
  buildSeededBuilderDraftYaml,
  BUILDER_NEW_SENTINEL_QUERY,
  clearBuilderDraftSeed,
  consumeBuilderDraftSeed,
  type BuilderDraftSeedPayload,
  writeBuilderDraftSeed,
} from "@/lib/builder-draft-seed";
import type { ScenarioSummary } from "@/lib/api/types";

type UseBuilderPageRouteStateArgs = {
  isDraftStart: boolean;
  scenarioIdParam: string | null;
  scenarioLibrary: readonly ScenarioSummary[] | null | undefined;
  scenarioLibraryError: unknown;
};

export function useBuilderPageRouteState({
  isDraftStart,
  scenarioIdParam,
  scenarioLibrary,
  scenarioLibraryError,
}: UseBuilderPageRouteStateArgs) {
  const router = useRouter();
  const [pendingSeed, setPendingSeed] = useState<BuilderDraftSeedPayload | null | undefined>(
    undefined,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagsOpen, setTagsOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (scenarioIdParam) {
      setPendingSeed(null);
      return;
    }
    if (isDraftStart) {
      setPendingSeed(consumeBuilderDraftSeed());
      return;
    }
    clearBuilderDraftSeed();
    setPendingSeed((current) => (current?.yaml ? current : null));
    // Reset to undefined on cleanup so back-navigation or param changes show
    // "Preparing builder…" for one cycle instead of flashing stale seed state.
    return () => {
      setPendingSeed(undefined);
    };
  }, [isDraftStart, scenarioIdParam]);

  const handleStartBuilding = useCallback(
    (seed: Parameters<typeof buildSeededBuilderDraftYaml>[0]) => {
      writeBuilderDraftSeed({
        yaml: buildSeededBuilderDraftYaml(seed),
        focusField: "metadata-id",
      });
      router.push(`/builder?${BUILDER_NEW_SENTINEL_QUERY}` as Route);
    },
    [router],
  );

  const handleOpenScenario = useCallback(
    (scenarioId: string) => {
      router.push(`/builder?id=${encodeURIComponent(scenarioId)}` as Route);
    },
    [router],
  );

  const isDraftWorkspace = isDraftStart || Boolean(pendingSeed?.yaml);
  const scenariosResolved =
    !scenarioIdParam || Boolean(scenarioLibrary) || Boolean(scenarioLibraryError);
  const scenarioListResolved = Boolean(scenarioLibrary) || Boolean(scenarioLibraryError);

  const scenarioAccess = useMemo(
    () =>
      resolveBuilderScenarioAccess({
        scenarioId: scenarioIdParam,
        scenarios: scenarioLibrary,
        scenariosResolved,
      }),
    [scenarioIdParam, scenarioLibrary, scenariosResolved],
  );

  const graphScenarios = useMemo(
    () => filterGraphScenarios(scenarioLibrary ?? []),
    [scenarioLibrary],
  );

  return {
    graphScenarios,
    handleOpenScenario,
    handleStartBuilding,
    isDraftWorkspace,
    pendingSeed,
    scenarioAccess,
    scenarioListResolved,
    scenariosResolved,
    searchQuery,
    selectedNamespace,
    selectedTags,
    setSearchQuery,
    setSelectedNamespace,
    setSelectedTags,
    setTagsOpen,
    tagsOpen,
  };
}
