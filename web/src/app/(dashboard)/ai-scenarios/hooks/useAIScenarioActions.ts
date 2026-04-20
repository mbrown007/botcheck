import { useState } from "react";
import type { AIScenarioSummary } from "@/lib/api/types";
import {
  createAIScenario,
  deleteAIScenario,
  deleteScenario,
  getAIScenario,
  updateAIScenario,
  uploadScenario,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import {
  buildAiBackingScenarioId,
  buildAiBackingScenarioYaml,
  deriveAiScenarioPublicId,
} from "@/lib/ai-scenario-authoring";
import {
  aiScenarioFormValuesToPayload,
  aiScenarioToFormValues,
  type AIScenarioEditorFormValues,
} from "@/lib/schemas/ai-scenario-editor";

interface UseAIScenarioActionsParams {
  mutateAIScenarios: () => Promise<unknown>;
  selectedAIScenarioId: string | null;
  setSelectedAIScenarioId: (value: string | null) => void;
}

export function useAIScenarioActions({
  mutateAIScenarios,
  selectedAIScenarioId,
  setSelectedAIScenarioId,
}: UseAIScenarioActionsParams) {
  const [creatingAIScenario, setCreatingAIScenario] = useState(false);
  const [editingAIScenarioId, setEditingAIScenarioId] = useState<string | null>(null);
  const [deletingAIScenarioId, setDeletingAIScenarioId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  async function handleCreateAIScenario(values: AIScenarioEditorFormValues) {
    setCreatingAIScenario(true);
    setActionError("");
    setActionSuccess("");
    let backingScenarioId: string | null = null;
    try {
      const payload = aiScenarioFormValuesToPayload(values);
      const publicId = deriveAiScenarioPublicId(payload.name || values.name, payload.ai_scenario_id);
      backingScenarioId = buildAiBackingScenarioId(publicId);
      const backingYaml = buildAiBackingScenarioYaml({
        scenarioId: backingScenarioId,
        name: payload.name || values.name.trim(),
        description: payload.scenario_brief || values.scenarioBrief.trim(),
      });
      await uploadScenario(backingYaml);
      await createAIScenario({
        ...payload,
        ai_scenario_id: publicId,
        scenario_id: backingScenarioId,
      });
      await mutateAIScenarios();
      setSelectedAIScenarioId(publicId);
      setActionSuccess("AI scenario created.");
      return true;
    } catch (err) {
      if (backingScenarioId) {
        try {
          await deleteScenario(backingScenarioId);
        } catch {
          // Best-effort rollback. If this fails, surface the original create error.
        }
      }
      setActionError(mapApiError(err, "Failed to create AI scenario").message);
      return false;
    } finally {
      setCreatingAIScenario(false);
    }
  }

  async function handleDeleteAIScenario(aiScenarioId: string) {
    if (!window.confirm("Delete this AI scenario mapping?")) {
      return;
    }
    setDeletingAIScenarioId(aiScenarioId);
    setActionError("");
    setActionSuccess("");
    try {
      await deleteAIScenario(aiScenarioId);
      await mutateAIScenarios();
      if (selectedAIScenarioId === aiScenarioId) {
        setSelectedAIScenarioId(null);
      }
      setActionSuccess("AI scenario deleted.");
    } catch (err) {
      setActionError(mapApiError(err, "Failed to delete AI scenario").message);
    } finally {
      setDeletingAIScenarioId((current) => (current === aiScenarioId ? null : current));
    }
  }

  async function handleUpdateAIScenario(
    aiScenarioId: string,
    values: AIScenarioEditorFormValues
  ) {
    setEditingAIScenarioId(aiScenarioId);
    setActionError("");
    setActionSuccess("");
    try {
      const current = await getAIScenario(aiScenarioId);
      const payload = aiScenarioFormValuesToPayload(values);
      await updateAIScenario(aiScenarioId, {
        ...payload,
        ai_scenario_id: aiScenarioId,
        scenario_id: current.scenario_id,
      });
      await mutateAIScenarios();
      setSelectedAIScenarioId(aiScenarioId);
      setActionSuccess("AI scenario updated.");
      return true;
    } catch (err) {
      setActionError(mapApiError(err, "Failed to update AI scenario").message);
      return false;
    } finally {
      setEditingAIScenarioId((current) => (current === aiScenarioId ? null : current));
    }
  }

  async function getEditValuesForScenario(
    aiScenarioId: string,
    fallbackScenario?: AIScenarioSummary
  ): Promise<AIScenarioEditorFormValues> {
    try {
      const scenario = await getAIScenario(aiScenarioId);
      return aiScenarioToFormValues(scenario);
    } catch {
      if (fallbackScenario) {
        return aiScenarioToFormValues(fallbackScenario);
      }
      throw new Error("Failed to load AI scenario");
    }
  }

  return {
    creatingAIScenario,
    editingAIScenarioId,
    deletingAIScenarioId,
    actionError,
    actionSuccess,
    handleCreateAIScenario,
    handleUpdateAIScenario,
    handleDeleteAIScenario,
    getEditValuesForScenario,
  };
}
