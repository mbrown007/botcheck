"use client";

import { useState } from "react";
import {
  createAIPersona,
  getAIPersona,
  deleteAIPersona,
  updateAIPersona,
  type AIPersonaSummary,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { nextPersonaCopyDisplayName, nextPersonaCopyHandle } from "@/lib/persona-copy";
import type { PersonaTemplate } from "@/lib/persona-templates";
import {
  createEmptyPersonaEditorValues,
  personaDetailToFormValues,
  personaFormValuesToPayload,
  personaTemplateToFormValues,
  type PersonaEditorFormValues,
} from "@/lib/schemas/persona-editor";

interface UsePersonaActionsArgs {
  personas: AIPersonaSummary[];
  mutatePersonas: () => Promise<unknown>;
}

export function usePersonaActions({
  personas,
  mutatePersonas,
}: UsePersonaActionsArgs) {
  const [editorValues, setEditorValues] = useState<PersonaEditorFormValues>(
    createEmptyPersonaEditorValues(0)
  );
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPersonaId, setEditingPersonaId] = useState<string | null>(null);
  const [savingPersona, setSavingPersona] = useState(false);
  const [openingPersonaId, setOpeningPersonaId] = useState<string | null>(null);
  const [duplicatingPersonaId, setDuplicatingPersonaId] = useState<string | null>(null);
  const [togglingPersonaId, setTogglingPersonaId] = useState<string | null>(null);
  const [deletingPersonaId, setDeletingPersonaId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  function resetEditor(nextAvatarIndex = 0) {
    setEditingPersonaId(null);
    setEditorValues(createEmptyPersonaEditorValues(nextAvatarIndex));
  }

  function openCreateDialog(template?: PersonaTemplate) {
    if (template) {
      setEditingPersonaId(null);
      setEditorValues(personaTemplateToFormValues(template));
    } else {
      resetEditor(personas.length + 1);
    }
    setActionError("");
    setActionSuccess("");
    setEditorOpen(true);
  }

  function closeEditor() {
    setEditorOpen(false);
    resetEditor(personas.length + 1);
  }

  async function handleSavePersona(values: PersonaEditorFormValues) {
    setSavingPersona(true);
    setActionError("");
    setActionSuccess("");
    try {
      const payload = personaFormValuesToPayload(values);
      if (editingPersonaId) {
        await updateAIPersona(editingPersonaId, payload);
        setActionSuccess("Persona updated.");
      } else {
        await createAIPersona(payload);
        setActionSuccess("Persona created.");
      }
      await mutatePersonas();
      closeEditor();
    } catch (err) {
      setActionError(
        mapApiError(err, editingPersonaId ? "Failed to update persona" : "Failed to create persona")
          .message
      );
    } finally {
      setSavingPersona(false);
    }
  }

  async function handleEditPersona(personaId: string) {
    setOpeningPersonaId(personaId);
    setActionError("");
    setActionSuccess("");
    try {
      const detail = await getAIPersona(personaId);
      setEditingPersonaId(detail.persona_id);
      const fallbackIndex = Math.max(
        0,
        personas.findIndex((persona) => persona.persona_id === personaId)
      );
      setEditorValues(personaDetailToFormValues(detail, fallbackIndex));
      setEditorOpen(true);
    } catch (err) {
      setActionError(mapApiError(err, "Failed to load persona").message);
    } finally {
      setOpeningPersonaId((current) => (current === personaId ? null : current));
    }
  }

  async function handleDuplicatePersona(personaId: string) {
    setDuplicatingPersonaId(personaId);
    setActionError("");
    setActionSuccess("");
    try {
      const detail = await getAIPersona(personaId);
      const nextDisplayName = nextPersonaCopyDisplayName(
        detail.display_name || detail.name,
        personas.map((persona) => persona.display_name)
      );
      await createAIPersona({
        name: nextPersonaCopyHandle(detail.name, personas.map((persona) => persona.name)),
        display_name: nextDisplayName,
        avatar_url: detail.avatar_url,
        backstory_summary: detail.backstory_summary,
        system_prompt: detail.system_prompt,
        style: detail.style,
        voice: detail.voice,
        is_active: detail.is_active,
      });
      await mutatePersonas();
      setActionSuccess("Persona duplicated.");
    } catch (err) {
      setActionError(mapApiError(err, "Failed to duplicate persona").message);
    } finally {
      setDuplicatingPersonaId((current) => (current === personaId ? null : current));
    }
  }

  async function handleTogglePersona(personaId: string, nextActive: boolean) {
    setTogglingPersonaId(personaId);
    setActionError("");
    setActionSuccess("");
    try {
      const detail = await getAIPersona(personaId);
      await updateAIPersona(personaId, {
        name: detail.name,
        display_name: detail.display_name,
        avatar_url: detail.avatar_url,
        backstory_summary: detail.backstory_summary,
        system_prompt: detail.system_prompt,
        style: detail.style,
        voice: detail.voice,
        is_active: nextActive,
      });
      await mutatePersonas();
      if (editingPersonaId === personaId) {
        setEditorValues((current) => ({ ...current, isActive: nextActive }));
      }
      setActionSuccess(nextActive ? "Persona activated." : "Persona deactivated.");
    } catch (err) {
      setActionError(mapApiError(err, "Failed to update persona status").message);
    } finally {
      setTogglingPersonaId((current) => (current === personaId ? null : current));
    }
  }

  async function handleDeletePersona(personaId: string) {
    if (!window.confirm("Delete this persona?")) {
      return;
    }
    setDeletingPersonaId(personaId);
    setActionError("");
    setActionSuccess("");
    try {
      await deleteAIPersona(personaId);
      await mutatePersonas();
      setActionSuccess("Persona deleted.");
    } catch (err) {
      setActionError(mapApiError(err, "Failed to delete persona").message);
    } finally {
      setDeletingPersonaId((current) => (current === personaId ? null : current));
    }
  }

  return {
    editorValues,
    editorOpen,
    editingPersonaId,
    savingPersona,
    openingPersonaId,
    duplicatingPersonaId,
    togglingPersonaId,
    deletingPersonaId,
    actionError,
    actionSuccess,
    setEditorOpen,
    openCreateDialog,
    closeEditor,
    handleSavePersona,
    handleEditPersona,
    handleDuplicatePersona,
    handleTogglePersona,
    handleDeletePersona,
  };
}
