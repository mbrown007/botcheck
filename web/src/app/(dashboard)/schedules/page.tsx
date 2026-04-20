"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CalendarClock,
  ChevronDown,
  Edit3,
  History,
  Pause,
  Play,
  RefreshCw,
  TimerReset,
  Trash2,
} from "lucide-react";
import {
  previewSchedule,
  useAIScenarios,
  useFeatures,
  useSchedules,
  useTransportProfiles,
  type ScheduleResponse,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import { SchedulesDashboard } from "@/components/schedules/schedules-dashboard";
import { ScheduleEditorModal } from "@/components/schedules/ScheduleEditorModal";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { destinationLabelForId, destinationNameMap } from "@/lib/destination-display";
import {
  formatScheduleTargetLabel,
  scheduleBotEndpointOverride,
  scheduleDestinationOverrideId,
} from "@/lib/schedule-target";
import { formatTs, lastStatusVariant } from "@/components/schedules/schedule-form-helpers";
import { useScheduleActions } from "@/app/(dashboard)/schedules/hooks/useScheduleActions";
import { useDashboardAccess } from "@/lib/current-user";
import {
  buildScheduleTimeline,
  bucketScheduleOccurrences,
  type ScheduleTimelineView,
} from "@/lib/schedule-timeline";

type TimelinePreviewMap = Record<string, string[]>;

function compactDateTime(value?: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function ScheduleMetric({
  label,
  value,
  accent,
  subtext,
}: {
  label: string;
  value: string;
  accent?: string;
  subtext?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-bg-elevated px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">{label}</p>
      <p className={`mt-1 text-sm font-semibold ${accent ?? "text-text-primary"}`}>{value}</p>
      {subtext ? <p className="mt-1 text-[11px] text-text-muted">{subtext}</p> : null}
    </div>
  );
}

function timelineCellClasses(count: number): string {
  if (count >= 3) {
    return "bg-brand";
  }
  if (count === 2) {
    return "bg-brand/70";
  }
  if (count === 1) {
    return "bg-brand/35";
  }
  return "bg-bg-elevated";
}

export default function SchedulesPage() {
  const { data: schedules, error, mutate } = useSchedules();
  const { data: features } = useFeatures();
  const aiEnabled = features?.ai_scenarios_enabled === true;
  const { data: aiScenarios } = useAIScenarios(aiEnabled);
  const aiScenarioIdSet = useMemo(
    () => new Set((aiScenarios ?? []).map((scenario) => scenario.ai_scenario_id)),
    [aiScenarios],
  );
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const destinationNames = useMemo(() => destinationNameMap(destinations), [destinations]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ScheduleResponse | null>(null);
  const [timelineView, setTimelineView] = useState<ScheduleTimelineView>("24h");
  const [timelineFilter, setTimelineFilter] = useState("all");
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState("");
  const [timelinePreviews, setTimelinePreviews] = useState<TimelinePreviewMap>({});
  const [focusedScheduleId, setFocusedScheduleId] = useState<string | null>(null);
  const [timelineOpen, setTimelineOpen] = useState(true);
  const actions = useScheduleActions(async () => {
    await mutate();
  });
  const { canManageSchedules } = useDashboardAccess();

  const sortedSchedules = useMemo(() => {
    return [...(schedules ?? [])].sort((left, right) => {
      if (left.active !== right.active) {
        return left.active ? -1 : 1;
      }
      return (left.next_run_at ?? "").localeCompare(right.next_run_at ?? "");
    });
  }, [schedules]);

  const timelineSummary = useMemo(() => buildScheduleTimeline(timelineView), [timelineView]);
  const timelineSchedules = useMemo(() => {
    if (!sortedSchedules.length) {
      return [];
    }
    if (timelineFilter === "all") {
      return sortedSchedules;
    }
    return sortedSchedules.filter((schedule) => schedule.schedule_id === timelineFilter);
  }, [sortedSchedules, timelineFilter]);

  useEffect(() => {
    if (!timelineSchedules.length) {
      setTimelinePreviews({});
      return;
    }
    let cancelled = false;
    setTimelineLoading(true);
    setTimelineError("");
    void Promise.allSettled(
      timelineSchedules.map(async (schedule) => {
        const preview = await previewSchedule(
          schedule.cron_expr,
          schedule.timezone,
          timelineSummary.previewCount,
        );
        return [schedule.schedule_id, preview.occurrences] as const;
      }),
    )
      .then((results) => {
        if (cancelled) {
          return;
        }
        const next: TimelinePreviewMap = {};
        let rejected = 0;
        for (const result of results) {
          if (result.status === "fulfilled") {
            const [scheduleId, occurrences] = result.value;
            next[scheduleId] = occurrences;
          } else {
            rejected += 1;
          }
        }
        setTimelinePreviews(next);
        setTimelineError(rejected > 0 ? "Some schedule previews could not be loaded." : "");
      })
      .finally(() => {
        if (!cancelled) {
          setTimelineLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [timelineSchedules, timelineSummary.previewCount]);

  useEffect(() => {
    if (!focusedScheduleId) {
      return;
    }
    const element = document.getElementById(`schedule-card-${focusedScheduleId}`);
    if (!element) {
      return;
    }
    element.scrollIntoView({ behavior: "smooth", block: "start" });
    const timeout = window.setTimeout(() => setFocusedScheduleId(null), 1800);
    return () => window.clearTimeout(timeout);
  }, [focusedScheduleId]);

  return (
    <TooltipProvider delayDuration={120}>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text-primary">Schedules</h1>
            <p className="mt-0.5 text-sm text-text-secondary">
              Autonomous schedule dispatch with timezone-aware run timing.
            </p>
          </div>
          {canManageSchedules ? (
            <Button variant="primary" onClick={() => setShowCreate(true)}>
              New Schedule
            </Button>
          ) : null}
        </div>
        {!canManageSchedules ? (
          <p className="text-xs text-text-muted">
            Read-only access. Schedule create, edit, pause, and delete require editor role or above.
          </p>
        ) : null}

        {showCreate && canManageSchedules ? (
          <ScheduleEditorModal
            mode="create"
            onClose={() => setShowCreate(false)}
            actions={actions}
          />
        ) : null}

        {editingSchedule && canManageSchedules ? (
          <ScheduleEditorModal
            mode="edit"
            schedule={editingSchedule}
            onClose={() => setEditingSchedule(null)}
            actions={actions}
          />
        ) : null}

        {actions.actionError ? <p className="text-sm text-fail">{actions.actionError}</p> : null}

        {schedules ? <SchedulesDashboard schedules={schedules} /> : null}

        <Card>
          <CardHeader>
            <div className="w-full space-y-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <button
                  type="button"
                  className="flex items-center gap-2 text-left"
                  onClick={() => setTimelineOpen((prev) => !prev)}
                >
                  <ChevronDown
                    className={`h-4 w-4 text-text-muted transition-transform duration-200 ${timelineOpen ? "" : "-rotate-90"}`}
                  />
                  <div>
                    <p className="text-sm font-medium text-text-secondary">Run timeline</p>
                    <p className="mt-1 text-xs text-text-muted">
                      Compact preview of when schedules will fire over the next 24 hours, 7 days, or 30 days.
                    </p>
                  </div>
                </button>
                {timelineOpen ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {(["24h", "7d", "30d"] as ScheduleTimelineView[]).map((view) => (
                      <Button
                        key={view}
                        type="button"
                        size="sm"
                        variant={timelineView === view ? "primary" : "secondary"}
                        onClick={() => setTimelineView(view)}
                      >
                        {view === "30d" ? "Month" : view}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </div>
              {timelineOpen ? (
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                    <CalendarClock className="h-4 w-4" />
                    <span>{timelineSchedules.length} schedule lane{timelineSchedules.length === 1 ? "" : "s"}</span>
                    {timelineLoading ? (
                      <span className="inline-flex items-center gap-1">
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        refreshing preview
                      </span>
                    ) : null}
                  </div>
                  <label className="flex items-center gap-2 text-sm text-text-secondary">
                    <span className="text-xs uppercase tracking-[0.14em] text-text-muted">Filter</span>
                    <select
                      data-testid="schedule-timeline-filter"
                      className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                      value={timelineFilter}
                      onChange={(event) => setTimelineFilter(event.target.value)}
                    >
                      <option value="all">All schedules</option>
                      {sortedSchedules.map((schedule) => (
                        <option key={schedule.schedule_id} value={schedule.schedule_id}>
                          {schedule.name?.trim() || schedule.schedule_id}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ) : null}
            </div>
          </CardHeader>
          {timelineOpen ? <CardBody>
            {timelineError ? <p className="mb-4 text-sm text-fail">{timelineError}</p> : null}
            {!schedules && !error ? (
              <TableState kind="loading" message="Loading schedule timeline…" columns={1} rows={3} />
            ) : null}
            {schedules?.length === 0 ? (
              <TableState
                kind="empty"
                title="No schedules yet"
                message="Create a schedule to see its preview lane here."
                columns={1}
              />
            ) : null}
            {timelineSchedules.length > 0 ? (
              <div className="overflow-x-auto">
                <div
                  className="grid min-w-[860px] gap-x-2 gap-y-3"
                  style={{
                    gridTemplateColumns: `220px repeat(${timelineSummary.slots.length}, minmax(0, 1fr))`,
                  }}
                >
                  <div />
                  {timelineSummary.slots.map((slot) => (
                    <div
                      key={slot.startMs}
                      className="text-center text-[11px] uppercase tracking-[0.12em] text-text-muted"
                      title={slot.label}
                    >
                      {slot.shortLabel}
                    </div>
                  ))}

                  {timelineSchedules.map((schedule) => {
                    const targetLabel = formatScheduleTargetLabel(schedule, aiScenarioIdSet);
                    const counts = bucketScheduleOccurrences(
                      timelinePreviews[schedule.schedule_id] ?? [],
                      timelineSummary.slots,
                    );
                    return (
                      <div
                        key={schedule.schedule_id}
                        className="contents"
                      >
                        <button
                          type="button"
                          className="rounded-xl border border-border bg-bg-elevated px-3 py-3 text-left transition-colors hover:border-border-focus hover:bg-bg-base"
                          onClick={() => setFocusedScheduleId(schedule.schedule_id)}
                        >
                          <p className="text-sm font-medium text-text-primary">
                            {schedule.name?.trim() || targetLabel}
                          </p>
                          <p className="mt-1 text-xs text-text-muted">{targetLabel}</p>
                        </button>
                        {counts.map((count, index) => (
                          <button
                            type="button"
                            key={`${schedule.schedule_id}-${timelineSummary.slots[index]?.startMs}`}
                            className={`h-10 rounded-md border border-border/70 ${timelineCellClasses(count)}`}
                            title={`${timelineSummary.slots[index]?.label}: ${count} scheduled run${count === 1 ? "" : "s"}`}
                            onClick={() => setFocusedScheduleId(schedule.schedule_id)}
                          />
                        ))}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </CardBody> : null}
        </Card>

        <div className="grid gap-5 xl:grid-cols-2">
          {error ? (
            <Card className="xl:col-span-2">
              <CardBody>
                <TableState
                  kind="error"
                  title="Failed to load schedules"
                  message={error.message}
                  columns={1}
                />
              </CardBody>
            </Card>
          ) : null}
          {!schedules && !error ? (
            <Card className="xl:col-span-2">
              <CardBody>
                <TableState kind="loading" message="Loading schedules…" columns={1} rows={4} />
              </CardBody>
            </Card>
          ) : null}
          {schedules?.length === 0 ? (
            <Card className="xl:col-span-2">
              <CardBody>
                <TableState
                  kind="empty"
                  title="No schedules yet"
                  message="Create a schedule to enable autonomous production checks."
                  columns={1}
                />
              </CardBody>
            </Card>
          ) : null}
          {sortedSchedules.map((schedule) => {
            const targetLabel = formatScheduleTargetLabel(schedule, aiScenarioIdSet);
            const scheduleLabel = schedule.name?.trim() || targetLabel;
            const transportProfileId = scheduleDestinationOverrideId(schedule);
            const dialTarget = scheduleBotEndpointOverride(schedule);
            const transportProfileLabel = destinationLabelForId(
              transportProfileId,
              destinationNames,
            );
            return (
              <Card
                key={schedule.schedule_id}
                data-testid={`schedule-card-${schedule.schedule_id}`}
                id={`schedule-card-${schedule.schedule_id}`}
                className={`overflow-hidden transition-shadow ${
                  focusedScheduleId === schedule.schedule_id ? "ring-2 ring-brand/40 shadow-lg" : ""
                }`}
              >
                <CardHeader>
                  <div className="flex w-full items-start justify-between gap-4">
                    <div>
                      <p className="text-base font-semibold text-text-primary">{scheduleLabel}</p>
                      <p className="mt-1 text-xs font-mono text-text-secondary">{targetLabel}</p>
                      <p className="mt-1 text-[11px] text-text-muted">{schedule.schedule_id}</p>
                    </div>
                    <StatusBadge
                      value={schedule.active ? "pass" : "pending"}
                      label={schedule.active ? "active" : "paused"}
                    />
                  </div>
                </CardHeader>
                <CardBody className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <ScheduleMetric
                      label="Last run"
                      value={compactDateTime(schedule.last_run_at)}
                    />
                    <ScheduleMetric
                      label="Next due"
                      value={compactDateTime(schedule.next_run_at)}
                      accent={schedule.active ? "text-brand" : "text-text-primary"}
                    />
                    <ScheduleMetric
                      label="Last status"
                      value={schedule.last_status ?? "—"}
                      accent={
                        lastStatusVariant(schedule.last_status) === "fail"
                          ? "text-fail"
                          : lastStatusVariant(schedule.last_status) === "warn"
                            ? "text-warn"
                            : lastStatusVariant(schedule.last_status) === "pass"
                              ? "text-pass"
                              : "text-text-primary"
                      }
                      subtext={schedule.last_run_outcome ? `run: ${schedule.last_run_outcome}` : undefined}
                    />
                    <ScheduleMetric
                      label="Failure streak"
                      value={String(schedule.consecutive_failures ?? 0)}
                      accent={(schedule.consecutive_failures ?? 0) > 1 ? "text-fail" : (schedule.consecutive_failures ?? 0) > 0 ? "text-warn" : "text-pass"}
                      subtext={schedule.retry_on_failure ? "retry enabled" : "no retry"}
                    />
                  </div>

                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <div className="space-y-2 rounded-xl border border-border bg-bg-elevated px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                        Schedule
                      </p>
                      <p className="font-mono text-xs text-text-primary">{schedule.cron_expr}</p>
                      <p className="text-xs text-text-secondary">{schedule.timezone}</p>
                    </div>
                    <div className="space-y-2 rounded-xl border border-border bg-bg-elevated px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
                        Routing
                      </p>
                      {transportProfileId ? (
                        <p className="text-xs text-text-secondary">
                          transport: {transportProfileLabel ?? transportProfileId}
                        </p>
                      ) : (
                        <p className="text-xs text-text-muted">No transport override</p>
                      )}
                      {dialTarget ? (
                        <p className="break-all text-xs text-text-secondary">dial target: {dialTarget}</p>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
                    <div className="flex items-center gap-2 text-xs text-text-muted">
                      <TimerReset className="h-3.5 w-3.5" />
                      {schedule.retry_on_failure
                        ? "Single-scenario retry on failure is enabled."
                        : "No retry fallback configured."}
                    </div>
                    <div className="inline-flex items-center gap-1.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Link
                            href={`/schedules/${schedule.schedule_id}/history`}
                            aria-label="History"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-bg-elevated text-text-primary transition-colors hover:bg-bg-base"
                          >
                            <History className="h-3.5 w-3.5" />
                          </Link>
                        </TooltipTrigger>
                        <TooltipContent>History</TooltipContent>
                      </Tooltip>
                      {canManageSchedules ? (
                        <>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                size="icon"
                                variant="secondary"
                                aria-label="Edit"
                                disabled={actions.busyId === schedule.schedule_id}
                                onClick={() => setEditingSchedule(schedule)}
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Edit</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                size="icon"
                                variant="secondary"
                                aria-label={schedule.active ? "Pause" : "Resume"}
                                disabled={actions.busyId === schedule.schedule_id}
                                onClick={() =>
                                  actions.toggleActive(schedule.schedule_id, !schedule.active)
                                }
                              >
                                {schedule.active ? (
                                  <Pause className="h-3.5 w-3.5" />
                                ) : (
                                  <Play className="h-3.5 w-3.5" />
                                )}
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>{schedule.active ? "Pause" : "Resume"}</TooltipContent>
                          </Tooltip>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                size="icon"
                                variant="destructive"
                                aria-label="Delete"
                                disabled={actions.busyId === schedule.schedule_id}
                                onClick={() => actions.removeSchedule(schedule.schedule_id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Delete</TooltipContent>
                          </Tooltip>
                        </>
                      ) : null}
                    </div>
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </div>
    </TooltipProvider>
  );
}
