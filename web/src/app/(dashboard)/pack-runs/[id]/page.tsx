"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  cancelPackRun,
  markPackRunFailed,
  useTransportProfiles,
  useFeatures,
  usePackRun,
  usePackRunChildren,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import type { PackRunDetail } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { PackRunAiLatencyCard } from "./_components/PackRunAiLatencyCard";
import { PackRunChildrenTable } from "./_components/PackRunChildrenTable";
import { PackRunDetailHeader } from "./_components/PackRunDetailHeader";
import { PackRunHeatmapCard } from "./_components/PackRunHeatmapCard";
import { PackRunSummaryGrid } from "./_components/PackRunSummaryGrid";
import { destinationLabelForId, destinationNameMap } from "@/lib/destination-display";
import { aiLatencyDegradedComponents, formatLatencyMs } from "@/lib/run-ai-latency";

const PAGE_SIZE = 50;

function childStateValue(row: { run_state?: string | null; state: string }): string {
  return row.run_state || row.state;
}

function formatTriggerSource(detail: PackRunDetail): string {
  if (detail.trigger_source === "scheduled") {
    return detail.schedule_id ? `scheduled:${detail.schedule_id}` : "scheduled";
  }
  return detail.trigger_source;
}

function formatTs(value?: string | null): string {
  if (!value) {
    return "\u2014";
  }
  return new Date(value).toLocaleString();
}

function formatDuration(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "\u2014";
  }
  if (value < 60) {
    return `${value.toFixed(1)}s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}m ${seconds.toFixed(1)}s`;
}

function formatHeatmapTrend(current?: number | null, previous?: number | null): {
  label: string;
  toneClass: string;
} {
  if (
    typeof current !== "number" ||
    !Number.isFinite(current) ||
    typeof previous !== "number" ||
    !Number.isFinite(previous)
  ) {
    return { label: "\u2014", toneClass: "text-text-muted" };
  }
  const delta = current - previous;
  if (Math.abs(delta) < 0.0001) {
    return { label: "\u2192 0.0000", toneClass: "text-text-muted" };
  }
  if (delta > 0) {
    return { label: `\u2191 +${delta.toFixed(4)}`, toneClass: "text-pass" };
  }
  return { label: `\u2193 ${delta.toFixed(4)}`, toneClass: "text-fail" };
}

