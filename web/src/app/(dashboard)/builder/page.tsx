"use client";

import "@xyflow/react/dist/style.css";

import { ReactFlowProvider } from "@xyflow/react";
import { useAvailableProviders, useFeatures, useScenarios, useTenant } from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";
import { buildSpeechCapabilitiesFromAvailableProviders } from "@/lib/provider-availability";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { AccessPanel } from "@/components/auth/access-panel";

import { useBuilderPageRouteState } from "./hooks/useBuilderPageRouteState";
import { BuilderLandingShell } from "./_components/BuilderLandingShell";
import { BuilderWorkspace } from "./_components/BuilderWorkspace";

function BuilderPageInner() {
  const searchParams = useSearchParams();
  const scenarioIdParam = searchParams.get("id");
  const isDraftStart = searchParams.get("new") === "1";

  const { data: tenant } = useTenant();
  const { data: features } = useFeatures();
  const { data: availableProvidersResponse } = useAvailableProviders();
  const { data: scenarioLibrary, error: scenarioLibraryError } = useScenarios();
  const { roleResolved, canUseBuilder } = useDashboardAccess();

  const speechCapabilities = useMemo(
    () =>
      buildSpeechCapabilitiesFromAvailableProviders(
        availableProvidersResponse?.items,
        features?.speech_capabilities,
      ),
    [availableProvidersResponse, features?.speech_capabilities],
  );

  const {
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
  } = useBuilderPageRouteState({
    isDraftStart,
    scenarioIdParam,
    scenarioLibrary,
    scenarioLibraryError,
  });

  if (!roleResolved) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-text-muted">
        Loading builder permissions…
      </div>
    );
  }

  if (!canUseBuilder) {
    return (
      <AccessPanel
        title="Scenario Builder"
        message="The visual builder is restricted to editor role or above."
        backHref="/scenarios"
        backLabel="Back to scenarios"
      />
    );
  }

  if (!scenarioIdParam && !isDraftWorkspace) {
    return (
      <BuilderLandingShell
        graphScenarios={graphScenarios}
        scenariosResolved={scenarioListResolved}
        filters={{
          searchQuery,
          selectedNamespace,
          selectedTags,
          tagsOpen,
        }}
        filterActions={{
          setSearchQuery,
          setSelectedNamespace,
          setSelectedTags,
          setTagsOpen,
        }}
        onStartBuilding={handleStartBuilding}
        onOpenScenario={handleOpenScenario}
      />
    );
  }

  // pendingSeed must be resolved before entering the workspace — undefined means
  // the effect has not yet run (first render on SSR or concurrent re-mount).
  if (pendingSeed === undefined) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-text-muted">
        Preparing builder…
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <BuilderWorkspace
        scenarioId={scenarioIdParam}
        tenantId={tenant?.tenant_id ?? "default-tenant"}
        features={features}
        speechCapabilities={speechCapabilities}
        scenarioLibrary={scenarioLibrary}
        scenariosResolved={scenariosResolved}
        scenarioAccess={scenarioAccess}
        pendingSeed={pendingSeed}
      />
    </ReactFlowProvider>
  );
}

export default function BuilderPage() {
  // Suspense is required because BuilderPageInner calls useSearchParams(),
  // which opts the subtree out of static rendering in Next.js App Router.
  return (
    <Suspense>
      <BuilderPageInner />
    </Suspense>
  );
}
