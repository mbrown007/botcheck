import { useState } from "react";
import { useAIScenario } from "@/lib/api";

interface UseAIScenarioPanelsParams {
  enabled: boolean;
  selectedAIScenarioId: string | null;
  onToggleRecords: (id: string | null) => void;
}

export function useAIScenarioPanels({
  enabled,
  selectedAIScenarioId,
  onToggleRecords,
}: UseAIScenarioPanelsParams) {
  const [detailAIScenarioId, setDetailAIScenarioId] = useState<string | null>(null);
  const {
    data: detailScenario,
    error: detailScenarioError,
  } = useAIScenario(detailAIScenarioId, enabled);

  function toggleDetailAIScenario(aiScenarioId: string) {
    setDetailAIScenarioId((current) => (current === aiScenarioId ? null : aiScenarioId));
  }

  function closeDetailAIScenario() {
    setDetailAIScenarioId(null);
  }

  function toggleRecordAIScenario(aiScenarioId: string) {
    onToggleRecords(selectedAIScenarioId === aiScenarioId ? null : aiScenarioId);
  }

  return {
    detailAIScenarioId,
    detailScenario,
    detailScenarioError,
    toggleDetailAIScenario,
    closeDetailAIScenario,
    toggleRecordAIScenario,
  };
}
