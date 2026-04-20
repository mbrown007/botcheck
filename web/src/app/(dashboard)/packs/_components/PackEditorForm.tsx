"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  useAIScenarios,
  useFeatures,
  useScenarios,
  type ScenarioPackUpsertRequest,
} from "@/lib/api";
import {
  addScenarioId,
  moveScenarioId,
  parseTagCsv,
  removeScenarioId,
} from "@/lib/pack-editor";
import {
  buildPackCatalogItems,
  buildPackCatalogNamespaceTree,
  filterPackCatalog,
  UNGROUPED_NAMESPACE_PATH,
} from "@/lib/pack-catalog";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

type SelectedPackItem = {
  scenarioId?: string | null;
  aiScenarioId?: string | null;
};

function packItemKey(item: SelectedPackItem): string {
  if (item.aiScenarioId) {
    return `ai:${item.aiScenarioId}`;
  }
  return `graph:${item.scenarioId ?? ""}`;
}

export interface PackEditorInitialValues {
  name: string;
  description: string;
  tags: string[];
  selectedItems: SelectedPackItem[];
}

export function PackEditorForm({
  title,
  subtitle,
  submitLabel,
  initialValues,
  onSubmit,
}: {
  title: string;
  subtitle: string;
  submitLabel: string;
  initialValues: PackEditorInitialValues;
  onSubmit: (payload: ScenarioPackUpsertRequest) => Promise<void>;
}) {
  const { data: scenarios, error: scenariosError } = useScenarios();
  const { data: features } = useFeatures();
  const aiEnabled = features?.ai_scenarios_enabled === true;
  const { data: aiScenarios, error: aiScenariosError } = useAIScenarios(aiEnabled);
  const graphScenarios = useMemo(
    () => (scenarios ?? []).filter((scenario) => scenario.scenario_kind !== "ai"),
    [scenarios]
  );

  const [name, setName] = useState(initialValues.name);
  const [description, setDescription] = useState(initialValues.description);
  const [tagsCsv, setTagsCsv] = useState(initialValues.tags.join(", "));
  const [selectedItems, setSelectedItems] = useState(initialValues.selectedItems);
  const [query, setQuery] = useState("");
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setName(initialValues.name);
    setDescription(initialValues.description);
    setTagsCsv(initialValues.tags.join(", "));
    setSelectedItems(initialValues.selectedItems);
    setSelectedNamespace(null);
  }, [initialValues]);

  const scenarioById = useMemo(() => {
    const mapping = new Map<string, string>();
    for (const scenario of graphScenarios) {
      mapping.set(scenario.id, scenario.name);
    }
    return mapping;
  }, [graphScenarios]);

  const aiScenarioByPublicId = useMemo(() => {
    const mapping = new Map<string, NonNullable<typeof aiScenarios>[number]>();
    for (const scenario of aiScenarios ?? []) {
      mapping.set(scenario.ai_scenario_id, scenario);
    }
    return mapping;
  }, [aiScenarios]);

  const aiScenarioIdSet = useMemo(
    () => new Set((aiScenarios ?? []).map((s) => s.ai_scenario_id)),
    [aiScenarios]
  );

  const selectedScenarioIds = useMemo(
    () =>
      selectedItems
        .map((item) => item.scenarioId)
        .filter((value): value is string => typeof value === "string" && value.length > 0),
    [selectedItems]
  );
  const selectedKeys = useMemo(
    () => new Set(selectedItems.map((item) => packItemKey(item))),
    [selectedItems]
  );

  const availableGraphScenarios = useMemo(() => {
    const selected = new Set(selectedScenarioIds);
    return graphScenarios.filter((scenario) => {
      if (selected.has(scenario.id)) {
        return false;
      }
      if (aiScenarioIdSet.has(scenario.id)) {
        return false;
      }
      return true;
    });
  }, [graphScenarios, selectedScenarioIds, aiScenarioIdSet]);

  const availableAIScenarios = useMemo(
    () =>
      (aiScenarios ?? []).filter((scenario) => !selectedKeys.has(`ai:${scenario.ai_scenario_id}`)),
    [aiScenarios, selectedKeys]
  );

  const availableCatalogItems = useMemo(
    () => buildPackCatalogItems(availableGraphScenarios, availableAIScenarios),
    [availableAIScenarios, availableGraphScenarios]
  );
  const namespaceNodes = useMemo(
    () => buildPackCatalogNamespaceTree(availableCatalogItems),
    [availableCatalogItems]
  );
  const filteredCatalogItems = useMemo(
    () =>
      filterPackCatalog(availableCatalogItems, {
        namespacePath: selectedNamespace,
        searchQuery: query,
      }),
    [availableCatalogItems, query, selectedNamespace]
  );
  const filteredCatalogKeys = useMemo(
    () => new Set(filteredCatalogItems.map((item) => item.key)),
    [filteredCatalogItems]
  );
  const namespaceScopedCatalogItems = useMemo(
    () =>
      filterPackCatalog(availableCatalogItems, {
        namespacePath: selectedNamespace,
        searchQuery: "",
      }),
    [availableCatalogItems, selectedNamespace]
  );
  const availableGraphScenarioIds = useMemo(
    () =>
      new Set(
        filteredCatalogItems.filter((item) => item.kind === "GRAPH").map((item) => item.id)
      ),
    [filteredCatalogItems]
  );
  const availableAIScenarioIds = useMemo(
    () => new Set(filteredCatalogItems.filter((item) => item.kind === "AI").map((item) => item.id)),
    [filteredCatalogItems]
  );
  const filteredGraphScenarios = useMemo(
    () => availableGraphScenarios.filter((scenario) => availableGraphScenarioIds.has(scenario.id)),
    [availableGraphScenarioIds, availableGraphScenarios]
  );
  const filteredAIScenarios = useMemo(
    () =>
      availableAIScenarios.filter((scenario) =>
        availableAIScenarioIds.has(scenario.ai_scenario_id)
      ),
    [availableAIScenarioIds, availableAIScenarios]
  );
  const selectedNamespaceLabel = useMemo(() => {
    if (!selectedNamespace) {
      return null;
    }
    if (selectedNamespace === UNGROUPED_NAMESPACE_PATH) {
      return "Unscoped";
    }
    return selectedNamespace;
  }, [selectedNamespace]);

  const selectedRows = useMemo(
    () =>
      selectedItems.map((item, index) => {
        const aiScenario = item.aiScenarioId
          ? aiScenarioByPublicId.get(item.aiScenarioId)
          : undefined;
        return {
          scenarioId: item.scenarioId,
          aiScenarioId: item.aiScenarioId ?? null,
          scenarioName:
          aiScenario?.name ??
            (item.scenarioId ? scenarioById.get(item.scenarioId) : undefined) ??
            item.aiScenarioId ??
            item.scenarioId ??
            "unknown",
          scenarioLabel: item.aiScenarioId ?? item.scenarioId ?? "unknown",
          scenarioKind: item.aiScenarioId ? "AI" : "GRAPH",
          orderIndex: index,
        };
      }),
    [aiScenarioByPublicId, scenarioById, selectedItems]
  );

  async function handleSubmit() {
    if (!name.trim()) {
      setError("Pack name is required");
      return;
    }
    if (selectedItems.length === 0) {
      setError("Add at least one scenario to the pack");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        tags: parseTagCsv(tagsCsv),
        execution_mode: "parallel",
        scenario_ids: [],
        items: selectedItems.map((item) => ({
          scenario_id: item.scenarioId ?? null,
          ai_scenario_id: item.aiScenarioId ?? null,
        })),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save pack");
      setSaving(false);
    }
  }

  function handleAddGraphScenario(scenarioId: string) {
    const next = addScenarioId(selectedScenarioIds, scenarioId);
    if (next.length === selectedScenarioIds.length) {
      setError("Scenario is already in the pack");
      return;
    }
    setError("");
    setSelectedItems((current) => [...current, { scenarioId }]);
  }

  function handleAddAIScenario(aiScenarioId: string) {
    const scenario = aiScenarioByPublicId.get(aiScenarioId);
    if (!scenario) {
      setError("AI scenario is unavailable");
      return;
    }
    if (selectedKeys.has(`ai:${scenario.ai_scenario_id}`)) {
      setError("Scenario is already in the pack");
      return;
    }
    setError("");
    setSelectedItems((current) => [
      ...current,
      { aiScenarioId: scenario.ai_scenario_id },
    ]);
  }

  function handleMove(itemKey: string, direction: -1 | 1) {
    setSelectedItems((current) => {
      const movedIds = moveScenarioId(
        current.map((item) => packItemKey(item)),
        itemKey,
        direction
      );
      return movedIds.map((movedId) => current.find((item) => packItemKey(item) === movedId)!);
    });
  }

  function handleRemove(itemKey: string) {
    setSelectedItems((current) => {
      const nextIds = removeScenarioId(
        current.map((item) => packItemKey(item)),
        itemKey
      );
      return nextIds.map((nextId) => current.find((item) => packItemKey(item) === nextId)!);
    });
  }

  function handleAddAllFromNamespace() {
    if (!selectedNamespace || namespaceScopedCatalogItems.length === 0) {
      return;
    }
    setError("");
    setSelectedItems((current) => [
      ...current,
      ...namespaceScopedCatalogItems.map((item) =>
        item.kind === "AI" ? { aiScenarioId: item.id } : { scenarioId: item.id }
      ),
    ]);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
          <p className="text-sm text-text-secondary mt-0.5">{subtitle}</p>
        </div>
        <Link
          href="/packs"
          className="inline-flex h-9 items-center justify-center rounded-md border border-border bg-bg-elevated px-4 text-sm font-medium text-text-primary transition-colors hover:bg-bg-subtle"
        >
          Back to Packs
        </Link>
      </div>

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">Pack Metadata</span>
        </CardHeader>
        <CardBody className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Security Regression Pack"
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">Description</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional summary of this pack's purpose"
              rows={3}
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">
              Tags (comma-separated)
            </span>
            <input
              value={tagsCsv}
              onChange={(event) => setTagsCsv(event.target.value)}
              placeholder="security, regression, nightly"
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
          </label>
        </CardBody>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <span className="text-sm font-medium text-text-secondary">Add Scenarios</span>
          </CardHeader>
          <CardBody className="space-y-3">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <label className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                  Namespace
                </label>
                {selectedNamespace ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => setSelectedNamespace(null)}
                  >
                    Clear
                  </Button>
                ) : null}
              </div>
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border bg-bg-elevated/60 p-2 pr-1">
                <button
                  type="button"
                  data-testid="pack-namespace-option-all"
                  onClick={() => setSelectedNamespace(null)}
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                    selectedNamespace === null
                      ? "bg-accent/15 text-text-primary"
                      : "text-text-secondary hover:bg-bg-subtle hover:text-text-primary"
                  }`}
                >
                  <span>All namespaces</span>
                  <span className="text-xs text-text-muted">{availableCatalogItems.length}</span>
                </button>
                {namespaceNodes.map((node) => (
                  <button
                    key={node.path}
                    type="button"
                    data-testid={`pack-namespace-option-${node.path}`}
                    onClick={() => setSelectedNamespace(node.path)}
                    className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                      selectedNamespace === node.path
                        ? "bg-accent/15 text-text-primary"
                        : "text-text-secondary hover:bg-bg-subtle hover:text-text-primary"
                    }`}
                    style={{ paddingLeft: `${0.5 + node.depth * 0.75}rem` }}
                  >
                    <span className="truncate">{node.label}</span>
                    <span className="text-xs text-text-muted">{node.count}</span>
                  </button>
                ))}
              </div>
            </div>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by scenario name, id, namespace, or tag"
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
            {selectedNamespace && namespaceScopedCatalogItems.length > 0 ? (
              <div className="rounded-md border border-border bg-bg-elevated/70 px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-text-primary">
                      {selectedNamespace === UNGROUPED_NAMESPACE_PATH
                        ? "Unscoped scenarios"
                        : selectedNamespaceLabel}
                    </p>
                    <p className="text-[11px] text-text-muted">
                      Add all remaining scenarios from this namespace in one action.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    data-testid="pack-add-all-from-namespace"
                    onClick={handleAddAllFromNamespace}
                  >
                    Add all from namespace ({namespaceScopedCatalogItems.length})
                  </Button>
                </div>
              </div>
            ) : null}
            {scenariosError ? (
              <p className="text-xs text-fail">
                Failed to load scenarios: {scenariosError.message}
              </p>
            ) : null}
            {aiScenariosError ? (
              <p className="text-xs text-fail">
                Failed to load AI scenarios: {aiScenariosError.message}
              </p>
            ) : null}
            {!scenarios && !scenariosError ? (
              <p className="text-xs text-text-muted">Loading scenarios…</p>
            ) : null}
            {scenarios &&
            filteredGraphScenarios.length === 0 &&
            (!aiEnabled || (aiScenarios && filteredAIScenarios.length === 0)) ? (
              <p className="text-xs text-text-muted">
                {query ? "No scenarios match this search." : "All scenarios are already added."}
              </p>
            ) : null}

            {filteredGraphScenarios.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  Graph Scenarios
                </p>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                  {filteredGraphScenarios.map((scenario) => (
                    <div
                      key={scenario.id}
                      data-testid={`pack-scenario-option-${scenario.id}`}
                      className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg-elevated px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm text-text-primary">{scenario.name}</p>
                          <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-muted">
                            GRAPH
                          </span>
                        </div>
                        {scenario.namespace ? (
                          <p className="truncate text-[11px] uppercase tracking-[0.14em] text-text-muted">
                            {scenario.namespace}
                          </p>
                        ) : null}
                        <p className="truncate font-mono text-[11px] text-text-muted">
                          {scenario.id}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleAddGraphScenario(scenario.id)}
                      >
                        Add
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {aiEnabled && filteredAIScenarios.length > 0 ? (
              <div className="space-y-2">
                <p className="pt-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                  AI Scenarios
                </p>
                <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                  {filteredAIScenarios.map((scenario) => (
                    <div
                      key={scenario.ai_scenario_id}
                      data-testid={`pack-scenario-option-${scenario.ai_scenario_id}`}
                      className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg-elevated px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm text-text-primary">{scenario.name}</p>
                          <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-muted">
                            AI
                          </span>
                        </div>
                        {scenario.namespace ? (
                          <p className="truncate text-[11px] uppercase tracking-[0.14em] text-text-muted">
                            {scenario.namespace}
                          </p>
                        ) : null}
                        <p className="truncate font-mono text-[11px] text-text-muted">
                          {scenario.ai_scenario_id}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleAddAIScenario(scenario.ai_scenario_id)}
                      >
                        Add
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <span className="text-sm font-medium text-text-secondary">
              Selected Scenarios ({selectedRows.length})
            </span>
          </CardHeader>
          <CardBody className="space-y-2">
            {selectedRows.length === 0 ? (
              <p className="text-xs text-text-muted">
                Add scenarios from the left panel. You can reorder them for display order.
              </p>
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {selectedRows.map((item) => (
                  <div
                    key={packItemKey(item)}
                    data-testid={`pack-scenario-selected-${item.aiScenarioId ?? item.scenarioId ?? ""}`}
                    className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg-elevated px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm text-text-primary">{item.scenarioName}</p>
                        <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-muted">
                          {item.scenarioKind}
                        </span>
                      </div>
                      <p className="truncate font-mono text-[11px] text-text-muted">
                        {item.scenarioLabel}
                      </p>
                    </div>
                    <div className="inline-flex gap-1">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={item.orderIndex === 0}
                        onClick={() => handleMove(packItemKey(item), -1)}
                      >
                        Up
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={item.orderIndex === selectedRows.length - 1}
                        onClick={() => handleMove(packItemKey(item), 1)}
                      >
                        Down
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleRemove(packItemKey(item))}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {error ? (
        <p className="rounded-md border border-fail-border bg-fail-bg px-3 py-2 text-sm text-fail">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-3">
        <Link
          href="/packs"
          className="inline-flex h-9 items-center justify-center rounded-md border border-border bg-bg-elevated px-4 text-sm font-medium text-text-primary transition-colors hover:bg-bg-subtle"
        >
          Cancel
        </Link>
        <Button variant="primary" disabled={saving} onClick={() => void handleSubmit()}>
          {saving ? "Saving…" : submitLabel}
        </Button>
      </div>
    </div>
  );
}
