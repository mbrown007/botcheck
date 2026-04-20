"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { BuilderNode } from "@/lib/flow-translator";
import { Button } from "@/components/ui/button";
import { mapApiError, previewScenarioTurnAudio } from "@/lib/api";
import { useBuilderStore } from "@/lib/builder-store";
import { scenarioCacheObjectPath } from "@/lib/scenario-cache";
import { DECISION_DEFAULT_SLOT } from "@/lib/decision-slots";
import {
  decisionLabelsFormSchema,
  normalizeDecisionLabelInput,
  type DecisionLabelsFormValues,
} from "@/lib/schemas/decision-labels";
import {
  mergeFormValuesIntoTurn,
  turnEditorFormSchema,
  turnToFormValues,
  type TurnEditorFormValues,
} from "@/lib/schemas/turn-editor";
import {
  decisionHandleId,
  decisionOutputSlots,
  decisionSlotLabel,
} from "@/lib/builder-decision";
import { decisionConditionForSlot } from "@/lib/builder-decision";
import {
  getBuilderTurnBranchCases,
  getBuilderTurnBranchMode,
  type BuilderBranchMode,
  type BuilderTurn,
} from "@/lib/builder-types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Invariant: decisionOutputSlotsFromCount always places DECISION_DEFAULT_SLOT at index 0,
// so the filtered non-default slots align positionally with existingCases (0-based).
// The render site uses `branchCases[slotIndex - 1]` relying on the same invariant.
function branchCasesForDecisionSlots(
  turn: BuilderTurn,
  decisionSlots: string[],
  decisionSlotLabels: Record<string, string>
) {
  const existingCases = getBuilderTurnBranchCases(turn);
  return decisionSlots
    .filter((slot) => slot !== DECISION_DEFAULT_SLOT)
    .map((slot, index) => {
      const existingCase = existingCases[index];
      const nextCase: {
        condition: string;
        next: string;
        match?: string;
        regex?: string;
      } = {
        condition: decisionConditionForSlot(slot, decisionSlotLabels),
        next: typeof existingCase?.next === "string" ? existingCase.next : "",
      };
      if (typeof existingCase?.match === "string" && existingCase.match.trim()) {
        nextCase.match = existingCase.match.trim();
      }
      if (typeof existingCase?.regex === "string" && existingCase.regex.trim()) {
        nextCase.regex = existingCase.regex.trim();
      }
      return nextCase;
    });
}

const BRANCH_MODE_LABELS: Record<BuilderBranchMode, string> = {
  classifier: "Classifier",
  keyword: "Keyword",
  regex: "Regex",
};

function branchModeSummary(mode: BuilderBranchMode): string {
  return BRANCH_MODE_LABELS[mode];
}

function branchRuleSummary(
  branchCases: Array<{
    condition: string;
    next: string;
    match?: string;
    regex?: string;
  }>,
  mode: BuilderBranchMode
): string[] {
  if (mode === "classifier") {
    return [];
  }
  return branchCases
    .map((entry) => {
      const rule = mode === "keyword" ? entry.match : entry.regex;
      if (!rule) {
        return null;
      }
      return `${entry.condition}: ${rule}`;
    })
    .filter((entry): entry is string => Boolean(entry));
}

