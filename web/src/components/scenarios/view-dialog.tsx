"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import { previewScenarioTurnAudio, useScenario, useScenarioCacheState } from "@/lib/api";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cacheStatusVariant } from "@/lib/cache-status";
import { getScenarioTurnKind, getScenarioTurnSpeaker, getScenarioTurnText } from "@/lib/scenario-turns";
import {
  buildScenarioCacheTurnLookup,
  scenarioCacheCoverageLabel,
  scenarioCacheObjectPath,
} from "@/lib/scenario-cache";

interface ScenarioViewDialogProps {
  scenarioId: string | null;
  cacheFeatureEnabled?: boolean;
  cacheStatus?: string | null;
  cacheUpdatedAt?: string | null;
  onOpenInBuilder?: (scenarioId: string) => void;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
        {title}
      </p>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-28 shrink-0 text-text-muted">{label}</span>
      <span className="text-text-primary">{value ?? "—"}</span>
    </div>
  );
}

function turnCacheStatusVariant(status?: string | null): string {
  const normalized = (status ?? "unknown").toLowerCase();
  if (normalized === "cached" || normalized === "skipped") return "pass";
  if (normalized === "failed") return "fail";
  return "pending";
}

export function ScenarioViewDialog({
  scenarioId,
  cacheFeatureEnabled = false,
  cacheStatus,
  cacheUpdatedAt,
  onOpenInBuilder,
  onClose,
}: ScenarioViewDialogProps) {
  const { data: scenario, error } = useScenario(scenarioId);
  const [previewingTurnId, setPreviewingTurnId] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState("");
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const activeAudioUrlRef = useRef<string | null>(null);
  const {
    data: cacheState,
    error: cacheStateError,
  } = useScenarioCacheState(scenarioId, cacheFeatureEnabled);

  const turns = scenario?.turns ?? [];
  const rubric = scenario?.scoring?.rubric ?? [];
  const persona = scenario?.persona;
  const bot = scenario?.bot;
  const tags = scenario?.tags ?? [];
  const turnStateById = buildScenarioCacheTurnLookup(cacheState);
  const cacheCoverage = scenarioCacheCoverageLabel(cacheState);
  // created_at is not part of ScenarioDefinition type but the API may include it
  const createdAt = (scenario as unknown as { created_at?: string })?.created_at;

  useEffect(() => {
    return () => {
      if (activeAudioRef.current) {
        activeAudioRef.current.pause();
        activeAudioRef.current.currentTime = 0;
      }
      if (activeAudioUrlRef.current) {
        URL.revokeObjectURL(activeAudioUrlRef.current);
      }
    };
  }, []);

  async function handlePreview(turnId: string) {
    if (!scenarioId) {
      return;
    }
    setPreviewError("");
    setPreviewingTurnId(turnId);
    try {
      if (activeAudioRef.current) {
        activeAudioRef.current.pause();
        activeAudioRef.current.currentTime = 0;
        activeAudioRef.current = null;
      }
      if (activeAudioUrlRef.current) {
        URL.revokeObjectURL(activeAudioUrlRef.current);
        activeAudioUrlRef.current = null;
      }

      const audioBlob = await previewScenarioTurnAudio(scenarioId, turnId);
      const objectUrl = URL.createObjectURL(audioBlob);
      activeAudioUrlRef.current = objectUrl;
      const audio = new Audio(objectUrl);
      activeAudioRef.current = audio;
      audio.onended = () => {
        if (activeAudioUrlRef.current) {
          URL.revokeObjectURL(activeAudioUrlRef.current);
          activeAudioUrlRef.current = null;
        }
        activeAudioRef.current = null;
      };
      audio.onerror = () => {
        if (activeAudioUrlRef.current) {
          URL.revokeObjectURL(activeAudioUrlRef.current);
          activeAudioUrlRef.current = null;
        }
        activeAudioRef.current = null;
      };
      await audio.play();
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Audio preview failed");
    } finally {
      setPreviewingTurnId((prev) => (prev === turnId ? null : prev));
    }
  }

  async function handleCopyCachePath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      setPreviewError("");
    } catch {
      setPreviewError("Failed to copy cache path");
    }
  }

  return (
    <Dialog.Root open={scenarioId !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-surface shadow-xl flex flex-col max-h-[85vh]">
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border px-6 py-4">
            <div className="space-y-1">
              {scenario ? (
                <>
                  <Dialog.Title className="text-base font-semibold text-text-primary">
                    {scenario.name}
                  </Dialog.Title>
                  <div className="flex items-center gap-2">
                    <StatusBadge value={scenario.type} label={scenario.type} />
                    <span className="font-mono text-xs text-text-muted">{scenario.id}</span>
                  </div>
                </>
              ) : (
                <Dialog.Title className="text-base font-semibold text-text-primary">
                  {error ? "Failed to load scenario" : "Loading…"}
                </Dialog.Title>
              )}
              <Dialog.Description className="sr-only">
                Full scenario definition
              </Dialog.Description>
            </div>
            <div className="flex items-center gap-2">
              {scenario && onOpenInBuilder && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onOpenInBuilder(scenario.id)}
                >
                  Open in Builder
                </Button>
              )}
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm">✕</Button>
              </Dialog.Close>
            </div>
          </div>

          {/* Body */}
          <div className="overflow-y-auto px-6 py-5 space-y-6">
            {error && (
              <p className="text-sm text-fail">{error.message}</p>
            )}

            {scenario && (
              <>
                {/* Metadata */}
                <Section title="Metadata">
                  <div className="space-y-1.5">
                    <Field label="Description" value={scenario.description} />
                    <Field label="Version" value={
                      <span className="font-mono text-xs">{scenario.version}</span>
                    } />
                    <Field label="Turns" value={turns.length} />
                    {cacheFeatureEnabled && (
                      <div className="flex gap-2 text-sm">
                        <span className="w-28 shrink-0 text-text-muted">Cache</span>
                        <StatusBadge
                          value={cacheStatusVariant(cacheStatus)}
                          label={cacheStatus ?? "cold"}
                        />
                      </div>
                    )}
                    {cacheFeatureEnabled && cacheUpdatedAt && (
                      <Field
                        label="Cache Updated"
                        value={new Date(cacheUpdatedAt).toLocaleString()}
                      />
                    )}
                    {cacheFeatureEnabled && cacheState && cacheCoverage && (
                      <Field
                        label="Cache Coverage"
                        value={cacheCoverage}
                      />
                    )}
                    {createdAt && (
                      <Field label="Created" value={
                        new Date(createdAt).toLocaleString()
                      } />
                    )}
                    {tags.length > 0 && (
                      <div className="flex gap-2 text-sm">
                        <span className="w-28 shrink-0 text-text-muted">Tags</span>
                        <div className="flex flex-wrap gap-1">
                          {tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded border border-border bg-bg-elevated px-1.5 py-0.5 font-mono text-xs text-text-secondary"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </Section>

                {/* Bot */}
                {bot && (bot.endpoint || bot.protocol) && (
                  <Section title="Bot">
                    <div className="space-y-1.5">
                      {bot.protocol && (
                        <Field label="Protocol" value={
                          <span className={`font-mono text-xs ${bot.protocol === "mock" ? "text-amber-400" : ""}`}>
                            {bot.protocol === "mock" ? "mock (local test bot)" : bot.protocol}
                          </span>
                        } />
                      )}
                      {bot.endpoint && (
                        <Field label="Endpoint" value={
                          <span className="font-mono text-xs">{bot.endpoint}</span>
                        } />
                      )}
                      {bot.caller_id && (
                        <Field label="Caller ID" value={
                          <span className="font-mono text-xs">{bot.caller_id}</span>
                        } />
                      )}
                      {bot.trunk_id && (
                        <Field label="Trunk ID" value={
                          <span className="font-mono text-xs">{bot.trunk_id}</span>
                        } />
                      )}
                    </div>
                  </Section>
                )}

                {/* Persona */}
                {persona && (
                  <Section title="Harness Persona">
                    <div className="space-y-1.5">
                      <Field label="Mood" value={persona.mood} />
                      <Field label="Style" value={persona.response_style} />
                    </div>
                  </Section>
                )}

                {/* Turns */}
                {turns.length > 0 && (
                  <Section title={`Turns (${turns.length})`}>
                    {cacheFeatureEnabled && cacheStateError && (
                      <p className="mb-3 text-xs text-warn">
                        Per-turn cache state unavailable.
                      </p>
                    )}
                    {previewError && (
                      <p className="mb-3 text-xs text-fail">{previewError}</p>
                    )}
                      <ol className="space-y-3">
                      {turns.map((turn, idx) => {
                        const kind = getScenarioTurnKind(turn);
                        const speaker = getScenarioTurnSpeaker(turn);
                        const text = getScenarioTurnText(turn);
                        const displayText =
                          text ||
                          (kind === "hangup"
                            ? "Hang up"
                            : kind === "wait"
                              ? "Wait / Pause"
                              : kind === "time_route"
                                ? "Time Route"
                                : "—");
                        const canPreview =
                          cacheFeatureEnabled && speaker === "harness" && Boolean(text);

                        return (
                          <li
                            key={turn.id}
                            className="rounded-md border border-border bg-bg-elevated p-3"
                          >
                            <div className="mb-1 flex items-center gap-2">
                              <span className="rounded bg-bg-surface px-1.5 py-0.5 font-mono text-xs text-text-muted">
                                {idx + 1}
                              </span>
                              <span className="font-mono text-xs text-text-muted">{turn.id}</span>
                              {canPreview && (
                                <StatusBadge
                                  value={turnCacheStatusVariant(turnStateById[turn.id]?.status ?? "unknown")}
                                  label={`cache:${turnStateById[turn.id]?.status ?? "unknown"}`}
                                />
                              )}
                              {turn.adversarial && (
                                <StatusBadge value="fail" label="adversarial" />
                              )}
                              {turn.technique && (
                                <span className="font-mono text-xs text-warn">{turn.technique}</span>
                              )}
                              {canPreview && (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  className="ml-auto"
                                  disabled={previewingTurnId !== null}
                                  onClick={() => void handlePreview(turn.id)}
                                >
                                  {previewingTurnId === turn.id ? "Previewing…" : "Preview"}
                                </Button>
                              )}
                            </div>
                            <p className="text-sm text-text-primary">{displayText}</p>
                            {canPreview && (() => {
                              const cachePath = scenarioCacheObjectPath(
                                cacheState?.bucket_name,
                                turnStateById[turn.id]?.key ?? null
                              );
                              return cachePath ? (
                                <div className="mt-2 flex items-start gap-2">
                                  <p
                                    className="min-w-0 flex-1 break-all font-mono text-[11px] text-text-muted"
                                    title={cachePath}
                                  >
                                    {cachePath}
                                  </p>
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    className="shrink-0"
                                    onClick={() => void handleCopyCachePath(cachePath)}
                                  >
                                    Copy
                                  </Button>
                                </div>
                              ) : (
                                <p className="mt-2 text-[11px] text-text-muted">
                                  No cached object path yet.
                                </p>
                              );
                            })()}
                          </li>
                        );
                      })}
                    </ol>
                  </Section>
                )}

                {/* Scoring rubric */}
                {rubric.length > 0 && (
                  <Section title="Scoring Rubric">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                          <th className="pb-2 font-medium">Dimension</th>
                          <th className="pb-2 font-medium">Weight</th>
                          <th className="pb-2 font-medium">Threshold</th>
                          <th className="pb-2 font-medium">Gate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rubric.map((entry) => (
                          <tr key={entry.dimension} className="border-b border-border last:border-0">
                            <td className="py-2 font-mono text-xs text-text-primary">
                              {entry.dimension}
                            </td>
                            <td className="py-2 text-text-secondary">
                              {Math.round(entry.weight * 100)}%
                            </td>
                            <td className="py-2 text-text-secondary">
                              {Math.round(entry.threshold * 100)}%
                            </td>
                            <td className="py-2">
                              {entry.gate ? (
                                <StatusBadge value="fail" label="gate" />
                              ) : (
                                <span className="text-text-muted">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Section>
                )}
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
