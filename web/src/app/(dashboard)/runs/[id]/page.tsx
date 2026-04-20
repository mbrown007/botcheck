"use client";

import { use, useEffect, useMemo, useState } from "react";
import {
  getRunRecordingBlob,
  markRunFailed,
  stopRun,
  useTransportProfiles,
  useFeatures,
  useGate,
  useRun,
  useScenario,
  useScenarios,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import { GateBadge } from "@/components/runs/gate-badge";
import { FindingsExplorer } from "@/components/runs/findings-explorer";
import { ScoreCards } from "@/components/runs/score-cards";
import { Transcript } from "@/components/runs/transcript";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { RunAiContextCard } from "./_components/RunAiContextCard";
import { RunAiLatencyCard } from "./_components/RunAiLatencyCard";
import { RunDetailHeader } from "./_components/RunDetailHeader";
import { RunJudgingBanner } from "./_components/RunJudgingBanner";
import { RunRecordingCard } from "./_components/RunRecordingCard";
import { RunSourceMetadata } from "./_components/RunSourceMetadata";
import { destinationLabelForId, destinationNameMap } from "@/lib/destination-display";
import { extractAiContextFromRunEvents } from "@/lib/run-ai-context";
import {
  aiLatencyDegradedComponents,
  deriveAiLatencyBreakdown,
  formatLatencyMs,
  hasAiLatencySamples,
} from "@/lib/run-ai-latency";

interface Props {
  params: Promise<{ id: string }>;
}

export default function RunDetailPage({ params }: Props) {
  const { id } = use(params);
  const { data: run, error: runError, mutate } = useRun(id);
  const { data: features } = useFeatures();
  const { data: scenarios } = useScenarios();
  const aiScenarioIds = useMemo(() => {
    const ids = new Set<string>();
    for (const row of scenarios ?? []) {
      if (row.scenario_kind === "ai") {
        const normalized = row.id.trim();
        if (normalized) {
          ids.add(normalized);
        }
      }
    }
    return ids;
  }, [scenarios]);
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const destinationNames = useMemo(
    () => destinationNameMap(destinations),
    [destinations]
  );
  const aiContext = run ? extractAiContextFromRunEvents(run.events) : null;
  const scenarioKindLabel: "AI" | "GRAPH" =
    run && (aiScenarioIds.has(run.scenario_id) || aiContext) ? "AI" : "GRAPH";
  const aiLatency = useMemo(
    () => (run ? deriveAiLatencyBreakdown(run.conversation) : null),
    [run],
  );
  const showLatencyCard = hasAiLatencySamples(aiLatency);
  const degradedAiComponents = useMemo(
    () => aiLatencyDegradedComponents(features?.provider_circuits),
    [features?.provider_circuits],
  );
  const { data: scenario } = useScenario(run?.scenario_id ?? null);
  const { data: gate } = useGate(
    run?.state === "complete" || run?.state === "failed" || run?.state === "error"
      ? id
      : null
  );
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState<string>("");
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [audioCurrentTimeMs, setAudioCurrentTimeMs] = useState(0);
  const [cacheBannerDismissed, setCacheBannerDismissed] = useState(false);
  const [actionLoading, setActionLoading] = useState<"stop" | "fail" | null>(null);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    return () => {
      if (recordingUrl) {
        URL.revokeObjectURL(recordingUrl);
      }
    };
  }, [recordingUrl]);

  useEffect(() => {
    setRecordingError("");
    setRecordingLoading(false);
    setRecordingUrl((prev) => {
      if (prev) {
        URL.revokeObjectURL(prev);
      }
      return null;
    });
  }, [id, run?.recording_s3_key]);

  useEffect(() => {
    setCacheBannerDismissed(false);
  }, [id, run?.tts_cache_status_at_start]);

  if (runError) {
    return (
      <p className="text-sm text-fail">
        Failed to load run: {runError.message}
      </p>
    );
  }

  if (!run) {
    return <p className="text-sm text-text-muted">Loading…</p>;
  }
  const runData = run;
  const canOperatorAct =
    runData.state === "pending" || runData.state === "running" || runData.state === "judging";

  async function loadRecording() {
    if (!runData.recording_s3_key) {
      return;
    }
    setRecordingLoading(true);
    setRecordingError("");
    try {
      const blob = await getRunRecordingBlob(runData.run_id);
      if (recordingUrl) {
        URL.revokeObjectURL(recordingUrl);
      }
      setRecordingUrl(URL.createObjectURL(blob));
    } catch (err) {
      setRecordingError(err instanceof Error ? err.message : "Failed to load recording");
    } finally {
      setRecordingLoading(false);
    }
  }

  async function handleStopRun() {
    if (!window.confirm("Stop this run now? This will force-close it.")) {
      return;
    }
    setActionLoading("stop");
    setActionError("");
    try {
      await stopRun(runData.run_id, "Stopped by operator from run detail");
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to stop run").message);
    } finally {
      setActionLoading((current) => (current === "stop" ? null : current));
    }
  }

  async function handleMarkFailed() {
    if (!window.confirm("Mark this run as failed?")) {
      return;
    }
    setActionLoading("fail");
    setActionError("");
    try {
      await markRunFailed(runData.run_id, "Marked failed by operator from run detail");
      await mutate();
    } catch (err) {
      setActionError(mapApiError(err, "Failed to mark run failed").message);
    } finally {
      setActionLoading((current) => (current === "fail" ? null : current));
    }
  }

  const isComplete =
    runData.state === "complete" || runData.state === "failed" || runData.state === "error";
  const isJudging = runData.state === "judging" || runData.state === "running";
  const rubricDimensions = (scenario?.scoring?.rubric ?? []).map((item) => item.dimension);
  const cacheStatusAtStart = runData.tts_cache_status_at_start;
  const transportProfileLabel = destinationLabelForId(
    runData.transport_profile_id_at_start ?? runData.destination_id_at_start,
    destinationNames
  );
  const showCacheWarmupBanner = Boolean(
    features?.tts_cache_enabled &&
      cacheStatusAtStart &&
      cacheStatusAtStart !== "warm" &&
      !cacheBannerDismissed
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <RunDetailHeader
        runId={runData.run_id}
        scenarioId={runData.scenario_id}
        scenarioKindLabel={scenarioKindLabel}
        state={runData.state}
        triggerSource={runData.trigger_source}
        scheduleId={runData.schedule_id}
        gateResult={runData.gate_result}
        canOperatorAct={canOperatorAct}
        actionLoading={actionLoading}
        onStop={() => void handleStopRun()}
        onMarkFailed={() => void handleMarkFailed()}
      />
      {actionError ? <p className="text-sm text-fail">{actionError}</p> : null}

      <RunSourceMetadata
        createdAt={runData.created_at}
        triggeredBy={runData.triggered_by}
        transport={runData.transport}
        scheduleId={runData.schedule_id}
        transportProfileLabel={transportProfileLabel}
        transportProfileIdAtStart={
          runData.transport_profile_id_at_start ?? runData.destination_id_at_start
        }
        dialTargetAtStart={runData.dial_target_at_start}
        capacityScopeAtStart={runData.capacity_scope_at_start}
        capacityLimitAtStart={runData.capacity_limit_at_start}
      />

      {showCacheWarmupBanner && (
        <div className="rounded-lg border border-warn-border bg-warn-bg px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm text-warn">
              This run started while scenario cache status was{" "}
              <span className="font-mono">{cacheStatusAtStart}</span>. Early turns may include
              synthesis latency while cache warming completes.
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCacheBannerDismissed(true)}
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      <RunAiContextCard aiContext={aiContext} />

      <RunAiLatencyCard
        aiLatency={showLatencyCard ? aiLatency : null}
        providerDegraded={features?.provider_degraded === true}
        degradedAiComponents={degradedAiComponents}
        formatLatencyMs={formatLatencyMs}
        title={scenarioKindLabel === "AI" ? "AI Runtime Latency" : "Voice Runtime Latency"}
      />

      <RunJudgingBanner visible={isJudging} />

      {/* Gate summary */}
      {isComplete && gate && (
        <Card>
          <CardBody className="flex items-start gap-4">
            <GateBadge result={gate.gate_result} className="mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm text-text-primary">{gate.summary || "No summary available."}</p>
              {gate.failed_dimensions.length > 0 && (
                <p className="mt-1 text-xs text-fail">
                  Failed: {gate.failed_dimensions.join(", ")}
                </p>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Score cards */}
      {isComplete && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-text-secondary uppercase tracking-wide">
            Score Dimensions
          </h2>
          <ScoreCards
            scores={runData.scores}
            failedDimensions={gate?.failed_dimensions ?? runData.failed_dimensions}
            dimensionKeys={rubricDimensions}
          />
        </section>
      )}

      <RunRecordingCard
        recordingS3Key={runData.recording_s3_key}
        recordingUrl={recordingUrl}
        recordingError={recordingError}
        recordingLoading={recordingLoading}
        onLoad={() => void loadRecording()}
        onTimeUpdate={(ms) => setAudioCurrentTimeMs(ms)}
      />

      {/* Transcript */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-text-secondary uppercase tracking-wide">
          Conversation Transcript
        </h2>
        <Card>
          <CardBody>
            <Transcript
              turns={runData.conversation}
              events={runData.events ?? []}
              scenario={scenario ?? null}
              currentTimeMs={audioCurrentTimeMs}
            />
          </CardBody>
        </Card>
      </section>

      {/* Judge findings */}
      {isComplete && (runData.summary || runData.findings.length > 0) && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-text-secondary uppercase tracking-wide">
            Judge Findings
          </h2>
          <Card>
            <CardBody>
              {runData.summary && (
                <p className="text-sm text-text-primary leading-relaxed">{runData.summary}</p>
              )}
              <div className="mt-4">
                <FindingsExplorer findings={runData.findings} />
              </div>
            </CardBody>
          </Card>
        </section>
      )}
    </div>
  );
}
