"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import {
  useTransportProfiles,
  useTenantSIPPools,
  useFeatures,
  useRuns,
  useAIScenarios,
  useScenarios,
  createRun,
  stopRun,
  markRunFailed,
  useRun,
  useScenario,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { StatusBadge } from "@/components/ui/badge";
import { GateBadge } from "@/components/runs/gate-badge";
import { AttributionBadge } from "@/components/runs/attribution-badge";
import { Transcript } from "@/components/runs/transcript";
import { RunsDashboard } from "@/components/runs/runs-dashboard";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TableState } from "@/components/ui/table-state";
import {
  describeTransportDispatch,
  destinationLabelForId,
  destinationNameMap,
  transportProfileOptionLabel,
} from "@/lib/destination-display";
import {
  deriveRunMonitorPhase,
  describeRunEvent,
  formatRunEventLabel,
  latestRunEvents,
} from "@/lib/run-monitor";
import { useDashboardAccess } from "@/lib/current-user";

function NewRunModal({
  onClose,
  onCreated,
  canOperateRuns,
}: {
  onClose: () => void;
  onCreated: () => void;
  canOperateRuns: boolean;
}) {
  const { data: scenarios } = useScenarios();
  const { data: features } = useFeatures();
  const aiEnabled = features?.ai_scenarios_enabled === true;
  const { data: aiScenarios } = useAIScenarios(aiEnabled);
  const graphScenarios = useMemo(
    () => (scenarios ?? []).filter((row) => row.scenario_kind !== "ai"),
    [scenarios]
  );
  const destinationsEnabled = features?.destinations_enabled === true;
  const harnessDegraded = features?.harness_degraded === true;
  const harnessState = features?.harness_state ?? "unknown";
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const { data: tenantPools } = useTenantSIPPools(canOperateRuns);
  const [scenarioId, setScenarioId] = useState("");
  const [aiScenarioId, setAiScenarioId] = useState("");
  const [dialTarget, setDialTarget] = useState("");
  const [transportProfileId, setTransportProfileId] = useState("");
  const [trunkPoolId, setTrunkPoolId] = useState("");
  const [adHocOpen, setAdHocOpen] = useState(true);
  const [createdRunId, setCreatedRunId] = useState<string | null>(null);
  const [launchedAiScenarioId, setLaunchedAiScenarioId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { data: monitoredRun, mutate: mutateMonitoredRun } = useRun(createdRunId);
  const { data: monitoredScenario } = useScenario(monitoredRun?.scenario_id ?? null);
  const [monitorActionLoading, setMonitorActionLoading] = useState<"stop" | "fail" | null>(null);
  const [monitorActionError, setMonitorActionError] = useState("");
  const dispatchHint = useMemo(
    () =>
      describeTransportDispatch({
        destinations,
        transportProfileId,
        dialTarget,
        fallbackTargetLabel: "scenario endpoint",
      }),
    [destinations, transportProfileId, dialTarget],
  );
  const selectedPool = useMemo(
    () => tenantPools?.items.find((pool) => pool.trunk_pool_id === trunkPoolId) ?? null,
    [tenantPools, trunkPoolId],
  );
  const adHocSipHint = useMemo(() => {
    if (!selectedPool) {
      return null;
    }
    const targetText = dialTarget.trim() || "the entered phone number";
    return `Will dial ${targetText} through ${selectedPool.tenant_label} (${selectedPool.trunk_pool_id}).`;
  }, [dialTarget, selectedPool]);
  const monitorRun = monitoredRun ?? null;
  const monitorPhase = monitorRun ? deriveRunMonitorPhase(monitorRun) : null;
  const recentEvents = useMemo(
    () => latestRunEvents(monitorRun?.events, 8),
    [monitorRun?.events]
  );
  const canMonitorAct =
    monitorRun?.state === "pending" ||
    monitorRun?.state === "running" ||
    monitorRun?.state === "judging";

  const handleCreate = async () => {
    if ((!scenarioId && !aiScenarioId) || harnessDegraded) return;
    setLoading(true);
    setError("");
    try {
      const createdRun = await createRun(
        scenarioId || undefined,
        dialTarget || undefined,
        transportProfileId || undefined,
        aiScenarioId || undefined,
        transportProfileId ? undefined : trunkPoolId || undefined,
      );
      setCreatedRunId(createdRun.run_id);
      setLaunchedAiScenarioId(aiScenarioId || null);
      onCreated();
    } catch (err) {
      setError(mapApiError(err, "Failed to create run").message);
    }
    setLoading(false);
  };

  async function handleMonitorStop() {
    if (!monitorRun || !window.confirm("Stop this run now? This will force-close it.")) {
      return;
    }
    setMonitorActionLoading("stop");
    setMonitorActionError("");
    try {
      await stopRun(monitorRun.run_id, "Stopped by operator from run monitor");
      await mutateMonitoredRun();
      onCreated();
    } catch (err) {
      setMonitorActionError(mapApiError(err, "Failed to stop run").message);
    } finally {
      setMonitorActionLoading((current) => (current === "stop" ? null : current));
    }
  }

  async function handleMonitorMarkFailed() {
    if (!monitorRun || !window.confirm("Mark this run as failed?")) {
      return;
    }
    setMonitorActionLoading("fail");
    setMonitorActionError("");
    try {
      await markRunFailed(monitorRun.run_id, "Marked failed by operator from run monitor");
      await mutateMonitoredRun();
      onCreated();
    } catch (err) {
      setMonitorActionError(mapApiError(err, "Failed to mark run failed").message);
    } finally {
      setMonitorActionLoading((current) => (current === "fail" ? null : current));
    }
  }

  if (monitorRun && monitorPhase) {
    const startedAt = monitorRun.created_at ? new Date(monitorRun.created_at).toLocaleString() : "—";
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center">
        <div className="absolute inset-0 bg-overlay/60 backdrop-blur-sm" onClick={onClose} />
        <div className="relative z-50 flex max-h-[min(90vh,860px)] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-border bg-bg-surface shadow-xl">
          <div className="border-b border-border px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-text-muted">Run Monitor</p>
                <h2 className="mt-1 text-lg font-semibold text-text-primary">
                  {launchedAiScenarioId ? "AI Scenario Run" : "Graph Scenario Run"}
                </h2>
                <p className="mt-1 font-mono text-xs text-text-muted">{monitorRun.run_id}</p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge value={monitorPhase.tone} label={monitorPhase.label} />
                <Link
                  href={`/runs/${monitorRun.run_id}`}
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

          <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[340px_minmax(0,1fr)]">
            <aside className="min-h-0 overflow-y-auto border-b border-border bg-bg-base/40 p-4 lg:border-b-0 lg:border-r">
              <div className="space-y-4 pb-2">
                <div className="grid gap-3">
                  <div className="rounded-xl border border-border bg-bg-surface px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Scenario</p>
                    <p className="mt-1 text-sm text-text-primary">
                      {monitorRun.scenario_id}
                      {launchedAiScenarioId ? ` · ${launchedAiScenarioId}` : ""}
                    </p>
                  </div>
                  <div className="rounded-xl border border-border bg-bg-surface px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Started</p>
                    <p className="mt-1 text-sm text-text-primary">{startedAt}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-bg-surface px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Transport</p>
                    <p className="mt-1 text-sm text-text-primary">
                      {monitorRun.transport_profile_id_at_start ??
                        transportProfileId ??
                        (trunkPoolId ? `${selectedPool?.tenant_label ?? "Selected Pool"} (${trunkPoolId})` : null) ??
                        "scenario/default transport"}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      {(monitorRun.dial_target_at_start ?? dialTarget) || "scenario/default target"}
                    </p>
                  </div>
                </div>

                {(monitorRun.error_code || monitorRun.end_reason) && (
                  <div className="rounded-xl border border-fail-border bg-fail-bg px-4 py-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-fail">Issue</p>
                    <p className="mt-1 text-sm text-fail">
                      {monitorRun.error_code ?? monitorRun.end_reason}
                    </p>
                  </div>
                )}

                <div className="min-h-0">
                  <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-text-muted">
                    Recent Events
                  </p>
                  <div className="space-y-2">
                    {recentEvents.length === 0 ? (
                      <p className="rounded-xl border border-border bg-bg-surface px-4 py-3 text-sm text-text-muted">
                        Waiting for the first run events.
                      </p>
                    ) : (
                      recentEvents.map((event, index) => (
                        <div
                          key={`${event.type}:${event.ts ?? index}`}
                          className="rounded-xl border border-border bg-bg-surface px-4 py-3"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-medium text-text-primary">
                              {formatRunEventLabel(event.type)}
                            </p>
                            <p className="text-[11px] text-text-muted">
                              {event.ts ? new Date(event.ts).toLocaleTimeString() : "now"}
                            </p>
                          </div>
                          <p className="mt-2 text-xs text-text-secondary">{describeRunEvent(event)}</p>
                          {event.detail ? (
                            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-[11px] text-text-muted">
                              {JSON.stringify(event.detail, null, 2)}
                            </pre>
                          ) : null}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </aside>

            <div className="min-h-0 overflow-y-auto p-4">
              <div className="flex min-h-0 flex-col space-y-4">
                <div className="flex min-h-0 flex-1 flex-col">
                  <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-text-muted">
                    Live Transcript
                  </p>
                  <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-bg-surface px-4 py-4">
                    <div className="min-h-full">
                      <Transcript
                        turns={monitorRun.conversation}
                        events={monitorRun.events ?? []}
                        scenario={monitoredScenario ?? null}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-border px-6 py-4">
            <p className="text-xs text-text-muted">
              The monitor updates automatically while the run is pending, running, or judging.
            </p>
            <div className="flex items-center gap-2">
              {canMonitorAct && canOperateRuns ? (
                <>
                  <Button
                    variant="secondary"
                    onClick={() => void handleMonitorMarkFailed()}
                    disabled={monitorActionLoading !== null}
                  >
                    {monitorActionLoading === "fail" ? "Marking Failed…" : "Mark Failed"}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void handleMonitorStop()}
                    disabled={monitorActionLoading !== null}
                  >
                    {monitorActionLoading === "stop" ? "Stopping…" : "Stop Run"}
                  </Button>
                </>
              ) : null}
              <Button variant="secondary" onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-overlay/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative z-50 w-full max-w-md rounded-lg border border-border bg-bg-surface p-6 shadow-xl">
        <h2 className="mb-4 text-base font-semibold text-text-primary">
          New Run
        </h2>
        <label className="block mb-3">
          <span className="text-xs text-text-secondary mb-1.5 block">
            Graph Scenario
          </span>
          <select
            data-testid="create-run-graph-scenario-id"
            value={scenarioId}
            disabled={Boolean(aiScenarioId)}
            onChange={(e) => {
              setScenarioId(e.target.value);
              if (e.target.value) {
                setAiScenarioId("");
              }
            }}
            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">Select a graph scenario…</option>
            {graphScenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        {aiEnabled ? (
          <label className="block mb-3">
            <span className="text-xs text-text-secondary mb-1.5 block">
              AI Scenario
            </span>
            <select
              data-testid="create-run-ai-scenario-id"
              value={aiScenarioId}
              disabled={Boolean(scenarioId)}
              onChange={(e) => {
                setAiScenarioId(e.target.value);
                if (e.target.value) {
                  setScenarioId("");
                }
              }}
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="">Select an AI scenario…</option>
              {aiScenarios?.map((scenario) => (
                <option key={scenario.ai_scenario_id} value={scenario.ai_scenario_id}>
                  {scenario.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {destinationsEnabled ? (
          <label className="block mb-3">
            <span className="text-xs text-text-secondary mb-1.5 block">
              Transport Profile
            </span>
            <select
              data-testid="create-run-destination-id"
              value={transportProfileId}
              onChange={(e) => {
                setTransportProfileId(e.target.value);
                if (e.target.value) {
                  setTrunkPoolId("");
                  setDialTarget("");
                  setAdHocOpen(false);
                }
              }}
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            >
              <option value="">Use scenario transport defaults</option>
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
        ) : null}
        {!transportProfileId && (
          <div className="mb-3">
            <button
              type="button"
              onClick={() => setAdHocOpen((o) => !o)}
              className="flex w-full items-center justify-between rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-secondary hover:bg-bg-elevated/80"
            >
              <span>Ad hoc SIP connection</span>
              <svg
                className={`h-4 w-4 transition-transform ${adHocOpen ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {adHocOpen && (
              <div className="mt-2 rounded-md border border-border bg-bg-base px-3 py-3 space-y-3">
                {tenantPools?.items.length ? (
                  <label className="block">
                    <span className="text-xs text-text-secondary mb-1.5 block">
                      SIP Trunk Pool
                    </span>
                    <select
                      data-testid="create-run-trunk-pool-id"
                      value={trunkPoolId}
                      onChange={(e) => setTrunkPoolId(e.target.value)}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                    >
                      <option value="">Use scenario/default SIP routing</option>
                      {tenantPools.items.map((pool) => (
                        <option
                          key={pool.trunk_pool_id}
                          value={pool.trunk_pool_id}
                          disabled={!pool.is_active}
                        >
                          {pool.tenant_label} ({pool.provider_name})
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <label className="block">
                  <span className="text-xs text-text-secondary mb-1.5 block">
                    Target Override
                  </span>
                  <input
                    data-testid="create-run-bot-endpoint"
                    type="text"
                    value={dialTarget}
                    onChange={(e) => setDialTarget(e.target.value)}
                    placeholder="Phone number or SIP URI"
                    className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
                  />
                  <p className="mt-1 text-[11px] text-text-muted">
                    Dialed number or SIP URI. Overrides the scenario default endpoint.
                  </p>
                </label>
                {(adHocSipHint ?? dispatchHint) && (
                  <p className="text-[11px] text-text-muted">{adHocSipHint ?? dispatchHint}</p>
                )}
              </div>
            )}
          </div>
        )}
        {transportProfileId && dispatchHint && (
          <div className="mb-3 flex items-start gap-2 rounded-md border border-border bg-bg-base px-3 py-2">
            <svg className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z" />
            </svg>
            <p className="text-[11px] leading-relaxed text-text-muted">{dispatchHint}</p>
          </div>
        )}
        {harnessDegraded ? (
          <p className="mb-3 text-xs text-warn">
            Harness worker is unavailable (state: {harnessState.replace("_", " ")}). New runs are
            temporarily disabled.
          </p>
        ) : null}
        {error && <p className="mb-3 text-xs text-fail">{error}</p>}
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={
              (!scenarioId && !aiScenarioId) ||
              loading ||
              harnessDegraded ||
              !canOperateRuns ||
              (!!trunkPoolId && !transportProfileId && !dialTarget.trim())
            }
          >
            {loading ? "Creating…" : "Create Run"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function RunsPage() {
  const { data: runs, error, mutate } = useRuns(100, 0);
  const { data: features } = useFeatures();
  const { data: scenarios } = useScenarios();
  const aiScenarioIds = useMemo(
    () =>
      new Set(
        (scenarios ?? [])
          .filter((row) => row.scenario_kind === "ai")
          .map((row) => row.id)
      ),
    [scenarios]
  );
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const destinationNames = useMemo(
    () => destinationNameMap(destinations),
    [destinations]
  );
  const harnessDegraded = features?.harness_degraded === true;
  const harnessState = features?.harness_state ?? "unknown";
  const [showModal, setShowModal] = useState(false);
  const [actioningRunId, setActioningRunId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const { canOperateRuns } = useDashboardAccess();

  const isActiveRunState = (state: string) =>
    state === "pending" || state === "running" || state === "judging";

  const handleStopRun = async (runId: string) => {
    if (!window.confirm("Stop this run now? This will force-close it.")) {
      return;
    }
    setActionError("");
    setActioningRunId(runId);
    try {
      await stopRun(runId, "Stopped by operator from runs list");
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to stop run").message);
    } finally {
      setActioningRunId((current) => (current === runId ? null : current));
    }
  };

  const handleMarkFailed = async (runId: string) => {
    if (!window.confirm("Mark this run as failed?")) {
      return;
    }
    setActionError("");
    setActioningRunId(runId);
    try {
      await markRunFailed(runId, "Marked failed by operator from runs list");
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to mark run failed").message);
    } finally {
      setActioningRunId((current) => (current === runId ? null : current));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Runs</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            Test run history — refreshes every 5s
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setShowModal(true)}
          disabled={harnessDegraded || !canOperateRuns}
          title={harnessDegraded ? `Harness unavailable (${harnessState})` : undefined}
        >
          New Run
        </Button>
      </div>
      {!canOperateRuns ? (
        <p className="text-xs text-text-muted">
          Read-only access. Creating, stopping, and failing runs require operator role or above.
        </p>
      ) : null}

      {showModal && (
        <NewRunModal
          onClose={() => setShowModal(false)}
          onCreated={() => mutate()}
          canOperateRuns={canOperateRuns}
        />
      )}

      {runs && runs.length > 0 && <RunsDashboard runs={runs} />}

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <span className="text-sm font-medium text-text-secondary">
              {runs?.length ?? 0} runs (latest 50)
            </span>
            {actionError ? <p className="text-xs text-fail">{actionError}</p> : null}
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {error && (
            <TableState kind="error" title="Failed to load runs" message={error.message} columns={7} />
          )}
          {!runs && !error && (
            <TableState kind="loading" message="Loading runs…" columns={7} rows={6} />
          )}
          {runs?.length === 0 && (
            <TableState
              kind="empty"
              title="No runs yet"
              message="Create a run to start collecting execution evidence."
              columns={7}
            />
          )}
          {runs && runs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                  <th className="px-5 py-3 text-left font-medium">Run ID</th>
                  <th className="px-5 py-3 text-left font-medium">Scenario</th>
                  <th className="px-5 py-3 text-left font-medium">State</th>
                  <th className="px-5 py-3 text-left font-medium hidden md:table-cell">
                    Source
                  </th>
                  <th className="px-5 py-3 text-left font-medium hidden md:table-cell">
                    Gate
                  </th>
                  <th className="px-5 py-3 text-left font-medium hidden lg:table-cell">
                    Created
                  </th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="border-b border-border last:border-0 hover:bg-bg-elevated transition-colors"
                  >
                    <td className="px-5 py-3 font-mono text-xs text-text-muted">
                      {run.run_id}
                    </td>
                    <td className="px-5 py-3 text-text-secondary">
                      <div>{run.scenario_id}</div>
                      <div className="mt-1 text-[10px] uppercase tracking-wide text-text-muted">
                        {aiScenarioIds.has(run.scenario_id) ? "AI" : "GRAPH"}
                      </div>
                      {run.transport_profile_id_at_start ||
                      run.destination_id_at_start ||
                      run.dial_target_at_start ||
                      run.capacity_scope_at_start ||
                      typeof run.capacity_limit_at_start === "number" ? (
                        <div className="mt-1 text-[10px] text-text-muted">
                          {run.transport_profile_id_at_start || run.destination_id_at_start
                            ? `transport: ${
                                destinationLabelForId(
                                  run.transport_profile_id_at_start ?? run.destination_id_at_start,
                                  destinationNames
                                ) ??
                                run.transport_profile_id_at_start ??
                                run.destination_id_at_start
                              }`
                            : "transport: —"}
                          {run.dial_target_at_start ? ` · target: ${run.dial_target_at_start}` : ""}
                          {run.capacity_scope_at_start
                            ? ` · scope: ${run.capacity_scope_at_start}`
                            : ""}
                          {typeof run.capacity_limit_at_start === "number"
                            ? ` · cap: ${run.capacity_limit_at_start}`
                            : ""}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge value={run.state} />
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell">
                      <AttributionBadge
                        triggerSource={run.trigger_source}
                        scheduleId={run.schedule_id}
                      />
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell">
                      <GateBadge result={run.gate_result} />
                    </td>
                    <td className="px-5 py-3 text-xs text-text-muted hidden lg:table-cell">
                      {run.created_at
                        ? new Date(run.created_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {isActiveRunState(run.state) && canOperateRuns ? (
                        <div className="mb-1 flex justify-end gap-2">
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => void handleStopRun(run.run_id)}
                            disabled={actioningRunId === run.run_id}
                          >
                            Stop
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => void handleMarkFailed(run.run_id)}
                            disabled={actioningRunId === run.run_id}
                          >
                            Mark Failed
                          </Button>
                        </div>
                      ) : null}
                      <Link
                        href={`/runs/${run.run_id}`}
                        className="text-xs text-brand hover:text-brand-hover transition-colors"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
