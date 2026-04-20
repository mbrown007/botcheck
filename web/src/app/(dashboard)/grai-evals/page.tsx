"use client";

import type { Route } from "next";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ChevronRight,
  FileSearch,
  FlaskConical,
  LoaderCircle,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Upload,
} from "lucide-react";

import {
  availableProviderItems,
  cancelGraiEvalRun,
  createGraiEvalRun,
  createGraiEvalSuite,
  deleteGraiEvalSuite,
  importGraiEvalSuite,
  mapApiError,
  updateGraiEvalSuite,
  useAvailableProviders,
  useFeatures,
  useGraiEvalRun,
  useGraiEvalRunMatrix,
  useGraiEvalRunProgress,
  useGraiEvalRunReport,
  useGraiEvalRunResults,
  useGraiEvalSuite,
  useGraiEvalSuiteRuns,
  useGraiEvalSuites,
  useTransportProfiles,
  type BotDestinationSummary,
  type GraiEvalResultFilters,
  type GraiEvalResultListItem,
  type GraiEvalRunHistorySummary,
  type GraiEvalSuiteDetail,
  type GraiEvalSuiteSummary,
  type GraiEvalSuiteUpsertRequest,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import { TenantProviderAccessCard } from "@/components/providers/tenant-provider-access-card";
import { useDashboardAccess } from "@/lib/current-user";
import { GraiArtifactDialog } from "./_components/GraiArtifactDialog";
import { GraiImportDialog } from "./_components/GraiImportDialog";
import { GraiMatrixCard } from "./_components/GraiMatrixCard";
import { GraiSuiteEditorDialog } from "./_components/GraiSuiteEditorDialog";

function formatTs(value?: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}

function progressPercent(value: number): string {
  return `${Math.max(0, Math.min(100, Math.round(value * 100)))}%`;
}

function suiteAssertionTypes(suite: GraiEvalSuiteDetail | null | undefined): string[] {
  if (!suite) {
    return [];
  }
  const seen = new Set<string>();
  for (const item of suite.cases) {
    for (const assertion of item.assert_json) {
      const value = assertion.assertion_type.trim();
      if (value) {
        seen.add(value);
      }
    }
  }
  return [...seen].sort();
}

function suiteTags(suite: GraiEvalSuiteDetail | null | undefined): string[] {
  if (!suite) {
    return [];
  }
  const seen = new Set<string>();
  for (const item of suite.cases) {
    for (const tag of item.tags_json) {
      const value = tag.trim();
      if (value) {
        seen.add(value);
      }
    }
  }
  return [...seen].sort();
}

function statusTone(status: string): "pass" | "fail" | "warn" | "pending" {
  const normalized = status.trim().toLowerCase();
  if (normalized === "complete") {
    return "pass";
  }
  if (normalized === "failed" || normalized === "cancelled") {
    return "fail";
  }
  if (normalized === "running" || normalized === "pending") {
    return "warn";
  }
  return "pending";
}

function destinationChoices(destinations: BotDestinationSummary[] | undefined): BotDestinationSummary[] {
  return (destinations ?? []).filter(
    (item) => item.protocol === "http" && item.is_active
  );
}

function suiteSearchFilter(items: GraiEvalSuiteSummary[], query: string): GraiEvalSuiteSummary[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return items;
  }
  return items.filter((item) => {
    return (
      item.name.toLowerCase().includes(normalized) ||
      (item.description ?? "").toLowerCase().includes(normalized) ||
      item.suite_id.toLowerCase().includes(normalized)
    );
  });
}

function resultLabel(item: GraiEvalResultListItem): string {
  const destination = item.destination_label || item.transport_profile_id;
  return [
    item.prompt_label,
    item.case_description || item.case_id,
    item.assertion_type,
    destination,
  ]
    .filter(Boolean)
    .join(" · ");
}

function runHistoryDestinationSummary(run: GraiEvalRunHistorySummary): string {
  if (run.destinations.length === 0) {
    return "No destinations recorded";
  }
  const labels = run.destinations.map((item) => item.label || item.transport_profile_id);
  if (labels.length <= 2) {
    return labels.join(" · ");
  }
  return `${labels[0]} + ${labels.length - 1} more`;
}

function runHistoryMeta(run: GraiEvalRunHistorySummary): string {
  return `${run.dispatched_count} dispatched · ${run.completed_count} completed · ${run.failed_count} failed`;
}

