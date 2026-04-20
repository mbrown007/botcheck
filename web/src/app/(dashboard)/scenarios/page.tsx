"use client";

import { useMemo, useState } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  Edit3,
  Eye,
  FolderTree,
  Hammer,
  RefreshCw,
  Search,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import {
  deleteScenario,
  rebuildScenarioCache,
  useFeatures,
  useScenarios,
} from "@/lib/api";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { UploadDialog } from "@/components/scenarios/upload-dialog";
import { GenerateWizard } from "@/components/scenarios/generate-wizard";
import { ScenarioEditDialog } from "@/components/scenarios/edit-dialog";
import { ScenarioViewDialog } from "@/components/scenarios/view-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TableState } from "@/components/ui/table-state";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cacheStatusVariant } from "@/lib/cache-status";
import { useDashboardAccess } from "@/lib/current-user";
import { NamespacePath } from "@/components/scenarios/namespace-path";
import {
  buildScenarioNamespaceTree,
  collectScenarioTags,
  filterScenarioCatalog,
} from "@/lib/scenario-catalog";

export default function ScenariosPage() {
  const router = useRouter();
  const { data: scenarios, error, mutate } = useScenarios();
  const { data: features } = useFeatures();
  const visibleScenarios = scenarios?.filter((scenario) => scenario.scenario_kind !== "ai") ?? [];
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagsOpen, setTagsOpen] = useState(false);
  const [namespaceOpen, setNamespaceOpen] = useState(false);
  const [filtersCollapsed, setFiltersCollapsed] = useState(false);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [rebuildingId, setRebuildingId] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [actionError, setActionError] = useState<string>("");
  const {
    canGenerateScenarios,
    canManageScenarios,
    canUseBuilder,
  } = useDashboardAccess();

  const namespaceNodes = useMemo(
    () => buildScenarioNamespaceTree(visibleScenarios),
    [visibleScenarios]
  );
  const namespaceScopedScenarios = useMemo(
    () =>
      filterScenarioCatalog(visibleScenarios, {
        namespacePath: selectedNamespace,
        searchQuery: "",
        selectedTags: [],
      }),
    [selectedNamespace, visibleScenarios]
  );
  const availableTags = useMemo(
    () => collectScenarioTags(namespaceScopedScenarios),
    [namespaceScopedScenarios]
  );
  const visibleTagOptions = useMemo(
    () =>
      Array.from(new Set([...selectedTags, ...availableTags])).sort((a, b) =>
        a.localeCompare(b)
      ),
    [availableTags, selectedTags]
  );
  const filteredScenarios = useMemo(
    () =>
      filterScenarioCatalog(visibleScenarios, {
        namespacePath: selectedNamespace,
        searchQuery,
        selectedTags,
      }),
    [searchQuery, selectedNamespace, selectedTags, visibleScenarios]
  );
  const viewingScenario =
    filteredScenarios.find((s) => s.id === viewingId) ??
    visibleScenarios.find((s) => s.id === viewingId) ??
    null;
  const hasActiveFilters =
    Boolean(selectedNamespace) ||
    searchQuery.trim().length > 0 ||
    selectedTags.length > 0;
  const filterSummary = `${filteredScenarios.length} of ${visibleScenarios.length} graph scenarios`;
  const hasUngroupedScenarios = useMemo(
    () => visibleScenarios.some((scenario) => !scenario.namespace),
    [visibleScenarios]
  );
  const hasUngroupedNamespaceNode = useMemo(
    () => namespaceNodes.some((node) => node.path === "__ungrouped__"),
    [namespaceNodes]
  );

  // Label shown on the namespace button when a filter is active
  const selectedNamespaceLabel = useMemo(() => {
    if (!selectedNamespace) return "All namespaces";
    if (selectedNamespace === "__ungrouped__") return "Unscoped";
    const node = namespaceNodes.find((n) => n.path === selectedNamespace);
    return node?.label ?? selectedNamespace;
  }, [selectedNamespace, namespaceNodes]);

  function cacheStatusDetail(status?: string | null): string | null {
    const normalized = (status ?? "cold").toLowerCase();
    if (normalized === "partial") return "Cache incomplete. Rebuild before smoke testing.";
    if (normalized === "cold") return "No prebuilt cache available.";
    if (normalized === "warming") return "Cache rebuild in progress.";
    return null;
  }

  async function handleDelete(scenarioId: string) {
    if (!window.confirm("Delete this scenario? This cannot be undone.")) return;
    setActionError("");
    try {
      await deleteScenario(scenarioId);
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete scenario");
    }
  }

  async function handleRebuildCache(scenarioId: string) {
    setActionError("");
    setRebuildingId(scenarioId);
    try {
      await rebuildScenarioCache(scenarioId);
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to rebuild cache");
    } finally {
      setRebuildingId((prev) => (prev === scenarioId ? null : prev));
    }
  }

  function handleOpenInBuilder(scenarioId: string) {
    setViewingId(null);
    router.push(`/builder?id=${encodeURIComponent(scenarioId)}` as Route);
  }

  function toggleTag(tag: string) {
    setSelectedTags((current) =>
      current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag]
    );
  }

  function clearFilters() {
    setSelectedNamespace(null);
    setSearchQuery("");
    setSelectedTags([]);
  }

  return (
    <div className="space-y-6">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Scenarios</h1>
          <p className="text-sm text-text-secondary mt-0.5">YAML test scenario definitions</p>
          {features && !features.tts_cache_enabled && (
            <p className="text-xs text-warn mt-1">TTS cache is disabled for this deployment.</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canManageScenarios && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="primary" size="md" data-testid="scenario-graph-actions-trigger">
                  <Hammer className="size-4" />
                  Graph scenarios
                  <ChevronDown className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem
                  data-testid="scenario-action-new-graph"
                  onSelect={() => router.push("/builder" as Route)}
                >
                  <Hammer className="size-4" />
                  New graph scenario
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-testid="scenario-action-upload-yaml"
                  onSelect={() => setUploadOpen(true)}
                >
                  <Edit3 className="size-4" />
                  Upload YAML
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {canGenerateScenarios && (
            <Button variant="secondary" size="md" onClick={() => setShowWizard(true)}>
              <Sparkles className="size-4" />
              Generate with AI
            </Button>
          )}
        </div>
      </div>

      {!canManageScenarios && (
        <p className="text-xs text-text-muted">
          Read-only access. Scenario upload, edit, cache rebuild, and delete require editor role or
          above.
        </p>
      )}

      {/* ── Dialogs / wizards ── */}
      {showWizard && canGenerateScenarios && (
        <GenerateWizard
          onClose={() => {
            setShowWizard(false);
            void mutate();
          }}
        />
      )}
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onSuccess={() => mutate()} />
      <ScenarioViewDialog
        scenarioId={viewingId}
        cacheFeatureEnabled={Boolean(features?.tts_cache_enabled)}
        cacheStatus={viewingScenario?.cache_status ?? null}
        cacheUpdatedAt={viewingScenario?.cache_updated_at ?? null}
        onOpenInBuilder={handleOpenInBuilder}
        onClose={() => setViewingId(null)}
      />
      <ScenarioEditDialog
        scenarioId={editingId}
        onClose={() => setEditingId(null)}
        onSuccess={() => mutate()}
      />

      <TooltipProvider delayDuration={120}>
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-text-muted">{filterSummary}</p>
          <div className="flex items-center gap-3">
            {filtersCollapsed && hasActiveFilters ? (
              <button
                type="button"
                data-testid="scenario-catalog-clear-collapsed"
                onClick={clearFilters}
                className="text-xs text-text-muted transition-colors hover:text-text-primary"
              >
                Clear filters
              </button>
            ) : null}
            <button
              type="button"
              data-testid="scenario-catalog-collapse-toggle"
              onClick={() => setFiltersCollapsed((current) => !current)}
              className="text-xs text-text-muted transition-colors hover:text-text-primary"
            >
              {filtersCollapsed ? "Expand filters" : "Collapse filters"}
            </button>
          </div>
        </div>

        {!filtersCollapsed ? (
        <>
        {/* ── Filter toolbar ── */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative min-w-[200px] flex-1 max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
            <input
              id="scenario-search-input"
              data-testid="scenario-search-input"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search name, id, namespace, tags…"
              className="w-full rounded-md border border-border bg-bg-surface py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
            />
          </div>

          <Button
            variant="secondary"
            size="md"
            data-testid="scenario-catalog-toggle-namespaces"
            onClick={() => setNamespaceOpen((current) => !current)}
            className={selectedNamespace ? "border-brand text-text-primary" : ""}
          >
            <FolderTree className="size-4" />
            {selectedNamespaceLabel}
            <ChevronDown className={`size-4 transition-transform ${namespaceOpen ? "rotate-180" : ""}`} />
          </Button>

          {/* Tags multi-select dropdown */}
          <DropdownMenu open={tagsOpen} onOpenChange={setTagsOpen} modal={false}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="secondary"
                size="md"
                data-testid="scenario-catalog-toggle-tags"
                className={selectedTags.length > 0 ? "border-brand text-text-primary" : ""}
              >
                <Tag className="size-4" />
                Tags
                {selectedTags.length > 0 && (
                  <span className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-brand text-[10px] font-medium text-white">
                    {selectedTags.length}
                  </span>
                )}
                <ChevronDown className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-52">
              {visibleTagOptions.length === 0 ? (
                <p className="px-3 py-2 text-sm text-text-muted">
                  No tags available for this namespace.
                </p>
              ) : (
                visibleTagOptions.map((tag) => {
                  const active = selectedTags.includes(tag);
                  return (
                    <DropdownMenuItem
                      key={tag}
                      data-testid={`scenario-tag-${tag}`}
                      onSelect={(e) => {
                        e.preventDefault();
                        toggleTag(tag);
                      }}
                      className="flex items-center gap-2"
                    >
                      <span className={`flex-1 ${active ? "font-medium text-text-primary" : ""}`}>
                        #{tag}
                      </span>
                      {active && <Check className="size-3.5 text-brand" />}
                    </DropdownMenuItem>
                  );
                })
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Active filter chips */}
          {hasActiveFilters && (
            <div className="flex flex-wrap items-center gap-1.5">
              {selectedNamespace && (
                <button
                  type="button"
                  onClick={() => setSelectedNamespace(null)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs text-text-primary transition-colors hover:bg-brand/20"
                >
                  <FolderTree className="size-3" />
                  <NamespacePath
                    namespace={selectedNamespace === "__ungrouped__" ? null : selectedNamespace}
                    compact
                  />
                  <X className="size-3 text-text-muted" />
                </button>
              )}
              {selectedTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs text-text-primary transition-colors hover:bg-brand/20"
                >
                  #{tag}
                  <X className="size-3 text-text-muted" />
                </button>
              ))}
              {searchQuery.trim() && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-surface"
                >
                  &ldquo;{searchQuery.trim()}&rdquo;
                  <X className="size-3 text-text-muted" />
                </button>
              )}
              <button
                type="button"
                onClick={clearFilters}
                className="text-xs text-text-muted transition-colors hover:text-text-primary"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
        {namespaceOpen ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="scenario-namespace-all"
              onClick={() => setSelectedNamespace(null)}
              className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors ${
                selectedNamespace === null
                  ? "border-brand bg-brand/10 text-text-primary"
                  : "border-border bg-bg-surface text-text-secondary hover:bg-bg-subtle"
              }`}
            >
              <span>All scenarios</span>
              <span className="font-mono text-[10px] text-text-muted">{visibleScenarios.length}</span>
            </button>
            {namespaceNodes.map((node) => (
              <button
                key={node.path}
                type="button"
                data-testid={`scenario-namespace-${node.path}`}
                onClick={() => setSelectedNamespace(node.path)}
                className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors ${
                  selectedNamespace === node.path
                    ? "border-brand bg-brand/10 text-text-primary"
                    : "border-border bg-bg-surface text-text-secondary hover:bg-bg-subtle"
                }`}
              >
                <span>{node.label}</span>
                <span className="font-mono text-[10px] text-text-muted">{node.count}</span>
              </button>
            ))}
            {hasUngroupedScenarios && !hasUngroupedNamespaceNode ? (
              <button
                type="button"
                data-testid="scenario-namespace-__ungrouped__"
                onClick={() => setSelectedNamespace("__ungrouped__")}
                className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors ${
                  selectedNamespace === "__ungrouped__"
                    ? "border-brand bg-brand/10 text-text-primary"
                    : "border-border bg-bg-surface text-text-secondary hover:bg-bg-subtle"
                }`}
              >
                <span>Unscoped</span>
                <span className="font-mono text-[10px] text-text-muted">
                  {visibleScenarios.filter((scenario) => !scenario.namespace).length}
                </span>
              </button>
            ) : null}
          </div>
        ) : null}
        </>
        ) : null}

        {/* ── Scenarios table ── */}
        <Card>
          <CardBody className="p-0">
            {error && (
              <TableState
                kind="error"
                title="Failed to load scenarios"
                message={error.message}
                columns={7}
              />
            )}
            {!scenarios && !error && (
              <TableState kind="loading" message="Loading scenarios…" columns={7} rows={6} />
            )}
            {scenarios && visibleScenarios.length === 0 && (
              <TableState
                kind="empty"
                title="No scenarios yet"
                message="Upload a YAML file to create your first graph scenario."
                columns={7}
              />
            )}
            {scenarios && visibleScenarios.length > 0 && filteredScenarios.length === 0 && (
              <TableState
                kind="empty"
                title="No scenarios match these filters"
                message="Try a broader namespace, remove a tag, or search for a different phrase."
                columns={7}
              />
            )}
            {filteredScenarios.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                    <th className="px-5 py-3 text-left font-medium">Name</th>
                    <th className="px-5 py-3 text-left font-medium">Type</th>
                    <th className="px-5 py-3 text-left font-medium">Turns</th>
                    <th className="px-5 py-3 text-left font-medium hidden lg:table-cell">
                      Version
                    </th>
                    {features?.tts_cache_enabled && (
                      <th className="px-5 py-3 text-left font-medium">Cache</th>
                    )}
                    <th className="px-5 py-3 text-left font-medium hidden xl:table-cell">
                      Created
                    </th>
                    <th className="px-5 py-3 text-right font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredScenarios.map((s) => (
                    <tr
                      key={s.id}
                      className="border-b border-border last:border-0 hover:bg-bg-elevated transition-colors cursor-pointer"
                      onClick={() => setViewingId(s.id)}
                      data-testid={`scenario-row-${s.id}`}
                    >
                      <td className="px-5 py-3">
                        <div className="mb-1">
                          <NamespacePath namespace={s.namespace} compact />
                        </div>
                        <span className="font-mono text-xs text-brand">{s.id}</span>
                        <p className="text-text-primary text-sm">{s.name}</p>
                        {s.tags.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {s.tags.slice(0, 4).map((tag) => (
                              <span
                                key={`${s.id}-${tag}`}
                                className="inline-flex items-center rounded-full border border-border bg-bg-elevated px-2 py-0.5 text-[11px] text-text-secondary"
                              >
                                #{tag}
                              </span>
                            ))}
                            {s.tags.length > 4 && (
                              <span className="inline-flex items-center rounded-full border border-border bg-bg-elevated px-2 py-0.5 text-[11px] text-text-muted">
                                +{s.tags.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <StatusBadge value={s.type} label={s.type} />
                      </td>
                      <td className="px-5 py-3 font-mono text-text-secondary">{s.turns}</td>
                      <td className="px-5 py-3 font-mono text-xs text-text-muted hidden lg:table-cell">
                        {s.version_hash?.slice(0, 12) ?? "—"}
                      </td>
                      {features?.tts_cache_enabled && (
                        <td className="px-5 py-3">
                          <div className="space-y-1">
                            <StatusBadge
                              value={cacheStatusVariant(s.cache_status)}
                              label={s.cache_status ?? "cold"}
                            />
                            {cacheStatusDetail(s.cache_status) && (
                              <p
                                className={
                                  (s.cache_status ?? "").toLowerCase() === "partial"
                                    ? "text-[11px] text-warn"
                                    : "text-[11px] text-text-muted"
                                }
                              >
                                {cacheStatusDetail(s.cache_status)}
                              </p>
                            )}
                          </div>
                        </td>
                      )}
                      <td className="px-5 py-3 text-text-muted text-xs hidden xl:table-cell">
                        {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                      </td>
                      <td
                        className="px-5 py-3 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex justify-end gap-2">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                aria-label="View"
                                variant="secondary"
                                size="icon"
                                onClick={() => setViewingId(s.id)}
                              >
                                <Eye className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                aria-label="Edit"
                                variant="secondary"
                                size="icon"
                                disabled={!canManageScenarios}
                                onClick={() => setEditingId(s.id)}
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Edit</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                aria-label="Open in Builder"
                                variant="secondary"
                                size="icon"
                                disabled={!canUseBuilder}
                                onClick={() => handleOpenInBuilder(s.id)}
                              >
                                <Hammer className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Open in Builder</TooltipContent>
                          </Tooltip>
                          {features?.tts_cache_enabled && canManageScenarios && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  aria-label="Rebuild Cache"
                                  variant={
                                    (s.cache_status ?? "").toLowerCase() === "partial"
                                      ? "primary"
                                      : "secondary"
                                  }
                                  size="icon"
                                  disabled={rebuildingId === s.id}
                                  onClick={() => void handleRebuildCache(s.id)}
                                >
                                  <RefreshCw className="h-3.5 w-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                {rebuildingId === s.id ? "Rebuilding Cache" : "Rebuild Cache"}
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {canManageScenarios && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  aria-label="Delete"
                                  variant="destructive"
                                  size="icon"
                                  onClick={() => void handleDelete(s.id)}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Delete</TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {actionError && (
              <p className="px-5 py-4 text-sm text-fail border-t border-border">{actionError}</p>
            )}
          </CardBody>
        </Card>
      </TooltipProvider>
    </div>
  );
}
