"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useMemo, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Button } from "@/components/ui/button";
import { useBuilderStore } from "@/lib/builder-store";
import {
  decisionHandleId,
  decisionOutputSlots,
  decisionSlotLabel,
} from "@/lib/builder-decision";
import { DECISION_DEFAULT_SLOT } from "@/lib/decision-slots";
import {
  getBuilderTimeRouteTimezone,
  getBuilderTimeRouteWindows,
  toCanonicalBuilderTurn,
} from "@/lib/builder-types";
import type { BuilderNode } from "@/lib/flow-translator";
import { TIME_ROUTE_HHMM_RE } from "@/lib/builder-validation";

type DraftWindow = {
  label: string;
  start: string;
  end: string;
};

function normalizeDraftWindows(data: BuilderNode["data"], outputCount: number): Record<string, DraftWindow> {
  const labels =
    data.decisionOutputLabels && typeof data.decisionOutputLabels === "object"
      ? (data.decisionOutputLabels as Record<string, string>)
      : {};
  const existingWindows = getBuilderTimeRouteWindows(data.turn);
  const windows: Record<string, DraftWindow> = {};
  const slots = decisionOutputSlots(outputCount).filter((slot) => slot !== DECISION_DEFAULT_SLOT);
  slots.forEach((slot, index) => {
    const existing = existingWindows[index];
    windows[slot] = {
      label:
        typeof labels[slot] === "string" && labels[slot].trim()
          ? labels[slot].trim()
          : (existing?.label ?? decisionSlotLabel(slot)),
      start: existing?.start ?? "",
      end: existing?.end ?? "",
    };
  });
  return windows;
}