export default function GraiEvalsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedSuiteIdParam = searchParams.get("suite");
  const selectedRunIdParam = searchParams.get("run");
  const { roleResolved, canViewGraiEvals, canManageGraiSuites, canLaunchGraiRuns } =
    useDashboardAccess();
  const { data: features } = useFeatures();
  const {
    data: availableProvidersResponse,
    error: availableProvidersError,
  } = useAvailableProviders(canViewGraiEvals);
  const destinationsEnabled = features?.destinations_enabled === true;
  const availableProviders = availableProviderItems(availableProvidersResponse);
  const { data: suites, error: suitesError, mutate: mutateSuites } = useGraiEvalSuites();
  const { data: suiteDetail, error: suiteDetailError } = useGraiEvalSuite(selectedSuiteIdParam);
  const { data: runDetail, error: runDetailError, mutate: mutateRunDetail } = useGraiEvalRun(selectedRunIdParam);
  const { data: runProgress, error: runProgressError, mutate: mutateRunProgress } = useGraiEvalRunProgress(
    selectedRunIdParam,
    Boolean(selectedRunIdParam)
  );
  const { data: matrix, error: matrixError, mutate: mutateMatrix } = useGraiEvalRunMatrix(
    selectedRunIdParam,
    Boolean(selectedRunIdParam)
  );
  const {
    data: suiteRuns,
    error: suiteRunsError,
    mutate: mutateSuiteRuns,
  } = useGraiEvalSuiteRuns(selectedSuiteIdParam, 12);
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const [suiteSearch, setSuiteSearch] = useState("");
  const deferredSuiteSearch = useDeferredValue(suiteSearch);
  const [transportProfileIds, setTransportProfileIds] = useState<string[]>([]);
  const [pageError, setPageError] = useState("");
  const [launchingRun, setLaunchingRun] = useState(false);
  const [cancellingRun, setCancellingRun] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [createError, setCreateError] = useState("");
  const [editError, setEditError] = useState("");
  const [importError, setImportError] = useState("");
  const [savingSuite, setSavingSuite] = useState(false);
  const [deletingSuite, setDeletingSuite] = useState(false);
  const [importingSuite, setImportingSuite] = useState(false);
  const [artifactResultId, setArtifactResultId] = useState<string | null>(null);
  const [resultsCursor, setResultsCursor] = useState<string | null>(null);
  const [resultItems, setResultItems] = useState<GraiEvalResultListItem[]>([]);
  const [reportFilters, setReportFilters] = useState<GraiEvalResultFilters>({
    prompt_id: null,
    assertion_type: null,
    tag: null,
    status: null,
    destination_index: null,
  });
  const { data: report, error: reportError, mutate: mutateReport } = useGraiEvalRunReport(
    selectedRunIdParam,
    reportFilters,
    Boolean(selectedRunIdParam)
  );
  const { data: resultsPage, error: resultsError, mutate: mutateResultsPage } = useGraiEvalRunResults(
    selectedRunIdParam,
    { ...reportFilters, cursor: resultsCursor, limit: 12 },
    Boolean(selectedRunIdParam)
  );

  useEffect(() => {
    if (!suites || suites.length === 0) {
      return;
    }
    if (selectedRunIdParam && runDetail?.suite_id) {
      if (selectedSuiteIdParam !== runDetail.suite_id) {
        const params = new URLSearchParams(searchParams.toString());
        params.set("suite", runDetail.suite_id);
        params.set("run", selectedRunIdParam);
        router.replace(`/grai-evals?${params.toString()}` as Route);
      }
      return;
    }
    if (selectedSuiteIdParam && suites.some((item) => item.suite_id === selectedSuiteIdParam)) {
      return;
    }
    if (selectedRunIdParam && !runDetail && !runDetailError) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("suite", suites[0].suite_id);
    params.delete("run");
    const target = `/grai-evals?${params.toString()}`;
    if (typeof window !== "undefined" && window.location.pathname + window.location.search === target) {
      return;
    }
    router.replace(target as Route);
  }, [
    router,
    runDetail,
    runDetailError,
    searchParams,
    selectedRunIdParam,
    selectedSuiteIdParam,
    suites,
  ]);

  useEffect(() => {
    setResultsCursor(null);
    setResultItems([]);
  }, [
    reportFilters.assertion_type,
    reportFilters.destination_index,
    reportFilters.prompt_id,
    reportFilters.status,
    reportFilters.tag,
    selectedRunIdParam,
  ]);

  useEffect(() => {
    setReportFilters({
      prompt_id: null,
      assertion_type: null,
      tag: null,
      status: null,
      destination_index: null,
    });
    setArtifactResultId(null);
  }, [selectedRunIdParam]);

  useEffect(() => {
    setTransportProfileIds([]);
  }, [selectedSuiteIdParam]);

  useEffect(() => {
    if (!resultsPage) {
      return;
    }
    setResultItems((current) => {
      if (!resultsCursor) {
        return resultsPage.items;
      }
      const next = [...current];
      const seen = new Set(current.map((item) => item.eval_result_id));
      for (const item of resultsPage.items) {
        if (!seen.has(item.eval_result_id)) {
          next.push(item);
          seen.add(item.eval_result_id);
        }
      }
      return next;
    });
  }, [resultsCursor, resultsPage]);

  const filteredSuites = useMemo(
    () => suiteSearchFilter(suites ?? [], deferredSuiteSearch),
    [deferredSuiteSearch, suites]
  );
  const httpDestinations = useMemo(() => destinationChoices(destinations), [destinations]);
  const selectedSuiteSummary = useMemo(
    () => (suites ?? []).find((item) => item.suite_id === selectedSuiteIdParam) ?? null,
    [selectedSuiteIdParam, suites]
  );
  const selectedAssertionTypes = useMemo(() => suiteAssertionTypes(suiteDetail), [suiteDetail]);
  const selectedTags = useMemo(() => suiteTags(suiteDetail), [suiteDetail]);
  const selectedRunStatus = runProgress?.status ?? runDetail?.status ?? null;
  const reportData = report ?? null;

  async function refreshRunSurface() {
    await Promise.all([mutateRunDetail(), mutateRunProgress()]);
    void mutateMatrix();
    void mutateReport();
    void mutateResultsPage();
    void mutateSuiteRuns();
  }

  function updateQuery(patch: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
    }
    const encoded = params.toString();
    router.replace((encoded ? `/grai-evals?${encoded}` : "/grai-evals") as Route);
  }

  async function handleCreateSuite(payload: GraiEvalSuiteUpsertRequest) {
    setSavingSuite(true);
    setCreateError("");
    try {
      const created = await createGraiEvalSuite(payload);
      await mutateSuites();
      setShowCreateDialog(false);
      updateQuery({ suite: created.suite_id, run: null });
    } catch (err) {
      setCreateError(mapApiError(err, "Failed to create grai eval suite").message);
    } finally {
      setSavingSuite(false);
    }
  }

  async function handleEditSuite(payload: GraiEvalSuiteUpsertRequest) {
    if (!selectedSuiteIdParam) return;
    setSavingSuite(true);
    setEditError("");
    try {
      await updateGraiEvalSuite(selectedSuiteIdParam, payload);
      await mutateSuites();
      setShowEditDialog(false);
    } catch (err) {
      setEditError(mapApiError(err, "Failed to update grai eval suite").message);
    } finally {
      setSavingSuite(false);
    }
  }

  async function handleDeleteSuite() {
    if (!selectedSuiteIdParam) return;
    setDeletingSuite(true);
    try {
      await deleteGraiEvalSuite(selectedSuiteIdParam);
      await mutateSuites();
      setShowEditDialog(false);
      updateQuery({ suite: null, run: null });
    } catch (err) {
      setEditError(mapApiError(err, "Failed to delete grai eval suite").message);
    } finally {
      setDeletingSuite(false);
    }
  }

  async function handleImportSuite(values: { name: string; yaml: string }) {
    setImportingSuite(true);
    setImportError("");
    try {
      const created = await importGraiEvalSuite({
        yaml_content: values.yaml,
        name: values.name.trim() || null,
      });
      await mutateSuites();
      setShowImportDialog(false);
      updateQuery({ suite: created.suite_id, run: null });
    } catch (err) {
      setImportError(mapApiError(err, "Failed to import grai eval suite").message);
    } finally {
      setImportingSuite(false);
    }
  }

  async function handleLaunchRun() {
    if (!selectedSuiteIdParam || transportProfileIds.length === 0) {
      return;
    }
    setLaunchingRun(true);
    setPageError("");
    try {
      const created = await createGraiEvalRun({
        suite_id: selectedSuiteIdParam,
        transport_profile_id: transportProfileIds[0] ?? null,
        transport_profile_ids: transportProfileIds,
      });
      await mutateSuiteRuns();
      setArtifactResultId(null);
      setResultItems([]);
      setResultsCursor(null);
      updateQuery({ run: created.eval_run_id });
    } catch (err) {
      setPageError(mapApiError(err, "Failed to launch grai eval run").message);
    } finally {
      setLaunchingRun(false);
    }
  }

  async function handleCancelRun() {
    if (!selectedRunIdParam) {
      return;
    }
    setCancellingRun(true);
    setPageError("");
    try {
      await cancelGraiEvalRun(selectedRunIdParam);
      await refreshRunSurface();
    } catch (err) {
      setPageError(mapApiError(err, "Failed to cancel grai eval run").message);
    } finally {
      setCancellingRun(false);
    }
  }

  function toggleTransportProfile(transportProfileId: string) {
    setTransportProfileIds((current) => {
      if (current.includes(transportProfileId)) {
        return current.filter((item) => item !== transportProfileId);
      }
      return [...current, transportProfileId];
    });
  }

  if (!roleResolved) {
    return <TableState kind="loading" message="Loading Grai evals access…" columns={1} rows={3} />;
  }

  if (!canViewGraiEvals) {
    return (
      <TableState
        kind="error"
        title="Grai evals unavailable"
        message="Viewer access is required to open the Grai Evals surface."
        columns={1}
      />
    );
  }

  return (
    <>
      <div className="space-y-6" data-testid="grai-evals-page">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text-primary">Grai Evals</h1>
            <p className="mt-0.5 max-w-3xl text-sm text-text-secondary">
              Create or import large direct-HTTP eval suites, run against one or more destinations
              simultaneously, then work from failure clusters instead of raw result sprawl.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canManageGraiSuites ? (
              <>
                <Button
                  variant="secondary"
                  data-testid="grai-import-button"
                  onClick={() => setShowImportDialog(true)}
                >
                  <Upload className="h-4 w-4" />
                  Import YAML
                </Button>
                <Button data-testid="grai-create-suite-button" onClick={() => setShowCreateDialog(true)}>
                  <Plus className="h-4 w-4" />
                  New Suite
                </Button>
              </>
            ) : null}
          </div>
        </div>

        {!canManageGraiSuites ? (
          <p className="text-xs text-text-muted">
            Read-only access. Suite creation and import require editor role or above. Run launch
            requires operator role or above.
          </p>
        ) : null}

        <div className="rounded-2xl border border-border bg-bg-elevated/50 px-4 py-3 text-xs text-text-secondary">
          Multi-destination evals now run one suite against several active HTTP transport profiles in
          the same job. Use the comparison matrix for side-by-side destination analysis, then drop
          into the failure-first report and raw result rows for deeper triage.
        </div>

        {pageError ? <p className="text-sm text-fail">{pageError}</p> : null}

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="overflow-hidden">
            <CardHeader className="flex-col items-stretch gap-3">
              <div>
                <p className="text-sm font-medium text-text-secondary">Suites</p>
                <p className="mt-1 text-xs text-text-muted">
                  Search imported and native eval suites without leaving the execution surface.
                </p>
              </div>
              <input
                data-testid="grai-suite-search"
                value={suiteSearch}
                onChange={(event) => setSuiteSearch(event.target.value)}
                placeholder="Search suite name, id, description…"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </CardHeader>
            <CardBody className="space-y-3">
              {!suites && !suitesError ? (
                <TableState kind="loading" message="Loading grai suites…" columns={1} rows={4} />
              ) : null}
              {suitesError ? (
                <TableState
                  kind="error"
                  message={mapApiError(suitesError, "Failed to load grai suites").message}
                  columns={1}
                />
              ) : null}
              {suites && suites.length === 0 ? (
                <TableState
                  kind="empty"
                  title="No grai suites yet"
                  message="Import promptfoo YAML or create a native suite to start direct-HTTP eval runs."
                  columns={1}
                />
              ) : null}
              {filteredSuites.map((suite) => {
                const selected = suite.suite_id === selectedSuiteIdParam;
                return (
                  <button
                    key={suite.suite_id}
                    type="button"
                    data-testid={`grai-suite-card-${suite.suite_id}`}
                    onClick={() => updateQuery({ suite: suite.suite_id, run: null })}
                    className={`w-full cursor-pointer rounded-xl border p-4 text-left transition-colors ${
                      selected
                        ? "border-brand bg-brand/10"
                        : "border-border bg-bg-elevated/50 hover:border-border-focus hover:bg-bg-elevated"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">{suite.name}</p>
                        <p className="mt-1 text-xs text-text-muted">{suite.suite_id}</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-text-muted" />
                    </div>
                    {suite.description ? (
                      <p className="mt-3 text-sm text-text-secondary">{suite.description}</p>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-muted">
                      <span>{suite.prompt_count} prompts</span>
                      <span>{suite.case_count} cases</span>
                      {suite.has_source_yaml ? <span>Imported YAML</span> : <span>Native suite</span>}
                    </div>
                  </button>
                );
              })}
            </CardBody>
          </Card>

          <div className="space-y-6">
            {!selectedSuiteSummary ? (
              <TableState
                kind="empty"
                title="Select a suite"
                message="Choose a grai suite from the rail to inspect prompts, launch runs, and review reports."
                columns={1}
              />
            ) : null}

            {selectedSuiteSummary && !suiteDetail && !suiteDetailError ? (
              <TableState kind="loading" message="Loading suite detail…" columns={1} rows={4} />
            ) : null}

            {suiteDetailError ? (
              <TableState
                kind="error"
                message={mapApiError(suiteDetailError, "Failed to load grai suite detail").message}
                columns={1}
              />
            ) : null}

            {suiteDetail && !suiteDetailError ? (
              <>
                <Card>
                  <CardHeader className="flex-row items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-text-secondary">Suite Overview</p>
                      <h2 className="mt-1 text-lg font-semibold text-text-primary">{suiteDetail.name}</h2>
                      <p className="mt-1 text-xs text-text-muted">{suiteDetail.suite_id}</p>
                    </div>
                    {canManageGraiSuites ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        data-testid="grai-suite-edit-btn"
                        onClick={() => { setEditError(""); setShowEditDialog(true); }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                    ) : null}
                  </CardHeader>
                  <CardBody className="space-y-5">
                    {suiteDetail.description ? (
                      <p className="text-sm text-text-secondary">{suiteDetail.description}</p>
                    ) : null}
                    <div className="grid gap-3 md:grid-cols-4">
                      <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Prompts</p>
                        <p className="mt-2 text-lg font-semibold text-text-primary">{suiteDetail.prompts.length}</p>
                      </div>
                      <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Cases</p>
                        <p className="mt-2 text-lg font-semibold text-text-primary">{suiteDetail.cases.length}</p>
                      </div>
                      <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Assertions</p>
                        <p className="mt-2 text-sm font-semibold text-text-primary">
                          {selectedAssertionTypes.join(", ") || "—"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Updated</p>
                        <p className="mt-2 text-sm font-semibold text-text-primary">
                          {formatTs(suiteDetail.updated_at)}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Prompt Variants</p>
                        <div className="mt-3 space-y-2">
                          {suiteDetail.prompts.map((prompt) => (
                            <div key={prompt.prompt_id} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                              <p className="text-sm font-medium text-text-primary">{prompt.label}</p>
                              <p className="mt-1 line-clamp-3 text-sm text-text-secondary">{prompt.prompt_text}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Case Coverage</p>
                        <div className="mt-3 space-y-2">
                          {suiteDetail.cases.map((item) => (
                            <div key={item.case_id} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                              <p className="text-sm font-medium text-text-primary">
                                {item.description || item.case_id}
                              </p>
                              <div className="mt-2 flex flex-wrap gap-2">
                                {item.tags_json.map((tag) => (
                                  <span
                                    key={`${item.case_id}-${tag}`}
                                    className="rounded-full border border-border px-2 py-1 text-[11px] text-text-secondary"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </CardBody>
                </Card>

                <Card data-testid="grai-run-launch-card">
                  <CardHeader>
                    <div>
                      <p className="text-sm font-medium text-text-secondary">Launch Eval Run</p>
                      <p className="mt-1 text-xs text-text-muted">
                        Choose one or more active HTTP transport profiles. The run snapshots each
                        destination&apos;s endpoint, headers, and direct HTTP config at launch.
                      </p>
                    </div>
                  </CardHeader>
                  <CardBody className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
                    <label className="block">
                      <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-text-muted">
                        HTTP Transport Profiles
                      </span>
                      <div
                        data-testid="grai-run-transport-select"
                        className="space-y-2 rounded-md border border-border bg-bg-elevated p-3"
                      >
                        {httpDestinations.length === 0 ? (
                          <p className="text-sm text-text-muted">
                            No active HTTP transport profiles available.
                          </p>
                        ) : null}
                        {httpDestinations.map((item) => {
                          const checked = transportProfileIds.includes(item.transport_profile_id);
                          return (
                            <label
                              key={item.transport_profile_id}
                              className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2 text-sm transition-colors ${
                                checked
                                  ? "border-brand bg-brand/10 text-text-primary"
                                  : "border-border bg-bg-surface text-text-secondary"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleTransportProfile(item.transport_profile_id)}
                                data-testid={`grai-run-transport-option-${item.transport_profile_id}`}
                                className="mt-0.5 h-4 w-4 rounded border-border"
                              />
                              <span className="min-w-0">
                                <span className="block font-medium">{item.name}</span>
                                <span className="block text-xs text-text-muted">
                                  {item.transport_profile_id}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        data-testid="grai-run-launch-button"
                        onClick={() => void handleLaunchRun()}
                        disabled={!canLaunchGraiRuns || launchingRun || transportProfileIds.length === 0}
                      >
                        {launchingRun ? (
                          <>
                            <LoaderCircle className="h-4 w-4 animate-spin" />
                            Launching…
                          </>
                        ) : (
                          <>
                            <Play className="h-4 w-4" />
                            Run Grai Eval
                          </>
                        )}
                      </Button>
                      {selectedRunIdParam ? (
                        <Button
                          variant="secondary"
                          data-testid="grai-run-refresh-button"
                          onClick={() => void refreshRunSurface()}
                        >
                          <RefreshCw className="h-4 w-4" />
                          Refresh
                        </Button>
                      ) : null}
                    </div>
                    {!canLaunchGraiRuns ? (
                      <p className="lg:col-span-2 text-xs text-text-muted">
                        Run launch requires operator role or above.
                      </p>
                    ) : null}
                    {transportProfileIds.length > 0 ? (
                      <p className="lg:col-span-2 text-xs text-text-muted">
                        Selected {transportProfileIds.length} destination
                        {transportProfileIds.length === 1 ? "" : "s"} for this run.
                      </p>
                    ) : null}
                    {httpDestinations.length === 0 ? (
                      <p className="lg:col-span-2 text-xs text-text-muted">
                        No active HTTP transport profiles are available yet. Create one in transport
                        profiles before launching a grai eval.
                      </p>
                    ) : null}
                  </CardBody>
                </Card>

                <Card data-testid="grai-run-history-card">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-text-secondary">Run History</p>
                        <p className="mt-1 text-xs text-text-muted">
                          Reopen prior eval reports for this suite without needing the run id.
                        </p>
                      </div>
                      <span className="rounded-full border border-border px-2.5 py-1 text-[11px] text-text-muted">
                        {suiteRuns
                          ? `${suiteRuns.length} recent run${suiteRuns.length === 1 ? "" : "s"}`
                          : "—"}
                      </span>
                    </div>
                  </CardHeader>
                  <CardBody className="space-y-3">
                    {!suiteRuns && !suiteRunsError ? (
                      <TableState kind="loading" message="Loading suite run history…" columns={1} rows={3} />
                    ) : null}
                    {suiteRunsError ? (
                      <TableState
                        kind="error"
                        message={mapApiError(suiteRunsError, "Failed to load grai eval run history").message}
                        columns={1}
                      />
                    ) : null}
                    {suiteRuns && suiteRuns.length === 0 ? (
                      <TableState
                        kind="empty"
                        title="No prior runs"
                        message="Launch the first eval for this suite to start building report history."
                        columns={1}
                      />
                    ) : null}
                    {(suiteRuns ?? []).map((run) => {
                      const selected = run.eval_run_id === selectedRunIdParam;
                      return (
                        <button
                          key={run.eval_run_id}
                          type="button"
                          aria-label={`Open eval run from ${formatTs(run.created_at)}, status ${run.status}`}
                          aria-current={selected ? "true" : undefined}
                          data-testid={`grai-run-history-${run.eval_run_id}`}
                          onClick={() => updateQuery({ suite: run.suite_id, run: run.eval_run_id })}
                          className={`w-full rounded-xl border px-4 py-4 text-left transition-colors ${
                            selected
                              ? "border-brand bg-brand/10"
                              : "border-border bg-bg-elevated/40 hover:border-border-focus hover:bg-bg-elevated"
                          }`}
                        >
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge value={statusTone(run.status)} label={run.status} />
                                <p className="text-sm font-medium text-text-primary">{formatTs(run.created_at)}</p>
                              </div>
                              <p className="mt-2 text-xs text-text-secondary">{runHistoryDestinationSummary(run)}</p>
                              <p className="mt-1 text-xs text-text-muted">{runHistoryMeta(run)}</p>
                            </div>
                            <div className="text-left lg:text-right">
                              <p className="text-xs text-text-secondary">{run.trigger_source}</p>
                              <p className="mt-1 text-[11px] text-text-muted">
                                {run.triggered_by || run.schedule_id || "Manual launch"}
                              </p>
                              <p className="mt-2 text-[11px] text-text-muted">{run.eval_run_id}</p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </CardBody>
                </Card>

                <TenantProviderAccessCard
                  testId="grai-provider-access-card"
                  title="Eval provider access"
                  description="Grai suites launch against HTTP destinations but the scoring path still depends on tenant-assigned judge and LLM providers."
                  providers={availableProviders}
                  capabilities={["judge", "llm"]}
                  loading={!availableProvidersResponse && !availableProvidersError}
                  errorMessage={availableProvidersError?.message ?? null}
                />
              </>
            ) : null}

            {selectedRunIdParam ? (
              <Card data-testid="grai-run-progress-card">
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-text-secondary">Run Progress</p>
                      <p className="mt-1 text-xs text-text-muted">{selectedRunIdParam}</p>
                    </div>
                    {selectedRunStatus ? (
                      <div className="flex items-center gap-2">
                        <StatusBadge value={statusTone(selectedRunStatus)} label={selectedRunStatus} />
                        {(selectedRunStatus === "pending" || selectedRunStatus === "running") && canLaunchGraiRuns ? (
                          <Button
                            variant="secondary"
                            size="sm"
                            data-testid="grai-run-cancel-button"
                            onClick={() => void handleCancelRun()}
                            disabled={cancellingRun}
                          >
                            {cancellingRun ? "Cancelling…" : "Cancel"}
                          </Button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </CardHeader>
                <CardBody className="space-y-4">
                  {runDetailError || runProgressError ? (
                    <TableState
                      kind="error"
                      message={mapApiError(runProgressError ?? runDetailError, "Failed to load grai eval run").message}
                      columns={1}
                    />
                  ) : null}
                  {!runProgress && !runDetail && !runDetailError && !runProgressError ? (
                    <TableState kind="loading" message="Loading run progress…" columns={1} rows={2} />
                  ) : null}
                  {(runProgress || runDetail) && !runDetailError && !runProgressError ? (
                    <>
                      <div className="grid gap-3 md:grid-cols-4">
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Total pairs</p>
                          <p className="mt-2 text-lg font-semibold text-text-primary">
                            {runProgress?.total_pairs ?? runDetail?.total_pairs ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Completed</p>
                          <p className="mt-2 text-lg font-semibold text-text-primary">
                            {runProgress?.completed_count ?? runDetail?.completed_count ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Failed</p>
                          <p className="mt-2 text-lg font-semibold text-fail">
                            {runProgress?.failed_count ?? runDetail?.failed_count ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Updated</p>
                          <p className="mt-2 text-sm font-semibold text-text-primary">
                            {formatTs(runProgress?.updated_at ?? runDetail?.updated_at)}
                          </p>
                        </div>
                      </div>
                      {runDetail?.transport_profile_ids?.length ? (
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                            Destinations
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {runDetail.transport_profile_ids.map((item) => (
                              <span
                                key={item}
                                className="rounded-full border border-border px-2 py-1 text-[11px] text-text-secondary"
                              >
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs text-text-muted">
                          <span>Progress</span>
                          <span>{progressPercent(runProgress?.progress_fraction ?? 0)}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-bg-elevated">
                          <div
                            className="h-full rounded-full bg-brand transition-[width] duration-300"
                            style={{ width: progressPercent(runProgress?.progress_fraction ?? 0) }}
                          />
                        </div>
                      </div>
                    </>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}

            {selectedRunIdParam ? (
              <Card>
                <CardBody className="p-5">
                  <GraiMatrixCard
                    matrix={matrix ?? null}
                    loading={!matrix && !matrixError}
                    error={matrixError ? mapApiError(matrixError, "Failed to build grai matrix").message : null}
                    onOpenArtifact={(evalResultId) => setArtifactResultId(evalResultId)}
                  />
                </CardBody>
              </Card>
            ) : null}

            {selectedRunIdParam ? (
              <Card data-testid="grai-report-card">
                <CardHeader className="flex-col items-stretch gap-4">
                  <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-sm font-medium text-text-secondary">Failure Report</p>
                      <p className="mt-1 text-xs text-text-muted">
                        Review failure clusters first, then drill into exemplar request/response artifacts.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-text-muted">
                      <FileSearch className="h-4 w-4" />
                      {reportData
                        ? `${reportData.failed_results} failed results / ${reportData.total_results} total`
                        : "Waiting for report data"}
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-5">
                    <select
                      data-testid="grai-report-filter-prompt"
                      value={reportFilters.prompt_id ?? ""}
                      onChange={(event) =>
                        setReportFilters((current) => ({
                          ...current,
                          prompt_id: event.target.value || null,
                        }))
                      }
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">All prompts</option>
                      {suiteDetail?.prompts.map((prompt) => (
                        <option key={prompt.prompt_id} value={prompt.prompt_id}>
                          {prompt.label}
                        </option>
                      ))}
                    </select>
                    <select
                      data-testid="grai-report-filter-assertion"
                      value={reportFilters.assertion_type ?? ""}
                      onChange={(event) =>
                        setReportFilters((current) => ({
                          ...current,
                          assertion_type: event.target.value || null,
                        }))
                      }
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">All assertion types</option>
                      {selectedAssertionTypes.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                    <select
                      data-testid="grai-report-filter-tag"
                      value={reportFilters.tag ?? ""}
                      onChange={(event) =>
                        setReportFilters((current) => ({
                          ...current,
                          tag: event.target.value || null,
                        }))
                      }
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">All tags</option>
                      {selectedTags.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                    <select
                      data-testid="grai-report-filter-destination"
                      value={reportFilters.destination_index ?? ""}
                      onChange={(event) =>
                        setReportFilters((current) => ({
                          ...current,
                          destination_index:
                            event.target.value === "" ? null : Number(event.target.value),
                        }))
                      }
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">All destinations</option>
                      {(runDetail?.destinations ?? []).map((item) => (
                        <option key={item.destination_index} value={item.destination_index}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <select
                      data-testid="grai-report-filter-status"
                      value={reportFilters.status ?? ""}
                      onChange={(event) =>
                        setReportFilters((current) => ({
                          ...current,
                          status: event.target.value ? (event.target.value as "passed" | "failed") : null,
                        }))
                      }
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">All statuses</option>
                      <option value="failed">Failed only</option>
                      <option value="passed">Passed only</option>
                    </select>
                  </div>
                </CardHeader>
                <CardBody className="space-y-5">
                  {reportError ? (
                    <TableState
                      kind="error"
                      message={mapApiError(reportError, "Failed to build grai report").message}
                      columns={1}
                    />
                  ) : null}
                  {!reportData && !reportError ? (
                    <TableState kind="loading" message="Building grai report…" columns={1} rows={3} />
                  ) : !reportError ? (
                    <>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Results</p>
                          <p className="mt-2 text-lg font-semibold text-text-primary">
                            {reportData?.total_results ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Passed</p>
                          <p className="mt-2 text-lg font-semibold text-ok">
                            {reportData?.passed_results ?? 0}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-3">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Failed</p>
                          <p className="mt-2 text-lg font-semibold text-fail">
                            {reportData?.failed_results ?? 0}
                          </p>
                        </div>
                      </div>

                      <div className="grid gap-4 xl:grid-cols-3">
                        <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Assertion Breakdown</p>
                          <div className="mt-3 space-y-2">
                            {(reportData?.assertion_type_breakdown ?? []).map((item) => (
                              <div key={item.assertion_type} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-medium text-text-primary">{item.assertion_type}</p>
                                  <span className="text-xs text-text-muted">{item.total_results}</span>
                                </div>
                                <p className="mt-1 text-xs text-text-secondary">
                                  {item.failed_results} failed · {item.passed_results} passed
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Failing Prompt Variants</p>
                          <div className="mt-3 space-y-2">
                            {(reportData?.failing_prompt_variants.length ?? 0) > 0 ? (
                              (reportData?.failing_prompt_variants ?? []).map((item) => (
                                <div key={item.prompt_id} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                                  <p className="text-sm font-medium text-text-primary">{item.prompt_label}</p>
                                  <p className="mt-1 text-xs text-text-secondary">
                                    {item.failure_count} failed assertions across {item.failed_pairs} prompt/case pairs
                                  </p>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-text-muted">No failing prompt variants for the current filter.</p>
                            )}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Tag Failure Clusters</p>
                          <div className="mt-3 space-y-2">
                            {(reportData?.tag_failure_clusters.length ?? 0) > 0 ? (
                              (reportData?.tag_failure_clusters ?? []).map((item) => (
                                <div key={item.tag} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                                  <p className="text-sm font-medium text-text-primary">{item.tag}</p>
                                  <p className="mt-1 text-xs text-text-secondary">
                                    {item.failure_count} failed assertions across {item.failed_pairs} pairs
                                  </p>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-text-muted">No failing tag clusters for the current filter.</p>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Exemplar Failures</p>
                            <p className="mt-1 text-xs text-text-secondary">
                              Inspect stored request/response artifacts for the most recent failed results.
                            </p>
                          </div>
                        </div>
                        <div className="mt-3 space-y-2">
                          {(reportData?.exemplar_failures.length ?? 0) > 0 ? (
                            (reportData?.exemplar_failures ?? []).map((item) => (
                              <div key={item.eval_result_id} className="rounded-lg border border-border bg-bg-surface px-3 py-3">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-text-primary">{resultLabel(item)}</p>
                                    <p className="mt-1 text-xs text-text-secondary">
                                      {item.failure_reason || "Assertion failed"} · {formatTs(item.created_at)}
                                    </p>
                                  </div>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    data-testid={`grai-exemplar-open-${item.eval_result_id}`}
                                    onClick={() => setArtifactResultId(item.eval_result_id)}
                                  >
                                    <FlaskConical className="h-3.5 w-3.5" />
                                    View Artifact
                                  </Button>
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-text-muted">No exemplar failures for the current filter.</p>
                          )}
                        </div>
                      </div>
                    </>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}

            {selectedRunIdParam ? (
              <Card data-testid="grai-results-card">
                <CardHeader>
                  <div>
                    <p className="text-sm font-medium text-text-secondary">Result Rows</p>
                    <p className="mt-1 text-xs text-text-muted">
                      Cursor-paginated rows for drilldown, triage, and future export views.
                    </p>
                  </div>
                </CardHeader>
                <CardBody className="space-y-3">
                  {resultsError ? (
                    <TableState
                      kind="error"
                      message={mapApiError(resultsError, "Failed to load grai eval result rows").message}
                      columns={1}
                    />
                  ) : null}
                  {!resultsPage && !resultsError ? (
                    <TableState kind="loading" message="Loading result rows…" columns={1} rows={3} />
                  ) : null}
                  {resultsPage && resultItems.length === 0 && !resultsError ? (
                    <TableState
                      kind="empty"
                      title="No result rows"
                      message="Adjust the current filter or let the eval run finish dispatching more pairs."
                      columns={1}
                    />
                  ) : null}
                  {resultItems.map((item) => (
                    <div
                      key={item.eval_result_id}
                      className="rounded-xl border border-border bg-bg-elevated/60 px-4 py-4"
                      data-testid={`grai-result-row-${item.eval_result_id}`}
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <StatusBadge value={item.passed ? "pass" : "fail"} label={item.passed ? "passed" : "failed"} />
                            <p className="text-sm font-medium text-text-primary">{resultLabel(item)}</p>
                          </div>
                          <p className="mt-2 text-xs text-text-secondary">
                            {item.failure_reason || "Passed"} · latency {item.latency_ms ?? "—"} ms
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {item.tags_json.map((tag) => (
                              <span
                                key={`${item.eval_result_id}-${tag}`}
                                className="rounded-full border border-border px-2 py-1 text-[11px] text-text-secondary"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {item.raw_s3_key ? (
                            <Button
                              variant="secondary"
                              size="sm"
                              data-testid={`grai-result-artifact-${item.eval_result_id}`}
                              onClick={() => setArtifactResultId(item.eval_result_id)}
                            >
                              View Artifact
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                  {resultsPage?.next_cursor ? (
                    <div className="flex justify-end">
                      <Button
                        variant="secondary"
                        data-testid="grai-results-load-more"
                        onClick={() => setResultsCursor(resultsPage.next_cursor ?? null)}
                      >
                        Load Next Page
                      </Button>
                    </div>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}
          </div>
        </div>
      </div>

      <GraiImportDialog
        open={showImportDialog}
        importing={importingSuite}
        error={importError}
        onOpenChange={setShowImportDialog}
        onSubmit={handleImportSuite}
      />
      <GraiSuiteEditorDialog
        open={showCreateDialog}
        saving={savingSuite}
        error={createError}
        onOpenChange={setShowCreateDialog}
        onSubmit={handleCreateSuite}
      />
      <GraiSuiteEditorDialog
        open={showEditDialog}
        saving={savingSuite}
        deleting={deletingSuite}
        error={editError}
        initialSuite={suiteDetail ?? null}
        onOpenChange={setShowEditDialog}
        onSubmit={handleEditSuite}
        onDelete={handleDeleteSuite}
      />
      <GraiArtifactDialog
        open={artifactResultId !== null}
        evalRunId={selectedRunIdParam}
        evalResultId={artifactResultId}
        onOpenChange={(open) => {
          if (!open) {
            setArtifactResultId(null);
          }
        }}
      />
    </>
  );
}