export function HarnessNode({ id, data }: NodeProps<BuilderNode>) {
  const updateNodeTurn = useBuilderStore((state) => state.updateNodeTurn);
  const nodeErrors = Array.isArray(data.nodeErrors)
    ? data.nodeErrors.filter((entry): entry is string => typeof entry === "string")
    : [];
  const {
    register: registerTurnField,
    handleSubmit,
    reset: resetTurnForm,
    formState: { errors: turnFormErrors, isDirty: turnFormDirty },
  } = useForm<TurnEditorFormValues>({
    resolver: zodResolver(turnEditorFormSchema),
    mode: "onChange",
    defaultValues: turnToFormValues(data.turn),
  });

  const [open, setOpen] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const previewAudioUrlRef = useRef<string | null>(null);

  const scenarioId =
    typeof data.scenarioId === "string" && data.scenarioId.trim()
      ? data.scenarioId
      : null;
  const ttsPreviewEnabled = data.ttsPreviewEnabled === true;
  const speakerIsHarness = data.speaker !== "bot";
  const turnCacheStatus =
    data.turnCacheStatus === "cached" ||
    data.turnCacheStatus === "skipped" ||
    data.turnCacheStatus === "failed"
      ? data.turnCacheStatus
      : "unknown";
  const turnCacheKey =
    typeof data.turnCacheKey === "string" && data.turnCacheKey.trim()
      ? data.turnCacheKey.trim()
      : null;
  const turnCacheBucketName =
    typeof data.turnCacheBucketName === "string" && data.turnCacheBucketName.trim()
      ? data.turnCacheBucketName.trim()
      : null;
  const turnCachePath = scenarioCacheObjectPath(turnCacheBucketName, turnCacheKey);
  const isBranchDecision = data.isBranchDecision === true;
  const branchOutputCount =
    typeof data.branchOutputCount === "number" && Number.isFinite(data.branchOutputCount)
      ? Math.max(1, Math.floor(data.branchOutputCount))
      : null;
  const decisionSlots = useMemo(
    () => (isBranchDecision ? decisionOutputSlots(branchOutputCount ?? undefined) : []),
    [branchOutputCount, isBranchDecision]
  );
  const decisionSlotLabels = useMemo(
    () =>
      isRecord(data.decisionOutputLabels)
        ? (data.decisionOutputLabels as Record<string, string>)
        : {},
    [data.decisionOutputLabels]
  );
  const branchMode = getBuilderTurnBranchMode(data.turn);
  const branchCases = useMemo(
    () => branchCasesForDecisionSlots(data.turn, decisionSlots, decisionSlotLabels),
    [data.turn, decisionSlotLabels, decisionSlots]
  );
  const branchRuleSummaries = useMemo(
    () => branchRuleSummary(branchCases, branchMode),
    [branchCases, branchMode]
  );
  const decisionSlotsSignature = useMemo(() => decisionSlots.join("|"), [decisionSlots]);
  const decisionLabelsSignature = useMemo(
    () => JSON.stringify(decisionSlotLabels),
    [decisionSlotLabels]
  );
  const onDecisionSlotLabelChange =
    typeof data.onDecisionSlotLabelChange === "function"
      ? (data.onDecisionSlotLabelChange as (slot: string, label: string) => void)
      : null;
  const onDecisionOutputCountChange =
    typeof data.onDecisionOutputCountChange === "function"
      ? (data.onDecisionOutputCountChange as (nextCount: number) => void)
      : null;
  const onToast =
    typeof data.onToast === "function"
      ? (data.onToast as (message: string, tone?: "info" | "warn" | "error") => void)
      : null;
  const {
    register: registerDecisionLabel,
    reset: resetDecisionLabelsForm,
    getValues: getDecisionLabelValues,
    setValue: setDecisionLabelValue,
    trigger: triggerDecisionLabelField,
    formState: { errors: decisionLabelFormErrors },
  } = useForm<DecisionLabelsFormValues>({
    resolver: zodResolver(decisionLabelsFormSchema),
    mode: "onChange",
    defaultValues: { labels: {} },
  });

  useEffect(() => {
    resetTurnForm(turnToFormValues(data.turn));
  }, [data.turn, resetTurnForm]);

  function stopPreviewAudio() {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current.currentTime = 0;
      previewAudioRef.current = null;
    }
    if (previewAudioUrlRef.current) {
      URL.revokeObjectURL(previewAudioUrlRef.current);
      previewAudioUrlRef.current = null;
    }
    setIsPlaying(false);
  }

  useEffect(() => {
    return () => {
      stopPreviewAudio();
    };
  }, []);

  useEffect(() => {
    if (!isBranchDecision) {
      resetDecisionLabelsForm({ labels: {} });
      return;
    }
    const labels: Record<string, string> = {};
    for (const slot of decisionSlots) {
      if (slot === DECISION_DEFAULT_SLOT) {
        continue;
      }
      const custom = typeof decisionSlotLabels[slot] === "string" ? decisionSlotLabels[slot] : "";
      labels[slot] = custom.trim() || decisionSlotLabel(slot);
    }
    resetDecisionLabelsForm({ labels });
  }, [
    decisionLabelsSignature,
    decisionSlotLabels,
    decisionSlots,
    decisionSlotsSignature,
    isBranchDecision,
    resetDecisionLabelsForm,
  ]);

  async function commitDecisionSlotLabel(slot: string) {
    if (!onDecisionSlotLabelChange || slot === DECISION_DEFAULT_SLOT) {
      return;
    }
    const fieldPath = `labels.${slot}` as `labels.${string}`;
    const isValid = await triggerDecisionLabelField(fieldPath);
    if (!isValid) {
      const message = decisionLabelFormErrors.labels?.[slot]?.message;
      if (typeof message === "string" && message) {
        onToast?.(message, "warn");
      }
      return;
    }
    const rawValue = getDecisionLabelValues(fieldPath);
    const current = typeof rawValue === "string" ? rawValue : "";
    const normalized = normalizeDecisionLabelInput(current);
    onDecisionSlotLabelChange(slot, normalized);
    if (!normalized) {
      setDecisionLabelValue(fieldPath, decisionSlotLabel(slot), {
        shouldDirty: false,
        shouldTouch: true,
        shouldValidate: true,
      });
    }
  }

  function decisionHandleTooltip(slot: string): string {
    if (slot === DECISION_DEFAULT_SLOT) {
      return `${DECISION_DEFAULT_SLOT} (fallback)`;
    }
    const custom =
      typeof decisionSlotLabels[slot] === "string" ? decisionSlotLabels[slot].trim() : "";
    const label = custom || decisionSlotLabel(slot);
    return `${slot} -> ${label}`;
  }

  function adjustDecisionOutputs(delta: number) {
    if (!onDecisionOutputCountChange || branchOutputCount === null) {
      return;
    }
    onDecisionOutputCountChange(branchOutputCount + delta);
  }

  function updateDecisionBranching(
    updater: (next: {
      mode: BuilderBranchMode;
      cases: Array<{
        condition: string;
        next: string;
        match?: string;
        regex?: string;
      }>;
      default: string;
    }) => void
  ) {
    const existingDefault =
      typeof data.turn.branching?.default === "string" ? data.turn.branching.default : "";
    const nextBranching = {
      mode: branchMode,
      cases: branchCases.map((entry) => ({ ...entry })),
      default: existingDefault,
    };
    updater(nextBranching);
    updateNodeTurn(id, {
      ...data.turn,
      branching: nextBranching,
    });
  }

  function handleBranchModeChange(nextMode: BuilderBranchMode) {
    updateDecisionBranching((nextBranching) => {
      nextBranching.mode = nextMode;
      nextBranching.cases = nextBranching.cases.map((entry) => {
        if (nextMode === "keyword") {
          const { regex: _regex, ...rest } = entry;
          return rest;
        }
        if (nextMode === "regex") {
          const { match: _match, ...rest } = entry;
          return rest;
        }
        const { match: _match, regex: _regex, ...rest } = entry;
        return rest;
      });
    });
  }

  function handleBranchRuleChange(slot: string, field: "match" | "regex", value: string) {
    const caseIndex = decisionSlots.findIndex((entry) => entry === slot);
    if (caseIndex <= 0) {
      return;
    }
    const normalizedValue = value.trim();
    updateDecisionBranching((nextBranching) => {
      const branchCase = nextBranching.cases[caseIndex - 1];
      if (!branchCase) {
        return;
      }
      if (field === "match") {
        delete branchCase.regex;
      } else {
        delete branchCase.match;
      }
      if (normalizedValue) {
        branchCase[field] = normalizedValue;
      } else {
        delete branchCase[field];
      }
    });
  }

  async function handleCopyCachePath() {
    if (!turnCachePath) {
      return;
    }
    try {
      await navigator.clipboard.writeText(turnCachePath);
      onToast?.("Copied cache path.", "info");
    } catch {
      onToast?.("Failed to copy cache path.", "warn");
    }
  }

  async function handlePlayPreview() {
    if (!ttsPreviewEnabled || !scenarioId || !speakerIsHarness) {
      return;
    }
    if (isPlaying) {
      stopPreviewAudio();
      return;
    }

    setPreviewing(true);

    try {
      stopPreviewAudio();
      const audioBlob = await previewScenarioTurnAudio(scenarioId, id);
      const objectUrl = URL.createObjectURL(audioBlob);
      previewAudioUrlRef.current = objectUrl;
      const audio = new Audio(objectUrl);
      previewAudioRef.current = audio;

      audio.onended = () => {
        stopPreviewAudio();
      };
      audio.onerror = () => {
        stopPreviewAudio();
      };

      await audio.play();
      setIsPlaying(true);
    } catch (error) {
      stopPreviewAudio();
      console.error("Turn preview failed", error);
      const { message, tone } = mapApiError(error, "Audio preview failed");
      onToast?.(message, tone);
    } finally {
      setPreviewing(false);
    }
  }

  const handleSave = handleSubmit(
    (values) => {
      const updatedTurn = mergeFormValuesIntoTurn(data.turn, id, values);
      updateNodeTurn(id, updatedTurn);
      setOpen(false);
    },
    () => {
      onToast?.("Fix validation errors before saving.", "warn");
    }
  );

  return (
    <div className="relative w-[280px] max-w-[280px] rounded-xl border border-brand/40 bg-bg-surface px-3 py-2 shadow-sm">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border !border-border !bg-bg-elevated"
      />
      {!isBranchDecision && (
        <Handle
          type="source"
          position={Position.Right}
          title="next"
          aria-label="next output"
          className="!h-2.5 !w-2.5 !border !border-border !bg-brand"
        />
      )}
      {isBranchDecision &&
        decisionSlots.map((slot, index) => {
          const topPct = ((index + 1) / (decisionSlots.length + 1)) * 100;
          const tooltip = decisionHandleTooltip(slot);
          return (
            <Handle
              key={slot}
              id={decisionHandleId(slot)}
              type="source"
              position={Position.Right}
              style={{ top: `${topPct}%` }}
              title={tooltip}
              aria-label={tooltip}
              className="!h-2.5 !w-2.5 !border !border-brand !bg-brand"
            />
          );
        })}
      <div className="flex items-center justify-between gap-3">
        <span className="rounded bg-brand-muted px-2 py-0.5 font-mono text-[11px] text-brand">
          {data.turnId}
        </span>
        <div className="flex items-center gap-2">
          {nodeErrors.length > 0 && (
            <span className="rounded border border-fail-border bg-fail-bg px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-fail">
              {nodeErrors.length} issue{nodeErrors.length === 1 ? "" : "s"}
            </span>
          )}
          <span className="text-[11px] uppercase tracking-wide text-text-muted">
            {data.speaker}
          </span>
          {isBranchDecision && branchOutputCount !== null && (
            <span className="rounded border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-muted">
              {branchOutputCount} outputs
            </span>
          )}
        </div>
      </div>
      <p className="mt-2 max-h-[3.75rem] overflow-hidden whitespace-pre-wrap break-words text-xs leading-5 text-text-primary [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:3]">
        {data.text || "No text"}
      </p>
      {isBranchDecision ? (
        <div className="mt-2 rounded border border-border bg-bg-elevated px-2 py-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase tracking-wide text-text-muted">Branching</p>
            <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary">
              {branchModeSummary(branchMode)}
            </span>
          </div>
          {branchRuleSummaries.length > 0 ? (
            <ul className="mt-1 space-y-1 text-[10px] text-text-secondary">
              {branchRuleSummaries.slice(0, 2).map((entry, index) => (
                <li key={index} className="truncate" title={entry}>
                  {entry}
                </li>
              ))}
              {branchRuleSummaries.length > 2 ? (
                <li className="text-text-muted">+{branchRuleSummaries.length - 2} more</li>
              ) : null}
            </ul>
          ) : (
            <p className="mt-1 text-[10px] text-text-muted">
              {branchMode === "classifier"
                ? "Edge labels become classifier outputs."
                : "Rules not set yet."}
            </p>
          )}
        </div>
      ) : null}
      {speakerIsHarness && ttsPreviewEnabled && (
        <div className="mt-2 rounded border border-border bg-bg-elevated px-2 py-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase tracking-wide text-text-muted">TTS Cache</p>
            <span className="font-mono text-[10px] text-text-secondary">{turnCacheStatus}</span>
          </div>
          {turnCachePath ? (
            <div className="mt-1 flex items-start gap-2">
              <p
                className="min-w-0 flex-1 truncate font-mono text-[10px] text-text-muted"
                title={turnCachePath}
              >
                {turnCachePath}
              </p>
              <button
                type="button"
                className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-text-secondary hover:text-text-primary"
                onClick={() => void handleCopyCachePath()}
                aria-label="Copy cache path"
                title="Copy cache path"
              >
                Copy
              </button>
            </div>
          ) : (
            <p className="mt-1 text-[10px] text-text-muted">No cached object path yet.</p>
          )}
        </div>
      )}
      {isBranchDecision && (
        <div className="mt-2 rounded border border-border bg-bg-elevated px-2 py-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] uppercase tracking-wide text-text-muted">
              Outputs
            </p>
            <div className="flex items-center gap-2">
              <select
                value={branchMode}
                onChange={(event) =>
                  handleBranchModeChange(event.target.value as BuilderBranchMode)
                }
                className="rounded border border-border bg-bg-surface px-1 py-0.5 text-[10px] text-text-primary focus:border-border-focus focus:outline-none"
                aria-label="Branch mode"
              >
                <option value="classifier">Classifier</option>
                <option value="keyword">Keyword</option>
                <option value="regex">Regex</option>
              </select>
              <div className="inline-flex items-center gap-1 rounded border border-border px-1 py-0.5 text-[10px] text-text-muted">
                <button
                  type="button"
                  className="h-4 w-4 rounded border border-border text-[10px] text-text-secondary hover:text-text-primary"
                  onClick={() => adjustDecisionOutputs(-1)}
                  aria-label="Decrease outputs"
                >
                  -
                </button>
                <span className="min-w-[16px] text-center">{branchOutputCount ?? 1}</span>
                <button
                  type="button"
                  className="h-4 w-4 rounded border border-border text-[10px] text-text-secondary hover:text-text-primary"
                  onClick={() => adjustDecisionOutputs(1)}
                  aria-label="Increase outputs"
                >
                  +
                </button>
              </div>
            </div>
          </div>
          <p className="mt-1 text-[10px] text-text-muted">
            {branchMode === "classifier"
              ? "Use edge labels as classifier outputs."
              : branchMode === "keyword"
                ? "Match each connected path using a case-insensitive keyword or phrase."
                : "Match each connected path using a case-insensitive regular expression."}
          </p>
          <div className="mt-1 space-y-1">
            {decisionSlots.map((slot, slotIndex) =>
              slot === DECISION_DEFAULT_SLOT ? (
                <div
                  key={slot}
                  className="flex items-center justify-between gap-2 rounded border border-border px-1 py-0.5"
                >
                  <span className="font-mono text-[10px] text-text-secondary">{slot}</span>
                  <span className="text-[10px] text-text-muted">fallback</span>
                </div>
              ) : (
                <div
                  key={slot}
                  className="rounded border border-border px-1 py-1"
                >
                  <label className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] text-text-secondary">{slot}</span>
                    <input
                      {...registerDecisionLabel(`labels.${slot}` as `labels.${string}`)}
                      onBlur={() => {
                        void commitDecisionSlotLabel(slot);
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter") {
                          return;
                        }
                        event.preventDefault();
                        void commitDecisionSlotLabel(slot);
                      }}
                      placeholder={decisionSlotLabel(slot)}
                      className="w-[120px] rounded border border-border bg-bg-surface px-1 py-0.5 text-[10px] text-text-primary focus:border-border-focus focus:outline-none"
                    />
                  </label>
                  {branchMode !== "classifier" ? (
                    <div className="mt-1">
                      <input
                        value={
                          branchMode === "keyword"
                            ? branchCases[slotIndex - 1]?.match ?? ""
                            : branchCases[slotIndex - 1]?.regex ?? ""
                        }
                        onChange={(event) =>
                          handleBranchRuleChange(
                            slot,
                            branchMode === "keyword" ? "match" : "regex",
                            event.target.value
                          )
                        }
                        placeholder={
                          branchMode === "keyword"
                            ? "billing support"
                            : "^(billing|payments)$"
                        }
                        className="w-full rounded border border-border bg-bg-surface px-1 py-0.5 text-[10px] text-text-primary focus:border-border-focus focus:outline-none"
                      />
                    </div>
                  ) : null}
                </div>
              )
            )}
          </div>
        </div>
      )}
      {nodeErrors.length > 0 && (
        <ul className="mt-2 space-y-1 rounded border border-fail-border bg-fail-bg px-2 py-1 text-[11px] text-fail">
          {nodeErrors.map((message) => (
            <li key={message}>• {message}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex w-full gap-2">
        {ttsPreviewEnabled && (
          <Button
            variant="secondary"
            size="sm"
            className="flex-1"
            onClick={() => void handlePlayPreview()}
            disabled={
              (previewing && !isPlaying) ||
              !speakerIsHarness ||
              scenarioId === null
            }
            title={
              !speakerIsHarness
                ? "Only harness turns support preview."
                : scenarioId === null
                  ? "Save scenario before previewing audio."
                  : undefined
            }
          >
            {previewing && !isPlaying
              ? "Loading…"
              : isPlaying
                ? "■ Stop"
                : "▶ Play"}
          </Button>
        )}
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Trigger asChild>
          <Button
            variant="secondary"
            size="sm"
            className={ttsPreviewEnabled ? "flex-1" : "w-full"}
          >
            Edit Turn
          </Button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[60] bg-overlay/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[70] flex w-full max-w-xl -translate-x-1/2 -translate-y-1/2 flex-col max-h-[calc(100vh-2rem)] rounded-lg border border-border bg-bg-surface shadow-xl">
            <div className="shrink-0 border-b border-border px-5 pt-5 pb-4">
              <Dialog.Title className="text-base font-semibold text-text-primary">
                Edit Turn {id}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-text-secondary">
                Update core turn fields. Branching edges remain graph-driven.
              </Dialog.Description>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="md:col-span-2">
                <span className="mb-1 block text-xs text-text-secondary">Text</span>
                <textarea
                  {...registerTurnField("text")}
                  rows={4}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
              </label>

              {speakerIsHarness && ttsPreviewEnabled ? (
                <div className="md:col-span-2 rounded-md border border-border bg-bg-elevated/70 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-text-primary">Turn Voice Preview</p>
                      <p className="mt-1 text-[11px] text-text-secondary">
                        {scenarioId === null
                          ? "Save the scenario before previewing turn audio."
                          : turnFormDirty
                            ? "Preview uses the last saved scenario version. Save builder changes to hear edits."
                            : "Preview the saved TTS output for this harness turn."}
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="shrink-0"
                      onClick={() => void handlePlayPreview()}
                      disabled={(previewing && !isPlaying) || scenarioId === null}
                    >
                      {previewing && !isPlaying
                        ? "Loading…"
                        : isPlaying
                          ? "Stop"
                          : "Preview"}
                    </Button>
                  </div>
                </div>
              ) : null}

              <label>
                <span className="mb-1 block text-xs text-text-secondary">Speaker</span>
                <select
                  {...registerTurnField("speaker")}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                >
                  <option value="harness">harness</option>
                  <option value="bot">bot</option>
                </select>
              </label>

              <label className="flex items-end gap-2 rounded-md border border-border bg-bg-elevated px-3 py-2">
                <input
                  type="checkbox"
                  {...registerTurnField("wait_for_response")}
                />
                <span className="text-xs text-text-secondary">Wait for response</span>
              </label>

              <label>
                <span className="mb-1 block text-xs text-text-secondary">DTMF</span>
                <input
                  {...registerTurnField("dtmf")}
                  placeholder="1 or 9#"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
              </label>

              <label>
                <span className="mb-1 block text-xs text-text-secondary">Silence (s)</span>
                <input
                  {...registerTurnField("silence_s")}
                  placeholder="2.5"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
                {turnFormErrors.silence_s?.message ? (
                  <p className="mt-1 text-[10px] text-fail">{turnFormErrors.silence_s.message}</p>
                ) : null}
              </label>

              <label>
                <span className="mb-1 block text-xs text-text-secondary">Audio File</span>
                <input
                  {...registerTurnField("audio_file")}
                  placeholder="prompts/intro.wav"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
              </label>

              <label>
                <span className="mb-1 block text-xs text-text-secondary">Max Visits</span>
                <input
                  {...registerTurnField("max_visits")}
                  placeholder="1"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
                {turnFormErrors.max_visits?.message ? (
                  <p className="mt-1 text-[10px] text-fail">{turnFormErrors.max_visits.message}</p>
                ) : null}
              </label>

              <label>
                <span className="mb-1 block text-xs text-text-secondary">
                  Timeout (s)
                </span>
                <input
                  {...registerTurnField("timeout_s")}
                  placeholder="15"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                />
                {turnFormErrors.timeout_s?.message ? (
                  <p className="mt-1 text-[10px] text-fail">{turnFormErrors.timeout_s.message}</p>
                ) : null}
              </label>

              <div className="md:col-span-2 rounded-md border border-border bg-bg-elevated/70 p-3">
                <p className="text-xs font-medium text-text-primary">Advanced Turn Timing</p>
                <p className="mt-1 text-[11px] text-text-secondary">
                  Optional per-turn overrides for silence retries, response filtering, and
                  playback/listen timing.
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Retry on Silence
                    </span>
                    <input
                      {...registerTurnField("retry_on_silence")}
                      placeholder="0"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.retry_on_silence?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.retry_on_silence.message}
                      </p>
                    ) : null}
                  </label>

                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Listen For (s)
                    </span>
                    <input
                      {...registerTurnField("listen_for_s")}
                      placeholder="3"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.listen_for_s?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.listen_for_s.message}
                      </p>
                    ) : null}
                  </label>

                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Min Response Duration (s)
                    </span>
                    <input
                      {...registerTurnField("min_response_duration_s")}
                      placeholder="0.5"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.min_response_duration_s?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.min_response_duration_s.message}
                      </p>
                    ) : null}
                  </label>

                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Pre-speak Pause (s)
                    </span>
                    <input
                      {...registerTurnField("pre_speak_pause_s")}
                      placeholder="0"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.pre_speak_pause_s?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.pre_speak_pause_s.message}
                      </p>
                    ) : null}
                  </label>

                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Post-speak Pause (s)
                    </span>
                    <input
                      {...registerTurnField("post_speak_pause_s")}
                      placeholder="0"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.post_speak_pause_s?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.post_speak_pause_s.message}
                      </p>
                    ) : null}
                  </label>

                  <label>
                    <span className="mb-1 block text-xs text-text-secondary">
                      Pre-listen Wait (s)
                    </span>
                    <input
                      {...registerTurnField("pre_listen_wait_s")}
                      placeholder="0"
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                    {turnFormErrors.pre_listen_wait_s?.message ? (
                      <p className="mt-1 text-[10px] text-fail">
                        {turnFormErrors.pre_listen_wait_s.message}
                      </p>
                    ) : null}
                  </label>
                </div>
              </div>
            </div>
            </div>

            <div className="shrink-0 flex justify-end gap-2 border-t border-border px-5 py-4">
              <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={() => void handleSave()}>
                Save Turn
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      </div>
    </div>
  );
}