export function TimeRouteNode({ id, data }: NodeProps<BuilderNode>) {
  const updateNodeTurn = useBuilderStore((state) => state.updateNodeTurn);
  const [open, setOpen] = useState(false);
  const branchOutputCount =
    typeof data.branchOutputCount === "number" && Number.isFinite(data.branchOutputCount)
      ? Math.max(2, Math.floor(data.branchOutputCount))
      : Math.max(2, getBuilderTimeRouteWindows(data.turn).length + 1);
  const decisionSlots = useMemo(
    () => decisionOutputSlots(branchOutputCount),
    [branchOutputCount]
  );
  const nonDefaultSlots = decisionSlots.filter((slot) => slot !== DECISION_DEFAULT_SLOT);
  const [draftTimezone, setDraftTimezone] = useState(getBuilderTimeRouteTimezone(data.turn) ?? "UTC");
  const [draftWindows, setDraftWindows] = useState<Record<string, DraftWindow>>(
    normalizeDraftWindows(data, branchOutputCount)
  );
  const [error, setError] = useState<string | null>(null);

  // Only re-sync draft state when the modal is closed. Re-syncing while
  // the modal is open would silently discard in-progress edits (e.g. a
  // timezone change) whenever the +/- window count buttons trigger a store
  // update that propagates back through the `data` prop.
  useEffect(() => {
    if (!open) {
      setDraftTimezone(getBuilderTimeRouteTimezone(data.turn) ?? "UTC");
      setDraftWindows(normalizeDraftWindows(data, branchOutputCount));
      setError(null);
    }
  }, [open, branchOutputCount, data]);

  function resetDraftState() {
    setDraftTimezone(getBuilderTimeRouteTimezone(data.turn) ?? "UTC");
    setDraftWindows(normalizeDraftWindows(data, branchOutputCount));
    setError(null);
  }

  const onDecisionOutputCountChange =
    typeof data.onDecisionOutputCountChange === "function"
      ? (data.onDecisionOutputCountChange as (nextCount: number) => void)
      : null;
  const onDecisionSlotLabelChange =
    typeof data.onDecisionSlotLabelChange === "function"
      ? (data.onDecisionSlotLabelChange as (slot: string, label: string) => void)
      : null;
  const nodeErrors = Array.isArray(data.nodeErrors)
    ? data.nodeErrors.filter((entry): entry is string => typeof entry === "string")
    : [];

  const summaries = nonDefaultSlots
    .map((slot) => {
      const window = draftWindows[slot];
      if (!window) {
        return null;
      }
      return `${window.label || decisionSlotLabel(slot)} ${window.start || "??:??"}-${window.end || "??:??"}`;
    })
    .filter((entry): entry is string => Boolean(entry));

  function updateDraftWindow(slot: string, field: keyof DraftWindow, value: string) {
    setDraftWindows((current) => ({
      ...current,
      [slot]: {
        ...(current[slot] ?? {
          label: decisionSlotLabel(slot),
          start: "",
          end: "",
        }),
        [field]: value,
      },
    }));
  }

  function adjustOutputs(delta: number) {
    onDecisionOutputCountChange?.(branchOutputCount + delta);
  }

  function handleSave() {
    try {
      const timezone = draftTimezone.trim();
      if (!timezone) {
        setError("Timezone is required.");
        return;
      }

      const nextWindows = nonDefaultSlots.map((slot, index) => {
        const window = draftWindows[slot] ?? {
          label: decisionSlotLabel(slot),
          start: "",
          end: "",
        };
        const label = window.label.trim() || decisionSlotLabel(slot);
        const start = window.start.trim();
        const end = window.end.trim();
        if (!TIME_ROUTE_HHMM_RE.test(start) || !TIME_ROUTE_HHMM_RE.test(end)) {
          throw new Error(`Window "${label}" requires start/end in HH:MM format.`);
        }
        if (start === end) {
          throw new Error(`Window "${label}" cannot use the same start and end time.`);
        }
        return {
          label,
          start,
          end,
          next: getBuilderTimeRouteWindows(data.turn)[index]?.next ?? "",
        };
      });

      nonDefaultSlots.forEach((slot) => {
        onDecisionSlotLabelChange?.(slot, draftWindows[slot]?.label ?? "");
      });
      updateNodeTurn(
        id,
        toCanonicalBuilderTurn({
          ...data.turn,
          kind: "time_route",
          timezone,
          windows: nextWindows,
          default: typeof data.turn.default === "string" ? data.turn.default : "",
        })
      );
      setError(null);
      setOpen(false);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Invalid time route.");
    }
  }

  return (
    <div className="relative min-w-[280px] rounded-md border border-sky-300 bg-sky-50 px-3 py-2 shadow-sm dark:border-sky-800 dark:bg-sky-950/30">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border !border-sky-300 !bg-bg-elevated"
      />
      {decisionSlots.map((slot, index) => {
        const topPct = ((index + 1) / (decisionSlots.length + 1)) * 100;
        return (
          <Handle
            key={slot}
            id={decisionHandleId(slot)}
            type="source"
            position={Position.Right}
            style={{ top: `${topPct}%` }}
            title={slot === DECISION_DEFAULT_SLOT ? "default" : draftWindows[slot]?.label || slot}
            aria-label={slot === DECISION_DEFAULT_SLOT ? "default" : draftWindows[slot]?.label || slot}
            className="!h-2.5 !w-2.5 !border !border-sky-300 !bg-bg-elevated"
          />
        );
      })}
      <div className="flex items-center justify-between gap-2">
        <span className="rounded border border-sky-400 bg-sky-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-sky-950 dark:border-sky-700 dark:bg-sky-900/50 dark:text-sky-200">
          Time Route
        </span>
        <span className="font-mono text-[11px] text-text-muted">{data.turnId}</span>
      </div>
      <p className="mt-2 text-xs text-text-primary">Route to different paths based on local time windows.</p>
      <div className="mt-2 rounded border border-sky-200 bg-white/85 px-2 py-1 text-[11px] text-text-secondary dark:border-sky-900 dark:bg-bg-surface/90">
        <div className="flex items-center justify-between gap-2">
          <span>Timezone</span>
          <span className="font-mono">{draftTimezone || "UTC"}</span>
        </div>
        {summaries.length > 0 ? (
          <ul className="mt-1 space-y-1">
            {summaries.slice(0, 2).map((entry, index) => (
              <li key={index} className="truncate" title={entry}>
                {entry}
              </li>
            ))}
            {summaries.length > 2 ? <li className="text-text-muted">+{summaries.length - 2} more</li> : null}
          </ul>
        ) : (
          <p className="mt-1 text-text-muted">No windows configured yet.</p>
        )}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-xs text-text-secondary">{nonDefaultSlots.length} windows + default</span>
        <Dialog.Root
          open={open}
          onOpenChange={(nextOpen) => {
            setOpen(nextOpen);
            if (!nextOpen) {
              resetDraftState();
            }
          }}
        >
          <Dialog.Trigger asChild>
            <Button variant="secondary" size="sm" className="h-7 px-2 text-[10px]">
              Edit
            </Button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-[60] bg-overlay/50" />
            <Dialog.Content className="fixed left-1/2 top-1/2 z-[70] flex max-h-[calc(100vh-2rem)] w-full max-w-xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-border bg-bg-surface shadow-xl">
              <div className="shrink-0 border-b border-border px-5 pb-4 pt-5">
                <Dialog.Title className="text-base font-semibold text-text-primary">
                  Edit Time Route {id}
                </Dialog.Title>
                <Dialog.Description className="mt-1 text-xs text-text-secondary">
                  Update timezone and time windows. Routing targets remain graph-driven.
                </Dialog.Description>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                <div className="space-y-3">
                  <label className="block">
                    <span className="mb-1 block text-xs text-text-secondary">Timezone</span>
                    <input
                      value={draftTimezone}
                      onChange={(event) => setDraftTimezone(event.target.value)}
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                    />
                  </label>

                  <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-bg-elevated/70 px-3 py-2">
                    <span className="text-xs text-text-secondary">Windows</span>
                    <div className="inline-flex items-center gap-1 rounded border border-border px-1 py-0.5 text-[10px] text-text-muted">
                      <button
                        type="button"
                        className="h-4 w-4 rounded border border-border text-[10px] text-text-secondary hover:text-text-primary"
                        onClick={() => adjustOutputs(-1)}
                        aria-label="Decrease windows"
                      >
                        -
                      </button>
                      <span className="min-w-[16px] text-center">{nonDefaultSlots.length}</span>
                      <button
                        type="button"
                        className="h-4 w-4 rounded border border-border text-[10px] text-text-secondary hover:text-text-primary"
                        onClick={() => adjustOutputs(1)}
                        aria-label="Increase windows"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {nonDefaultSlots.map((slot) => (
                    <div key={slot} className="rounded-md border border-border bg-bg-elevated/70 p-3">
                      <label className="block">
                        <span className="mb-1 block text-xs text-text-secondary">{slot} label</span>
                        <input
                          value={draftWindows[slot]?.label ?? ""}
                          onChange={(event) => updateDraftWindow(slot, "label", event.target.value)}
                          className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                        />
                      </label>
                      <div className="mt-3 grid grid-cols-2 gap-3">
                        <label className="block">
                          <span className="mb-1 block text-xs text-text-secondary">Start</span>
                          <input
                            value={draftWindows[slot]?.start ?? ""}
                            onChange={(event) => updateDraftWindow(slot, "start", event.target.value)}
                            placeholder="09:00"
                            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                          />
                        </label>
                        <label className="block">
                          <span className="mb-1 block text-xs text-text-secondary">End</span>
                          <input
                            value={draftWindows[slot]?.end ?? ""}
                            onChange={(event) => updateDraftWindow(slot, "end", event.target.value)}
                            placeholder="17:00"
                            className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
                          />
                        </label>
                      </div>
                    </div>
                  ))}

                  <div className="rounded-md border border-border bg-bg-elevated/70 px-3 py-2 text-xs text-text-secondary">
                    Default output uses the <span className="font-mono">default</span> handle.
                  </div>

                  {error ? <p className="text-xs text-fail">{error}</p> : null}
                  {nodeErrors.length > 0 ? (
                    <ul className="space-y-1 rounded-md border border-fail-border bg-fail-bg px-3 py-2 text-xs text-fail">
                      {nodeErrors.map((message) => (
                        <li key={message}>{message}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>

              <div className="shrink-0 flex justify-end gap-2 border-t border-border px-5 py-4">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    resetDraftState();
                    setOpen(false);
                  }}
                >
                  Cancel
                </Button>
                <Button variant="primary" size="sm" onClick={handleSave}>
                  Save
                </Button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </div>
  );
}
