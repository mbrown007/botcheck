"use client";

import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Check, ChevronDown, FolderTree, Search, Tag, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { BotProtocol, ScenarioSummary, ScenarioType } from "@/lib/api";
import {
  BUILDER_DRAFT_TEMPLATE_OPTIONS,
  type BuilderDraftStartMode,
  type BuilderDraftTemplateKey,
} from "@/lib/builder-draft-seed";
import { cn } from "@/lib/utils";
import {
  buildScenarioNamespaceTree,
  collectScenarioTags,
  filterScenarioCatalog,
  scenarioTags,
} from "@/lib/scenario-catalog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { BOT_PROTOCOL_OPTIONS, SCENARIO_TYPE_OPTIONS } from "@/lib/schemas/scenario-meta";
import { NamespacePath } from "@/components/scenarios/namespace-path";

interface BuilderCatalogFilters {
  searchQuery: string;
  selectedNamespace: string | null;
  selectedTags: string[];
  tagsOpen: boolean;
}

interface BuilderCatalogFilterActions {
  setSearchQuery: (value: string) => void;
  setSelectedNamespace: (value: string | null) => void;
  setSelectedTags: (value: string[]) => void;
  setTagsOpen: (open: boolean) => void;
}

interface BuilderLandingShellProps {
  graphScenarios: ScenarioSummary[];
  scenariosResolved: boolean;
  filters: BuilderCatalogFilters;
  filterActions: BuilderCatalogFilterActions;
  onStartBuilding: (seed: {
    name: string;
    type?: ScenarioType;
    botProtocol?: BotProtocol;
    templateKey: BuilderDraftTemplateKey;
    startMode: BuilderDraftStartMode;
  }) => void;
  onOpenScenario: (scenarioId: string) => void;
}

