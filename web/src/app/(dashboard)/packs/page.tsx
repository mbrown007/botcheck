"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Edit3, ExternalLink, Play, Trash2 } from "lucide-react";
import {
  cancelPackRun,
  deletePack,
  markPackRunFailed,
  runPack,
  usePackRun,
  usePackRunChildren,
  useTransportProfiles,
  useFeatures,
  usePackRuns,
  usePacks,
} from "@/lib/api";
import type { PackRunSummary } from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  describeTransportDispatch,
  destinationLabelForId,
  destinationNameMap,
  transportProfileOptionLabel,
} from "@/lib/destination-display";
import { derivePackRunMonitorPhase, latestPackRunActivity } from "@/lib/run-monitor";
import { useDashboardAccess } from "@/lib/current-user";

type PackStateVariant = "pass" | "warn" | "fail" | "pending";

function packStateVariant(state: string): PackStateVariant {
  const normalized = state.trim().toLowerCase();
  if (normalized === "complete") {
    return "pass";
  }
  if (normalized === "partial" || normalized === "running" || normalized === "pending") {
    return "warn";
  }
  if (normalized === "failed" || normalized === "cancelled") {
    return "fail";
  }
  return "pending";
}

function formatTs(value?: string | null): string {
  if (!value) {
    return "\u2014";
  }
  return new Date(value).toLocaleString();
}

