import { useState } from "react";
import type { AIScenarioRecordEditorFormValues } from "@/lib/schemas/ai-scenario-editor";
import { createAIScenarioRecord, deleteAIScenarioRecord } from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { aiScenarioRecordFormValuesToPayload } from "@/lib/schemas/ai-scenario-editor";

interface UseAIScenarioRecordActionsParams {
  selectedAIScenarioId: string | null;
  mutateSelectedRecords: () => Promise<unknown>;
  mutateAIScenarios: () => Promise<unknown>;
}

export function useAIScenarioRecordActions({
  selectedAIScenarioId,
  mutateSelectedRecords,
  mutateAIScenarios,
}: UseAIScenarioRecordActionsParams) {
  const [creatingRecord, setCreatingRecord] = useState(false);
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  async function handleCreateRecord(values: AIScenarioRecordEditorFormValues) {
    if (!selectedAIScenarioId) {
      setActionError("Select an AI scenario first.");
      setActionSuccess("");
      return false;
    }
    setCreatingRecord(true);
    setActionError("");
    setActionSuccess("");
    try {
      await createAIScenarioRecord(selectedAIScenarioId, aiScenarioRecordFormValuesToPayload(values));
      await Promise.all([mutateSelectedRecords(), mutateAIScenarios()]);
      setActionSuccess("Record created.");
      return true;
    } catch (err) {
      setActionError(mapApiError(err, "Failed to create record").message);
      return false;
    } finally {
      setCreatingRecord(false);
    }
  }

  async function handleDeleteRecord(recordId: string) {
    if (!selectedAIScenarioId) {
      return;
    }
    if (!window.confirm("Delete this record?")) {
      return;
    }
    setDeletingRecordId(recordId);
    setActionError("");
    setActionSuccess("");
    try {
      await deleteAIScenarioRecord(selectedAIScenarioId, recordId);
      await Promise.all([mutateSelectedRecords(), mutateAIScenarios()]);
      setActionSuccess("Record deleted.");
    } catch (err) {
      setActionError(mapApiError(err, "Failed to delete record").message);
    } finally {
      setDeletingRecordId((current) => (current === recordId ? null : current));
    }
  }

  return {
    creatingRecord,
    deletingRecordId,
    actionError,
    actionSuccess,
    handleCreateRecord,
    handleDeleteRecord,
  };
}
