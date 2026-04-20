"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import { AIScenarioCatalogTable } from "./_components/AIScenarioCatalogTable";
import { AIScenarioCreateWizard } from "./_components/AIScenarioCreateWizard";
import { AIScenarioDetailPanel } from "./_components/AIScenarioDetailPanel";
import {
  AIScenarioFilterToolbar,
  type AIScenarioNamespaceOption,
} from "./_components/AIScenarioFilterToolbar";
import { AIScenarioRecordsCard } from "./_components/AIScenarioRecordsCard";
import { useAIScenarioActions } from "./hooks/useAIScenarioActions";
import { useAIScenarioPanels } from "./hooks/useAIScenarioPanels";
import { useAIScenarioRecordActions } from "./hooks/useAIScenarioRecordActions";
import { useAIScenarioWorkspace } from "./hooks/useAIScenarioWorkspace";
import type { AIScenarioEditorFormValues } from "@/lib/schemas/ai-scenario-editor";
import { useDashboardAccess } from "@/lib/current-user";
import { AccessPanel } from "@/components/auth/access-panel";

export default function AIScenariosPage() {
  const [showCreateWizard, setShowCreateWizard] = useState(false);
  const [wizardMode, setWizardMode] = useState<"create" | "edit">("create");
  const [wizardInitialValues, setWizardInitialValues] = useState<AIScenarioEditorFormValues | null>(null);
  const [editingAIScenarioId, setEditingAIScenarioId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);

  const {
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
    selectedScenario,
  } = useAIScenarioWorkspace();
  const {
    detailAIScenarioId,
    detailScenario,
    detailScenarioError,
    toggleDetailAIScenario,
    closeDetailAIScenario,
    toggleRecordAIScenario,
  } = useAIScenarioPanels({
    enabled,
    selectedAIScenarioId,
    onToggleRecords: setSelectedAIScenarioId,
  });

  const {
    creatingAIScenario,
    editingAIScenarioId: savingAIScenarioId,
    deletingAIScenarioId,
    actionError: aiScenarioActionError,
    actionSuccess: aiScenarioActionSuccess,
    handleCreateAIScenario,
    handleUpdateAIScenario,
    handleDeleteAIScenario,
    getEditValuesForScenario,
  } = useAIScenarioActions({
    mutateAIScenarios,
    selectedAIScenarioId,
    setSelectedAIScenarioId,
  });

  const {
    creatingRecord,
    deletingRecordId,
    actionError: recordActionError,
    actionSuccess: recordActionSuccess,
    handleCreateRecord,
    handleDeleteRecord,
  } = useAIScenarioRecordActions({
    selectedAIScenarioId,
    mutateSelectedRecords,
    mutateAIScenarios,
  });

  const { roleResolved, canManageAIScenarios } = useDashboardAccess();

  const namespaceOptions = useMemo(() => {
    const seen = new Set<string>();
    const opts: AIScenarioNamespaceOption[] = [];
    for (const s of scenarios ?? []) {
      const ns = s.namespace?.trim() || "__ungrouped__";
      if (!seen.has(ns)) {
        seen.add(ns);
        opts.push({ label: ns === "__ungrouped__" ? "Unscoped" : ns, value: ns, count: 0 });
      }
    }
    // Populate counts
    for (const s of scenarios ?? []) {
      const ns = s.namespace?.trim() || "__ungrouped__";
      const opt = opts.find((o) => o.value === ns);
      if (opt) opt.count++;
    }
    return opts.sort((a, b) => a.label.localeCompare(b.label));
  }, [scenarios]);

  const filteredScenarios = useMemo(() => {
    const all = scenarios ?? [];
    const q = searchQuery.trim().toLowerCase();
    return all.filter((s) => {
      if (selectedNamespace) {
        const ns = s.namespace?.trim() || "__ungrouped__";
        if (ns !== selectedNamespace) return false;
      }
      if (q) {
        const haystack = [s.name, s.ai_scenario_id, s.scenario_id, s.namespace ?? ""]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [scenarios, searchQuery, selectedNamespace]);

  const selectedNamespaceLabel = useMemo(() => {
    if (!selectedNamespace) return "All namespaces";
    return namespaceOptions.find((o) => o.value === selectedNamespace)?.label ?? selectedNamespace;
  }, [selectedNamespace, namespaceOptions]);

  const hasActiveFilters = Boolean(selectedNamespace) || searchQuery.trim().length > 0;
  const filterSummary = `${filteredScenarios.length} of ${(scenarios ?? []).length} AI scenarios`;

  if (!enabled) {
    return (
      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">AI Scenarios</span>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-text-muted">
            AI scenarios are currently disabled for this environment.
          </p>
        </CardBody>
      </Card>
    );
  }

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading AI scenario permissions…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canManageAIScenarios) {
    return (
      <AccessPanel
        title="AI Scenarios"
        message="AI scenario authoring is restricted to admin role or above."
      />
    );
  }

  const actionError = recordActionError || aiScenarioActionError;
  const actionSuccess = recordActionSuccess || aiScenarioActionSuccess;

  function openCreateWizard() {
    setWizardMode("create");
    setWizardInitialValues(null);
    setEditingAIScenarioId(null);
    setShowCreateWizard(true);
  }

  function closeWizard(open: boolean) {
    setShowCreateWizard(open);
    if (!open) {
      setWizardMode("create");
      setWizardInitialValues(null);
      setEditingAIScenarioId(null);
    }
  }

  async function handleOpenEditWizard(aiScenarioId: string) {
    const scenario = scenarios?.find((row) => row.ai_scenario_id === aiScenarioId);
    if (!scenario) return;
    setWizardMode("edit");
    setEditingAIScenarioId(aiScenarioId);
    setWizardInitialValues(await getEditValuesForScenario(aiScenarioId, scenario));
    setShowCreateWizard(true);
  }

  async function handleSubmitAIScenario(values: AIScenarioEditorFormValues) {
    if (wizardMode === "edit" && editingAIScenarioId) {
      return handleUpdateAIScenario(editingAIScenarioId, values);
    }
    return handleCreateAIScenario(values);
  }

  return (
    <div className="space-y-6">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">AI Scenarios</h1>
          <p className="mt-0.5 text-sm text-text-secondary">
            Intent-first caller simulations built from personas, scenario briefs, and explicit
            success criteria.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/personas"
            className="inline-flex items-center justify-center rounded-md border border-border bg-bg-elevated px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-base"
          >
            Personas
          </Link>
          <Button onClick={openCreateWizard}>Add AI Scenario</Button>
        </div>
      </div>

      {actionError ? <p className="text-sm text-fail">{actionError}</p> : null}
      {actionSuccess ? <p className="text-sm text-pass">{actionSuccess}</p> : null}

      <AIScenarioCreateWizard
        personas={personas ?? []}
        speechCapabilities={speechCapabilities}
        open={showCreateWizard}
        mode={wizardMode}
        savingAIScenario={
          wizardMode === "edit"
            ? savingAIScenarioId === editingAIScenarioId
            : creatingAIScenario
        }
        initialValues={wizardInitialValues}
        onOpenChange={closeWizard}
        onSubmit={handleSubmitAIScenario}
      />

      <AIScenarioFilterToolbar
        searchQuery={searchQuery}
        selectedNamespace={selectedNamespace}
        selectedNamespaceLabel={selectedNamespaceLabel}
        namespaceOptions={namespaceOptions}
        totalScenarios={(scenarios ?? []).length}
        hasActiveFilters={hasActiveFilters}
        filterSummary={filterSummary}
        onSearchQueryChange={setSearchQuery}
        onSelectNamespace={setSelectedNamespace}
        onClearFilters={() => {
          setSearchQuery("");
          setSelectedNamespace(null);
        }}
      />

      {/* ── Table ── */}
      <Card>
        <CardBody className="p-0">
          {scenariosError ? (
            <TableState
              kind="error"
              title="Failed to load AI scenarios"
              message={scenariosError.message}
              columns={7}
            />
          ) : !scenarios ? (
            <TableState kind="loading" message="Loading AI scenarios…" columns={7} rows={6} />
          ) : scenarios.length === 0 ? (
            <TableState
              kind="empty"
              title="No AI scenarios yet"
              message="Create your first AI scenario to start testing role-play caller flows."
              columns={7}
            />
          ) : filteredScenarios.length === 0 ? (
            <TableState
              kind="empty"
              title="No AI scenarios match these filters"
              message="Try a different search term or namespace."
              columns={7}
            />
          ) : (
            <AIScenarioCatalogTable
              scenarios={filteredScenarios}
              personaNameById={personaNameById}
              selectedAIScenarioId={selectedAIScenarioId}
              detailAIScenarioId={detailAIScenarioId}
              deletingAIScenarioId={deletingAIScenarioId}
              editingAIScenarioId={savingAIScenarioId}
              onViewAIScenario={toggleDetailAIScenario}
              onEditAIScenario={(aiScenarioId) => void handleOpenEditWizard(aiScenarioId)}
              onToggleRecords={toggleRecordAIScenario}
              onDeleteAIScenario={(aiScenarioId) => void handleDeleteAIScenario(aiScenarioId)}
            />
          )}
        </CardBody>
      </Card>

      {detailAIScenarioId && !detailScenario && !detailScenarioError ? (
        <Card>
          <CardHeader>
            <span className="text-sm font-medium text-text-secondary">Scenario Detail</span>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-text-muted">Loading AI scenario detail…</p>
          </CardBody>
        </Card>
      ) : null}

      {detailAIScenarioId && detailScenarioError ? (
        <Card>
          <CardHeader>
            <span className="text-sm font-medium text-text-secondary">Scenario Detail</span>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-fail">{detailScenarioError.message}</p>
          </CardBody>
        </Card>
      ) : null}

      {detailScenario ? (
        <AIScenarioDetailPanel
          scenario={detailScenario}
          speechCapabilities={speechCapabilities}
          personaName={personaNameById.get(detailScenario.persona_id) ?? detailScenario.persona_id}
          onClose={closeDetailAIScenario}
        />
      ) : null}

      {selectedAIScenarioId ? (
        <AIScenarioRecordsCard
          selectedAIScenarioId={selectedAIScenarioId}
          selectedScenarioName={selectedScenario?.name ?? selectedAIScenarioId}
          creatingRecord={creatingRecord}
          deletingRecordId={deletingRecordId}
          selectedRecords={selectedRecords}
          selectedRecordsError={selectedRecordsError}
          onCreateRecord={handleCreateRecord}
          onDeleteRecord={(recordId) => void handleDeleteRecord(recordId)}
        />
      ) : null}
    </div>
  );
}
