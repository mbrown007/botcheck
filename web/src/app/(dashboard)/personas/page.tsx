"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useAIScenarios, useAIPersonas, useFeatures } from "@/lib/api";
import { defaultPersonaTemplates } from "@/lib/persona-templates";
import { TableState } from "@/components/ui/table-state";
import { AccessPanel } from "@/components/auth/access-panel";
import { useDashboardAccess } from "@/lib/current-user";
import { PersonaCard } from "./_components/PersonaCard";
import { PersonaEditorDialog } from "./_components/PersonaEditorDialog";
import { PersonaEmptyState } from "./_components/PersonaEmptyState";
import { usePersonaActions } from "./hooks/usePersonaActions";

export default function PersonasPage() {
  const { data: features } = useFeatures();
  const enabled = features?.ai_scenarios_enabled === true;
  const {
    data: personas,
    error: personasError,
    mutate: mutatePersonas,
  } = useAIPersonas(enabled);
  const { data: scenarios } = useAIScenarios(enabled);

  const sortedPersonas = useMemo(
    () =>
      [...(personas ?? [])].sort((left, right) =>
        left.display_name.localeCompare(right.display_name)
      ),
    [personas]
  );

  const {
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
  } = usePersonaActions({
    personas: sortedPersonas,
    mutatePersonas,
  });
  const { roleResolved, canManagePersonas } = useDashboardAccess();

  if (!enabled) {
    return (
      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">Personas</span>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-text-muted">
            Personas are unavailable because AI scenarios are currently disabled for this
            environment.
          </p>
        </CardBody>
      </Card>
    );
  }

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading persona permissions…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canManagePersonas) {
    return (
      <AccessPanel
        title="Personas"
        message="Persona authoring is restricted to admin role or above."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">
            Persona Workspace
          </p>
          <h1 className="text-2xl font-semibold text-text-primary">Reusable caller identities</h1>
          <p className="max-w-3xl text-sm text-text-secondary">
            Personas define who the AI caller is role-playing: name, portrait, tone, and the short
            backstory operators see when building scenarios and reviewing runs.
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-bg-surface px-4 py-3 text-right">
          <p className="text-xs uppercase tracking-wide text-text-muted">Total Personas</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">{sortedPersonas.length}</p>
        </div>
        <Button onClick={() => openCreateDialog()}>New Persona</Button>
      </div>

      {actionError ? (
        <Card className="border-fail-border bg-fail-bg">
          <CardBody>
            <p className="text-sm text-fail">{actionError}</p>
          </CardBody>
        </Card>
      ) : null}
      {actionSuccess ? (
        <Card className="border-pass-border bg-pass-bg">
          <CardBody>
            <p className="text-sm text-pass">{actionSuccess}</p>
          </CardBody>
        </Card>
      ) : null}

      {personasError ? (
        <TableState
          kind="error"
          title="Unable to load personas"
          message={personasError.message}
          columns={1}
        />
      ) : !personas ? (
        <TableState kind="loading" message="Loading personas…" columns={3} rows={3} />
      ) : personas.length === 0 ? (
        <PersonaEmptyState
          onCreateClick={() => openCreateDialog()}
          templates={defaultPersonaTemplates}
          onUseTemplate={openCreateDialog}
        />
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {sortedPersonas.map((persona, index) => (
            <PersonaCard
              key={persona.persona_id}
              persona={persona}
              scenarios={scenarios}
              index={index}
              editingPersonaId={openingPersonaId}
              duplicatingPersonaId={duplicatingPersonaId}
              togglingPersonaId={togglingPersonaId}
              deletingPersonaId={deletingPersonaId}
              onEdit={handleEditPersona}
              onDuplicate={handleDuplicatePersona}
              onToggleActive={handleTogglePersona}
              onDelete={handleDeletePersona}
            />
          ))}
        </div>
      )}

      <PersonaEditorDialog
        open={editorOpen}
        mode={editingPersonaId ? "edit" : "create"}
        initialValues={editorValues}
        savingPersona={savingPersona}
        templates={defaultPersonaTemplates}
        onOpenChange={(open) => {
          if (!open) {
            closeEditor();
            return;
          }
          setEditorOpen(true);
        }}
        onSave={handleSavePersona}
        onCancelEdit={closeEditor}
      />
    </div>
  );
}
