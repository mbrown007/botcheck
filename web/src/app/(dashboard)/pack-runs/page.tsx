"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  cancelPackRun,
  markPackRunFailed,
  useTransportProfiles,
  useFeatures,
  usePackRuns,
  usePacks,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TableState } from "@/components/ui/table-state";
import { destinationLabelForId, destinationNameMap } from "@/lib/destination-display";

function formatTs(value?: string | null): string {
  if (!value) {
    return "\u2014";
  }
  return new Date(value).toLocaleString();
}

export default function PackRunsPage() {
  const [selectedPackId, setSelectedPackId] = useState("");
  const [selectedState, setSelectedState] = useState("");
  const { data: features } = useFeatures();
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const { data: packs } = usePacks();
  const { data: runs, error, mutate } = usePackRuns({
    packId: selectedPackId || undefined,
    state: selectedState || undefined,
  });
  const [actioningRunId, setActioningRunId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");

  const packNameById = useMemo(() => {
    const mapping = new Map<string, string>();
    for (const pack of packs ?? []) {
      mapping.set(pack.pack_id, pack.name);
    }
    return mapping;
  }, [packs]);
  const destinationNames = useMemo(
    () => destinationNameMap(destinations),
    [destinations]
  );

  async function handleCancel(packRunId: string) {
    if (!window.confirm("Cancel this pack run?")) {
      return;
    }
    setActionError("");
    setActioningRunId(packRunId);
    try {
      await cancelPackRun(packRunId);
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to cancel pack run").message);
    } finally {
      setActioningRunId((current) => (current === packRunId ? null : current));
    }
  }

  async function handleMarkFailed(packRunId: string) {
    if (!window.confirm("Mark this pack run as failed?")) {
      return;
    }
    setActionError("");
    setActioningRunId(packRunId);
    try {
      await markPackRunFailed(packRunId, "Marked failed by operator from pack run list");
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to mark pack run failed").message);
    } finally {
      setActioningRunId((current) => (current === packRunId ? null : current));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Pack Runs</h1>
          <p className="mt-0.5 text-sm text-text-secondary">
            Historical execution and current state for pack dispatches.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">Filters</span>
        </CardHeader>
        <CardBody className="grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">Pack</span>
            <select
              value={selectedPackId}
              onChange={(event) => setSelectedPackId(event.target.value)}
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            >
              <option value="">All packs</option>
              {(packs ?? []).map((pack) => (
                <option key={pack.pack_id} value={pack.pack_id}>
                  {pack.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs text-text-secondary">State</span>
            <select
              value={selectedState}
              onChange={(event) => setSelectedState(event.target.value)}
              className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            >
              <option value="">All states</option>
              <option value="pending">pending</option>
              <option value="running">running</option>
              <option value="complete">complete</option>
              <option value="partial">partial</option>
              <option value="failed">failed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <span className="text-sm font-medium text-text-secondary">
              {runs?.length ?? 0} runs
            </span>
            {actionError ? <p className="text-xs text-fail">{actionError}</p> : null}
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {error && (
            <TableState
              kind="error"
              title="Failed to load pack runs"
              message={error.message}
              columns={8}
            />
          )}
          {!runs && !error && (
            <TableState kind="loading" message="Loading pack runs…" columns={8} rows={5} />
          )}
          {runs && runs.length === 0 && (
            <TableState
              kind="empty"
              title="No pack runs found."
              message="Run a pack to populate execution history and aggregate results."
              columns={8}
            />
          )}
          {runs && runs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                  <th className="px-5 py-3 text-left font-medium">Pack</th>
                  <th className="px-5 py-3 text-left font-medium hidden lg:table-cell">
                    Transport
                  </th>
                  <th className="px-5 py-3 text-left font-medium">State</th>
                  <th className="px-5 py-3 text-left font-medium">Gate</th>
                  <th className="px-5 py-3 text-left font-medium">Progress</th>
                  <th className="px-5 py-3 text-left font-medium">Trigger</th>
                  <th className="px-5 py-3 text-left font-medium">Created</th>
                  <th className="px-5 py-3 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.pack_run_id} className="border-b border-border last:border-0">
                    <td className="px-5 py-3">
                      <p className="text-sm text-text-primary">
                        {packNameById.get(run.pack_id) ?? run.pack_id}
                      </p>
                      <p className="font-mono text-[11px] text-text-muted">{run.pack_id}</p>
                    </td>
                    <td className="px-5 py-3 text-xs text-text-secondary hidden lg:table-cell">
                      {run.transport_profile_id || run.destination_id
                        ? destinationLabelForId(
                            run.transport_profile_id ?? run.destination_id,
                            destinationNames
                          ) ??
                          run.transport_profile_id ??
                          run.destination_id
                        : "—"}
                      {run.dial_target ? ` · ${run.dial_target}` : ""}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge value={run.state} label={run.state} />
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge value={run.gate_outcome} label={run.gate_outcome} />
                    </td>
                    <td className="px-5 py-3 text-xs text-text-secondary font-mono">
                      {run.completed}/{run.total_scenarios}
                    </td>
                    <td className="px-5 py-3 text-xs text-text-secondary font-mono">
                      {run.trigger_source}
                    </td>
                    <td className="px-5 py-3 text-xs text-text-muted">
                      {formatTs(run.created_at)}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {(run.state === "pending" || run.state === "running") ? (
                          <>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => void handleCancel(run.pack_run_id)}
                              disabled={actioningRunId === run.pack_run_id}
                            >
                              Cancel
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => void handleMarkFailed(run.pack_run_id)}
                              disabled={actioningRunId === run.pack_run_id}
                            >
                              Mark Failed
                            </Button>
                          </>
                        ) : null}
                        <Link
                          href={`/pack-runs/${run.pack_run_id}`}
                          className="text-brand hover:text-brand-strong text-xs font-mono"
                        >
                          View
                        </Link>
                      </div>
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