export default function PacksPage() {
  const { data: packs, error, mutate } = usePacks();
  const { data: packRuns, mutate: mutatePackRuns } = usePackRuns();
  const { data: features } = useFeatures();
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const destinationNames = useMemo(
    () => destinationNameMap(destinations),
    [destinations]
  );
  const [runningPackId, setRunningPackId] = useState<string | null>(null);
  const [monitorPackRunId, setMonitorPackRunId] = useState<string | null>(null);
  const [runModalPackId, setRunModalPackId] = useState<string | null>(null);
  const [transportProfileId, setTransportProfileId] = useState("");
  const [dialTarget, setDialTarget] = useState("");
  const [actionError, setActionError] = useState<string>("");
  const [monitorActionLoading, setMonitorActionLoading] = useState<"cancel" | "fail" | null>(null);
  const [monitorActionError, setMonitorActionError] = useState("");
  const { data: monitorPackRun, mutate: mutateMonitorPackRun } = usePackRun(monitorPackRunId);
  const { data: monitorPackChildren } = usePackRunChildren(monitorPackRunId, { limit: 8 });
  const { canManagePacks } = useDashboardAccess();
  const dispatchHint = useMemo(
    () =>
      describeTransportDispatch({
        destinations,
        transportProfileId,
        dialTarget,
        fallbackTargetLabel: "child scenario endpoint",
      }),
    [destinations, transportProfileId, dialTarget],
  );
  const monitorPhase = monitorPackRun ? derivePackRunMonitorPhase(monitorPackRun.state) : null;
  const packRunActivity = useMemo(
    () => latestPackRunActivity(monitorPackChildren?.items),
    [monitorPackChildren?.items],
  );

  const latestRunByPackId = useMemo(() => {
    const mapping = new Map<string, PackRunSummary>();
    for (const run of packRuns ?? []) {
      if (!mapping.has(run.pack_id)) {
        mapping.set(run.pack_id, run);
      }
    }
    return mapping;
  }, [packRuns]);

  function handleOpenRunModal(packId: string) {
    setDialTarget("");
    setTransportProfileId("");
    setActionError("");
    setRunModalPackId(packId);
  }

  async function executePackRun(packId: string) {
    setActionError("");
    setRunningPackId(packId);
    try {
      const started = await runPack(packId, {
        transportProfileId: transportProfileId || undefined,
        dialTarget: dialTarget || undefined,
      });
      setMonitorPackRunId(started.pack_run_id);
      await Promise.all([mutate(), mutatePackRuns()]);
    } catch (err) {
      setActionError(mapApiError(err, "Failed to run pack").message);
    } finally {
      setRunningPackId((prev) => (prev === packId ? null : prev));
    }
  }

  async function handleRunNow() {
    const packId = runModalPackId;
    if (!packId) return;
    setRunModalPackId(null);
    await executePackRun(packId);
  }

  async function handleCancelPackRun() {
    if (!monitorPackRun || !window.confirm("Cancel this pack run now?")) {
      return;
    }
    setMonitorActionLoading("cancel");
    setMonitorActionError("");
    try {
      await cancelPackRun(monitorPackRun.pack_run_id);
      await Promise.all([mutateMonitorPackRun(), mutatePackRuns()]);
    } catch (err) {
      setMonitorActionError(mapApiError(err, "Failed to cancel pack run").message);
    } finally {
      setMonitorActionLoading((current) => (current === "cancel" ? null : current));
    }
  }

  async function handleMarkPackRunFailed() {
    if (!monitorPackRun || !window.confirm("Mark this pack run as failed?")) {
      return;
    }
    setMonitorActionLoading("fail");
    setMonitorActionError("");
    try {
      await markPackRunFailed(monitorPackRun.pack_run_id, "Marked failed by operator from pack monitor");
      await Promise.all([mutateMonitorPackRun(), mutatePackRuns()]);
    } catch (err) {
      setMonitorActionError(mapApiError(err, "Failed to mark pack run failed").message);
    } finally {
      setMonitorActionLoading((current) => (current === "fail" ? null : current));
    }
  }

  async function handleDelete(packId: string) {
    if (!window.confirm("Delete this pack? This cannot be undone.")) {
      return;
    }
    setActionError("");
    try {
      await deletePack(packId);
      await Promise.all([mutate(), mutatePackRuns()]);
    } catch (err) {
      setActionError(mapApiError(err, "Failed to delete pack").message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Packs</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            Grouped scenario suites for one-click regression execution
          </p>
        </div>
        {canManagePacks ? (
          <Link
            href="/packs/new"
            className="inline-flex h-9 items-center justify-center rounded-md bg-brand px-4 text-sm font-medium text-text-inverse transition-colors hover:bg-brand-hover"
          >
            New Pack
          </Link>
        ) : null}
      </div>
      {!canManagePacks ? (
        <p className="text-xs text-text-muted">
          Read-only access. Pack create, edit, run, and delete require admin role or above.
        </p>
      ) : null}

      {destinationsEnabled ? (
        <Card>
          <CardBody className="space-y-3">
            <div className="grid gap-3 md:grid-cols-[minmax(0,20rem)_1fr]">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text-secondary">
                  Transport Profile <span className="font-normal text-text-muted">(optional)</span>
                </span>
                <select
                  value={transportProfileId}
                  onChange={(event) => setTransportProfileId(event.target.value)}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                >
                  <option value="">Use pack/scenario transport defaults</option>
                  {destinations?.map((destination) => (
                    <option
                      key={destination.destination_id}
                      value={destination.destination_id}
                      disabled={!destination.is_active}
                    >
                      {transportProfileOptionLabel(destination)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-[11px] text-text-muted">
                {dispatchHint}
              </div>
            </div>
          </CardBody>
        </Card>
      ) : null}

      {runModalPackId ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-overlay/60 backdrop-blur-sm"
            onClick={() => setRunModalPackId(null)}
          />
          <div className="relative z-50 w-full max-w-lg overflow-hidden rounded-lg border border-border bg-bg-surface shadow-xl">
            <div className="border-b border-border px-6 py-4">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Run Pack</p>
              <h2 className="mt-1 text-lg font-semibold text-text-primary">
                {packs?.find((p) => p.pack_id === runModalPackId)?.name ?? runModalPackId}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                Optionally override the transport profile or target before running.
              </p>
            </div>
            <div className="space-y-4 px-6 py-5">
              {destinationsEnabled ? (
                <>
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-text-secondary">
                      Transport Profile <span className="font-normal text-text-muted">(optional)</span>
                    </span>
                    <select
                      value={transportProfileId}
                      onChange={(event) => setTransportProfileId(event.target.value)}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">Use pack/scenario transport defaults</option>
                      {destinations?.map((destination) => (
                        <option
                          key={destination.destination_id}
                          value={destination.destination_id}
                          disabled={!destination.is_active}
                        >
                          {transportProfileOptionLabel(destination)}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[11px] text-text-muted">
                      Applies stored protocol-specific settings such as endpoint, auth headers, caller ID, and capacity controls when available.
                    </p>
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-text-secondary">
                      Target Override <span className="font-normal text-text-muted">(optional)</span>
                    </span>
                    <input
                      value={dialTarget}
                      onChange={(event) => setDialTarget(event.target.value)}
                      placeholder="Use profile default or enter an endpoint / SIP target"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
                    />
                    <p className="mt-1 text-[11px] text-text-muted">
                      Overrides the transport profile target. For SIP this is the dialed number or URI; for HTTP this is the request endpoint.
                    </p>
                  </label>
                  <p className="text-[11px] text-text-muted">{dispatchHint}</p>
                </>
              ) : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
              <Button variant="secondary" onClick={() => setRunModalPackId(null)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => void handleRunNow()}>
                Run Now
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {monitorPackRun && monitorPhase ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-overlay/60 backdrop-blur-sm"
            onClick={() => setMonitorPackRunId(null)}
          />
          <div className="relative z-50 flex max-h-[min(90vh,720px)] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-bg-surface shadow-xl">
            <div className="border-b border-border px-6 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Pack Run Monitor</p>
                  <h2 className="mt-1 text-lg font-semibold text-text-primary">{monitorPackRun.pack_name}</h2>
                  <p className="mt-1 font-mono text-xs text-text-muted">{monitorPackRun.pack_run_id}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge value={monitorPhase.tone} label={monitorPhase.label} />
                  <Link
                    href={`/pack-runs/${monitorPackRun.pack_run_id}`}
                    className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-bg-base"
                  >
                    Full Detail
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </div>
              <p className="mt-2 text-sm text-text-secondary">{monitorPhase.description}</p>
              {monitorActionError ? <p className="mt-2 text-sm text-fail">{monitorActionError}</p> : null}
            </div>
            <div className="grid gap-4 p-6 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-border bg-bg-base/60 px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">State</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusBadge value={monitorPackRun.state} label={monitorPackRun.state} />
                  <StatusBadge value={monitorPackRun.gate_outcome} label={monitorPackRun.gate_outcome} />
                </div>
              </div>
              <div className="rounded-xl border border-border bg-bg-base/60 px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Progress</p>
                <p className="mt-2 text-lg font-semibold text-text-primary">
                  {monitorPackRun.completed}/{monitorPackRun.total_scenarios}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  dispatched {monitorPackRun.dispatched} · failed {monitorPackRun.failed} · blocked {monitorPackRun.blocked}
                </p>
              </div>
              <div className="rounded-xl border border-border bg-bg-base/60 px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Transport</p>
                <p className="mt-2 text-sm text-text-primary">
                  {destinationLabelForId(
                    monitorPackRun.transport_profile_id ?? monitorPackRun.destination_id,
                    destinationNames
                  ) ??
                    monitorPackRun.transport_profile_id ??
                    monitorPackRun.destination_id ??
                    "scenario/default transport"}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  {monitorPackRun.dial_target || "child scenario endpoints"}
                </p>
              </div>
              <div className="rounded-xl border border-border bg-bg-base/60 px-4 py-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Started</p>
                <p className="mt-2 text-sm text-text-primary">{formatTs(monitorPackRun.created_at)}</p>
                <p className="mt-1 text-xs text-text-muted">updated {formatTs(monitorPackRun.updated_at)}</p>
              </div>
            </div>
            <div className="border-t border-border px-6 py-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Recent Child Activity</p>
                  <p className="mt-1 text-sm text-text-secondary">
                    Live progress across the most recent scenarios in this pack run.
                  </p>
                </div>
                <p className="text-xs text-text-muted">
                  {monitorPackChildren?.total ?? monitorPackRun.total_scenarios} total child runs
                </p>
              </div>
              {packRunActivity.length > 0 ? (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {packRunActivity.map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-border bg-bg-base/60 px-4 py-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-text-primary">{item.title}</p>
                          <p className="mt-1 text-xs text-text-muted">{item.detail}</p>
                        </div>
                        <StatusBadge value={item.tone} label={item.statusLabel} />
                      </div>
                      {item.summary ? (
                        <p className="mt-3 text-xs leading-5 text-text-secondary">{item.summary}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 rounded-xl border border-dashed border-border bg-bg-base/50 px-4 py-4 text-sm text-text-secondary">
                  No child activity yet. The monitor will populate as scenarios are dispatched and completed.
                </p>
              )}
            </div>
            <div className="flex items-center justify-between border-t border-border px-6 py-4">
              <p className="text-xs text-text-muted">
                The monitor updates automatically while the pack run is pending or running.
              </p>
              <div className="flex items-center gap-2">
                {canManagePacks &&
                  (monitorPackRun.state === "pending" || monitorPackRun.state === "running") && (
                  <>
                    <Button
                      variant="secondary"
                      onClick={() => void handleMarkPackRunFailed()}
                      disabled={monitorActionLoading !== null}
                    >
                      {monitorActionLoading === "fail" ? "Marking Failed…" : "Mark Failed"}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => void handleCancelPackRun()}
                      disabled={monitorActionLoading !== null}
                    >
                      {monitorActionLoading === "cancel" ? "Cancelling…" : "Cancel Run"}
                    </Button>
                  </>
                )}
                <Button variant="secondary" onClick={() => setMonitorPackRunId(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <TooltipProvider delayDuration={120}>
      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">
            {packs?.length ?? 0} packs
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {error && (
            <TableState kind="error" title="Failed to load packs" message={error.message} columns={6} />
          )}
          {!packs && !error && (
            <TableState kind="loading" message="Loading packs…" columns={6} rows={5} />
          )}
          {packs?.length === 0 && (
            <TableState
              kind="empty"
              title="No packs yet"
              message="Create a pack to run grouped regression suites."
              columns={6}
            />
          )}
          {packs && packs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                  <th className="px-5 py-3 text-left font-medium">Name</th>
                  <th className="px-5 py-3 text-left font-medium">Scenarios</th>
                  <th className="px-5 py-3 text-left font-medium">Execution</th>
                  <th className="px-5 py-3 text-left font-medium">Last Outcome</th>
                  <th className="px-5 py-3 text-left font-medium">Last Run</th>
                  <th className="px-5 py-3 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {packs.map((pack) => {
                  const latestRun = latestRunByPackId.get(pack.pack_id);
                  return (
                    <tr
                      key={pack.pack_id}
                      className="border-b border-border last:border-0 hover:bg-bg-elevated transition-colors"
                    >
                      <td className="px-5 py-3">
                        <span className="font-mono text-xs text-brand">{pack.pack_id}</span>
                        <p className="text-text-primary text-sm">{pack.name}</p>
                      </td>
                      <td className="px-5 py-3 font-mono text-text-secondary">
                        {pack.scenario_count}
                      </td>
                      <td className="px-5 py-3">
                        <StatusBadge value="pending" label={pack.execution_mode} />
                      </td>
                      <td className="px-5 py-3">
                        {latestRun ? (
                          <div className="space-y-1">
                            <Link
                              href={`/pack-runs/${latestRun.pack_run_id}`}
                              className="inline-flex"
                            >
                              <StatusBadge
                                value={packStateVariant(latestRun.state)}
                                label={latestRun.state.toUpperCase()}
                              />
                            </Link>
                            {latestRun.transport_profile_id || latestRun.destination_id ? (
                              <p className="text-[10px] text-text-muted">
                                transport:{" "}
                                {destinationLabelForId(
                                  latestRun.transport_profile_id ?? latestRun.destination_id,
                                  destinationNames
                                ) ??
                                  latestRun.transport_profile_id ??
                                  latestRun.destination_id}
                                {latestRun.dial_target ? ` · target: ${latestRun.dial_target}` : ""}
                              </p>
                            ) : null}
                          </div>
                        ) : (
                          <span className="text-text-muted text-xs">Never run</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-xs text-text-muted">
                        {latestRun ? formatTs(latestRun.created_at) : "\u2014"}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                aria-label="Run Now"
                                variant="secondary"
                                size="icon"
                                disabled={runningPackId === pack.pack_id || !canManagePacks}
                                onClick={() => {
                                  if (transportProfileId || dialTarget) {
                                    void executePackRun(pack.pack_id);
                                    return;
                                  }
                                  handleOpenRunModal(pack.pack_id);
                                }}
                              >
                                <Play className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                              {runningPackId === pack.pack_id ? "Starting Run" : "Run Now"}
                            </TooltipContent>
                          </Tooltip>
                          {canManagePacks ? (
                            <>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Link
                                    aria-label="Edit"
                                    href={`/packs/${pack.pack_id}/edit`}
                                    className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-bg-elevated text-text-primary transition-colors hover:bg-bg-subtle"
                                  >
                                    <Edit3 className="h-3.5 w-3.5" />
                                  </Link>
                                </TooltipTrigger>
                                <TooltipContent>Edit</TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    aria-label="Delete"
                                    variant="destructive"
                                    size="icon"
                                    onClick={() => void handleDelete(pack.pack_id)}
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Delete</TooltipContent>
                              </Tooltip>
                            </>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {actionError && (
            <p className="px-5 py-4 text-sm text-fail border-t border-border">
              {actionError}
            </p>
          )}
        </CardBody>
      </Card>
      </TooltipProvider>
    </div>
  );
}