export function BuilderLandingShell({
  graphScenarios,
  scenariosResolved,
  filters,
  filterActions,
  onStartBuilding,
  onOpenScenario,
}: BuilderLandingShellProps) {
  const [name, setName] = useState("");
  const [type, setType] = useState<ScenarioType | "">("");
  const [botProtocol, setBotProtocol] = useState<BotProtocol | "">("");
  const [templateKey, setTemplateKey] = useState<BuilderDraftTemplateKey>("blank");
  const [startMode, setStartMode] = useState<BuilderDraftStartMode>("caller_opens");
  const trimmedName = name.trim();
  const { searchQuery, selectedNamespace, selectedTags, tagsOpen } = filters;
  const { setSearchQuery, setSelectedNamespace, setSelectedTags, setTagsOpen } = filterActions;

  const namespaceNodes = useMemo(
    () => buildScenarioNamespaceTree(graphScenarios),
    [graphScenarios],
  );
  const namespaceScopedScenarios = useMemo(
    () =>
      filterScenarioCatalog(graphScenarios, {
        namespacePath: selectedNamespace,
        searchQuery: "",
        selectedTags: [],
      }),
    [graphScenarios, selectedNamespace],
  );
  const availableTags = useMemo(
    () => collectScenarioTags(namespaceScopedScenarios),
    [namespaceScopedScenarios],
  );
  const visibleTagOptions = useMemo(
    () =>
      Array.from(new Set([...selectedTags, ...availableTags])).sort((a, b) =>
        a.localeCompare(b),
      ),
    [availableTags, selectedTags],
  );
  const filteredGraphScenarios = useMemo(
    () =>
      filterScenarioCatalog(graphScenarios, {
        namespacePath: selectedNamespace,
        searchQuery,
        selectedTags,
      }),
    [graphScenarios, searchQuery, selectedNamespace, selectedTags],
  );
  const hasActiveOpenFilters =
    Boolean(selectedNamespace) ||
    searchQuery.trim().length > 0 ||
    selectedTags.length > 0;
  const visibleOpenResults = filteredGraphScenarios.slice(0, 6);

  const selectedNamespaceLabel = useMemo(() => {
    if (!selectedNamespace) return "All namespaces";
    if (selectedNamespace === "__ungrouped__") return "Unscoped";
    return namespaceNodes.find((n) => n.path === selectedNamespace)?.label ?? selectedNamespace;
  }, [selectedNamespace, namespaceNodes]);

  function clearOpenFilters() {
    setSearchQuery("");
    setSelectedNamespace(null);
    setSelectedTags([]);
  }

  function toggleTag(tag: string) {
    setSelectedTags(
      selectedTags.includes(tag)
        ? selectedTags.filter((currentTag) => currentTag !== tag)
        : [...selectedTags, tag],
    );
  }

  return (
    <div
      data-testid="builder-landing-shell"
      className="flex min-h-[calc(100vh-7rem)] flex-col gap-6"
    >
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-text-primary">Scenario Builder</h1>
        <p className="max-w-3xl text-sm text-text-secondary">
          Start a new graph scenario or open an existing one. This landing page stays
          lightweight until you enter the full visual editor.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        {/* ── Create new ── */}
        <section
          data-testid="builder-landing-create-panel"
          className="rounded-lg border border-border bg-bg-surface p-6 shadow-sm"
        >
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Create New
            </p>
            <h2 className="text-lg font-semibold text-text-primary">New graph scenario</h2>
            <p className="text-sm text-text-secondary">
              Name is the only required field. Type and template are optional seed hints
              that prefill the draft without becoming save-time validation gates.
            </p>
          </div>

          <div className="mt-5 grid gap-4">
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                Scenario name
              </span>
              <input
                data-testid="builder-landing-name-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Billing escalation smoke"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
              />
            </label>

            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                Scenario type
              </span>
              <select
                data-testid="builder-landing-type-select"
                value={type}
                onChange={(e) => setType(e.target.value as ScenarioType | "")}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="">Use draft default</option>
                {SCENARIO_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                Quick-start template
              </span>
              <select
                data-testid="builder-landing-template-select"
                value={templateKey}
                onChange={(e) => setTemplateKey(e.target.value as BuilderDraftTemplateKey)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                {BUILDER_DRAFT_TEMPLATE_OPTIONS.map((template) => (
                  <option key={template.key} value={template.key}>{template.label}</option>
                ))}
              </select>
              <p className="text-xs text-text-muted">
                {BUILDER_DRAFT_TEMPLATE_OPTIONS.find((t) => t.key === templateKey)?.description}
              </p>
            </label>

            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                Opening move
              </span>
              <select
                data-testid="builder-landing-start-mode-select"
                value={startMode}
                onChange={(e) => setStartMode(e.target.value as BuilderDraftStartMode)}
                disabled={templateKey !== "blank"}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="caller_opens">Caller opens immediately</option>
                <option value="bot_opens">Wait for bot greeting first</option>
              </select>
              <p className="text-xs text-text-muted">
                {templateKey === "blank"
                  ? "Choose whether the harness speaks first or listens for the bot on answer."
                  : "Templates control their own opening flow. Switch back to Blank draft to choose the opening move."}
              </p>
            </label>

            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-text-muted">
                Bot protocol
              </span>
              <select
                data-testid="builder-landing-protocol-select"
                value={botProtocol}
                onChange={(e) => setBotProtocol(e.target.value as BotProtocol | "")}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="">Use template default</option>
                {BOT_PROTOCOL_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <p className="text-xs text-text-muted">
                Optional seed hint for the draft bot connection.
              </p>
            </label>
          </div>

          <div className="mt-6">
            <Button
              type="button"
              size="md"
              data-testid="builder-landing-start-btn"
              onClick={() =>
                onStartBuilding({
                  name: trimmedName,
                  type: type || undefined,
                  botProtocol: botProtocol || undefined,
                  templateKey,
                  startMode,
                })
              }
              disabled={!trimmedName}
            >
              Start building
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </section>

        {/* ── Open existing ── */}
        <section
          data-testid="builder-landing-open-panel"
          className="rounded-lg border border-border bg-bg-surface p-6 shadow-sm"
        >
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
              Open Existing
            </p>
            <h2 className="text-lg font-semibold text-text-primary">Resume a graph scenario</h2>
            <p className="text-sm text-text-secondary">
              Search the shared catalog by namespace, tags, and free text without leaving
              the builder flow.
            </p>
          </div>

          {scenariosResolved ? (
            <div className="mt-5 space-y-4">
              {/* Filter toolbar */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Search */}
                <div className="relative min-w-0 flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-muted" />
                  <input
                    id="builder-open-scenario-search"
                    data-testid="builder-landing-open-search-input"
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search name, id, namespace, tags…"
                    className="w-full rounded-md border border-border bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
                  />
                </div>

                {/* Tags multi-select dropdown */}
                <DropdownMenu open={tagsOpen} onOpenChange={setTagsOpen} modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="secondary"
                      size="md"
                      data-testid="builder-landing-open-toggle-tags"
                      className={cn(selectedTags.length > 0 && "border-brand text-text-primary")}
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
                            data-testid={`builder-landing-open-tag-${tag}`}
                            onSelect={(e) => {
                              e.preventDefault();
                              toggleTag(tag);
                            }}
                            className="flex items-center gap-2"
                          >
                            <span className={cn("flex-1", active && "font-medium text-text-primary")}>
                              #{tag}
                            </span>
                            {active && <Check className="size-3.5 text-brand" />}
                          </DropdownMenuItem>
                        );
                      })
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  data-testid="builder-landing-open-namespace-all"
                  onClick={() => setSelectedNamespace(null)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors",
                    !selectedNamespace
                      ? "border-brand bg-brand/10 text-text-primary"
                      : "border-border bg-bg-elevated text-text-secondary hover:bg-bg-subtle",
                  )}
                >
                  <FolderTree className="size-3.5" />
                  <span>All namespaces</span>
                  <span className="font-mono text-[10px] text-text-muted">{graphScenarios.length}</span>
                </button>
                {namespaceNodes.map((node) => (
                  <button
                    key={node.path}
                    type="button"
                    data-testid={`builder-landing-open-namespace-${node.path.replaceAll("/", "__")}`}
                    onClick={() => setSelectedNamespace(node.path)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors",
                      selectedNamespace === node.path
                        ? "border-brand bg-brand/10 text-text-primary"
                        : "border-border bg-bg-elevated text-text-secondary hover:bg-bg-subtle",
                    )}
                    style={{ marginLeft: `${node.depth * 12}px` }}
                  >
                    <span>{node.label}</span>
                    <span className="font-mono text-[10px] text-text-muted">{node.count}</span>
                  </button>
                ))}
              </div>

              {/* Active filter chips */}
              {hasActiveOpenFilters && (
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
                    data-testid="builder-landing-open-clear-filters"
                    onClick={clearOpenFilters}
                    className="text-xs text-text-muted transition-colors hover:text-text-primary"
                  >
                    Clear all
                  </button>
                </div>
              )}

              {/* Results */}
              <div className="rounded-md border border-border bg-bg-elevated">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-text-primary">
                      {filteredGraphScenarios.length} matching graph scenarios
                    </p>
                    <p className="text-xs text-text-muted">
                      Open directly in the builder workspace.
                    </p>
                  </div>
                </div>

                {visibleOpenResults.length > 0 ? (
                  <div className="divide-y divide-border">
                    {visibleOpenResults.map((scenario) => (
                      <div
                        key={scenario.id}
                        className="flex items-start justify-between gap-3 px-4 py-3"
                      >
                        <div className="min-w-0 space-y-1">
                          <p className="truncate text-sm font-medium text-text-primary">
                            {scenario.name || scenario.id}
                          </p>
                          <p className="truncate text-xs text-text-muted">{scenario.id}</p>
                          <div className="flex flex-wrap items-center gap-2">
                            <NamespacePath namespace={scenario.namespace} compact />
                            {scenarioTags(scenario).slice(0, 3).map((tag) => (
                              <span
                                key={`${scenario.id}-${tag}`}
                                className="rounded-full border border-border bg-bg-subtle px-2 py-0.5 text-[10px] text-text-muted"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          data-testid={`builder-landing-open-scenario-${scenario.id}`}
                          onClick={() => onOpenScenario(scenario.id)}
                        >
                          Open
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="px-4 py-5 text-sm text-text-secondary">
                    No graph scenarios match the current filters.
                  </div>
                )}
              </div>

              {filteredGraphScenarios.length > visibleOpenResults.length && (
                <p className="text-xs text-text-muted">
                  Showing the first {visibleOpenResults.length} results. Narrow the filters
                  to find a specific scenario faster.
                </p>
              )}
            </div>
          ) : (
            <div className="mt-5 rounded-md border border-dashed border-border px-4 py-4">
              <p className="text-sm text-text-primary">Loading graph scenario inventory…</p>
            </div>
          )}

          <div className="mt-6 flex items-center gap-3">
            <Link
              href={"/scenarios" as Route}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-bg-elevated px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-subtle"
            >
              Browse full catalog
              <ArrowRight className="size-4" />
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