export default function PackRunDetailPage() {
  const params = useParams<{ id: string }>();
  const packRunId = decodeURIComponent(params?.id ?? "");
  const { data: features } = useFeatures();
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const { data: detail, error, mutate } = usePackRun(packRunId || null);
  const [sortMode, setSortMode] = useState<
    "failures_first" | "order" | "state" | "gate_result" | "scenario_id"
  >("failures_first");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [failuresOnly, setFailuresOnly] = useState(false);
  const [page, setPage] = useState(1);
  const {
    data: children,
    error: childrenError,
    mutate: mutateChildren,
  } = usePackRunChildren(packRunId || null, {
    failuresOnly,
    sortBy: sortMode,
    sortDir,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const [actionLoading, setActionLoading] = useState<"cancel" | "fail" | null>(null);
  const [actionError, setActionError] = useState("");
  const destinationNames = useMemo(
    () => destinationNameMap(destinations),
    [destinations]
  );
  const degradedAiComponents = useMemo(
    () => aiLatencyDegradedComponents(features?.provider_circuits),
    [features?.provider_circuits]
  );

  const rows = children?.items ?? [];
  const totalRows = children?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const pageStart = totalRows === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = totalRows === 0 ? 0 : Math.min(page * PAGE_SIZE, totalRows);

  useEffect(() => {
    setPage(1);
  }, [sortMode, sortDir, failuresOnly, packRunId]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const progressPct =
    detail && detail.total_scenarios > 0
      ? Math.round((detail.completed / detail.total_scenarios) * 100)
      : 0;
  const pendingOrRunning = detail
    ? Math.max(0, detail.total_scenarios - detail.completed)
    : 0;
  const passRatePct =
    detail && detail.total_scenarios > 0
      ? Math.round((detail.passed / detail.total_scenarios) * 100)
      : 0;
  const canCancel = detail?.state === "pending" || detail?.state === "running";
  const canMarkFailed = detail?.state === "pending" || detail?.state === "running";

  const heatmapRows = useMemo(
    () => Object.entries(detail?.dimension_heatmap ?? {}).sort((a, b) => a[0].localeCompare(b[0])),
    [detail]
  );
  const transportProfileLabel = destinationLabelForId(
    detail?.transport_profile_id ?? detail?.destination_id,
    destinationNames
  );

  async function handleCancel() {
    if (!packRunId) {
      return;
    }
    setActionError("");
    setActionLoading("cancel");
    try {
      await cancelPackRun(packRunId);
      await Promise.all([mutate(), mutateChildren()]);
    } catch (err) {
      setActionError(mapApiError(err, "Failed to cancel pack run").message);
    } finally {
      setActionLoading((current) => (current === "cancel" ? null : current));
    }
  }

  async function handleMarkFailed() {
    if (!packRunId) {
      return;
    }
    if (!window.confirm("Mark this pack run as failed?")) {
      return;
    }
    setActionError("");
    setActionLoading("fail");
    try {
      await markPackRunFailed(packRunId, "Marked failed by operator from pack run detail");
      await Promise.all([mutate(), mutateChildren()]);
    } catch (err) {
      setActionError(mapApiError(err, "Failed to mark pack run failed").message);
    } finally {
      setActionLoading((current) => (current === "fail" ? null : current));
    }
  }

  return (
    <div className="space-y-6">
      <PackRunDetailHeader
        packRunId={packRunId}
        packName={detail?.pack_name}
        createdAt={detail?.created_at}
        failuresOnly={failuresOnly}
        canCancel={canCancel}
        canMarkFailed={canMarkFailed}
        actionLoading={actionLoading}
        onToggleFailuresOnly={() => setFailuresOnly((prev) => !prev)}
        onCancel={() => void handleCancel()}
        onMarkFailed={() => void handleMarkFailed()}
        formatTs={formatTs}
      />

      {(error || childrenError) && (
        <Card>
          <CardBody>
            <p className="text-sm text-fail">
              Failed to load pack run details: {error?.message ?? childrenError?.message}
            </p>
          </CardBody>
        </Card>
      )}

      {detail ? (
        <PackRunSummaryGrid
          detail={detail}
          transportProfileLabel={transportProfileLabel}
          progressPct={progressPct}
          pendingOrRunning={pendingOrRunning}
          passRatePct={passRatePct}
          formatTriggerSource={formatTriggerSource}
          formatTs={formatTs}
        />
      ) : null}

      <PackRunHeatmapCard
        rows={heatmapRows}
        previousPackRunId={detail?.previous_pack_run_id}
        previousHeatmap={detail?.previous_dimension_heatmap}
        formatHeatmapTrend={formatHeatmapTrend}
      />

      <PackRunAiLatencyCard
        summary={children?.ai_latency_summary}
        providerDegraded={features?.provider_degraded === true}
        degradedAiComponents={degradedAiComponents}
        formatLatencyMs={formatLatencyMs}
      />

      <PackRunChildrenTable
        rows={rows}
        totalRows={totalRows}
        pageStart={pageStart}
        pageEnd={pageEnd}
        page={page}
        totalPages={totalPages}
        sortMode={sortMode}
        sortDir={sortDir}
        actionError={actionError}
        loading={!children && !childrenError}
        onSetSortMode={setSortMode}
        onSetSortDir={setSortDir}
        onPrevPage={() => setPage((current) => Math.max(1, current - 1))}
        onNextPage={() => setPage((current) => Math.min(totalPages, current + 1))}
        formatDuration={formatDuration}
        childStateValue={childStateValue}
      />
    </div>
  );
}
