import { useMemo, useState } from "react";
import {
  useAIScenarioRecords,
  useAIScenarios,
  useAIPersonas,
  useAvailableProviders,
  useFeatures,
} from "@/lib/api";
import {
  buildAIScenarioPersonaNameById,
  countAIScenarioRecords,
  findSelectedAIScenario,
} from "@/lib/ai-scenario-workspace";
import { buildSpeechCapabilitiesFromAvailableProviders } from "@/lib/provider-availability";

export function useAIScenarioWorkspace() {
  const { data: features } = useFeatures();
  const enabled = features?.ai_scenarios_enabled === true;
  const { data: availableProvidersResponse } = useAvailableProviders(enabled);
  const speechCapabilities = useMemo(
    () =>
      buildSpeechCapabilitiesFromAvailableProviders(
        availableProvidersResponse?.items,
        features?.speech_capabilities
      ),
    [availableProvidersResponse, features?.speech_capabilities]
  );
  const { data: personas } = useAIPersonas(enabled);
  const {
    data: scenarios,
    error: scenariosError,
    mutate: mutateAIScenarios,
  } = useAIScenarios(enabled);
  const [selectedAIScenarioId, setSelectedAIScenarioId] = useState<string | null>(null);
  const {
    data: selectedRecords,
    error: selectedRecordsError,
    mutate: mutateSelectedRecords,
  } = useAIScenarioRecords(selectedAIScenarioId, enabled);

  const personaNameById = useMemo(() => buildAIScenarioPersonaNameById(personas), [personas]);

  const personaCount = personas?.length ?? 0;
  const scenarioCount = scenarios?.length ?? 0;
  const totalRecords = useMemo(() => countAIScenarioRecords(scenarios), [scenarios]);
  const selectedScenario = useMemo(
    () => findSelectedAIScenario(scenarios, selectedAIScenarioId),
    [scenarios, selectedAIScenarioId]
  );

  return {
    enabled,
    speechCapabilities,
    personas,
    scenarios,
    scenariosError,
    mutateAIScenarios,
    selectedAIScenarioId,
    setSelectedAIScenarioId,
    selectedRecords,
    selectedRecordsError,
    mutateSelectedRecords,
    personaNameById,
    personaCount,
    scenarioCount,
    totalRecords,
    selectedScenario,
  };
}
