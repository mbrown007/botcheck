import type { PackRunChildSummary, RunEvent, RunResponse } from "@/lib/api/types";

interface RunMonitorPhase {
  label: string;
  description: string;
  tone: "pending" | "warn" | "pass" | "fail";
}

interface PackRunMonitorPhase {
  label: string;
  description: string;
  tone: "pending" | "warn" | "pass" | "fail";
}

interface PackRunActivityItem {
  id: string;
  title: string;
  statusLabel: string;
  tone: "pending" | "warn" | "pass" | "fail";
  detail: string;
  summary: string | null;
}

export function deriveRunMonitorPhase(
  run: Pick<RunResponse, "state" | "conversation" | "error_code" | "end_reason">
): RunMonitorPhase {
  const state = run.state.trim().toLowerCase();

  if (state === "pending") {
    return {
      label: "Queued",
      description: "Run created and waiting for the harness to start the call.",
      tone: "pending",
    };
  }

  if (state === "running") {
    if ((run.conversation?.length ?? 0) === 0) {
      return {
        label: "Starting Call",
        description: "Call setup is in progress. Waiting for the first live turn.",
        tone: "warn",
      };
    }
    return {
      label: "Conversation Live",
      description: "Turns are being recorded in real time.",
      tone: "warn",
    };
  }

  if (state === "judging") {
    return {
      label: "Judging",
      description: "The run is complete and the judge is producing scores and findings.",
      tone: "warn",
    };
  }

  if (state === "complete") {
    return {
      label: "Complete",
      description: "Run finished successfully and results are available.",
      tone: "pass",
    };
  }

  if (state === "failed" || state === "error") {
    return {
      label: "Failed",
      description:
        run.error_code?.trim() || run.end_reason?.trim() || "Run ended with an error condition.",
      tone: "fail",
    };
  }

  return {
    label: run.state,
    description: "Run state update received.",
    tone: "pending",
  };
}

export function formatRunEventLabel(type: string): string {
  const normalized = type.trim();
  if (!normalized) {
    return "event";
  }
  return normalized.replace(/_/g, " ");
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function describeRunEvent(event: RunEvent): string {
  const detail = event.detail ?? {};
  switch (event.type) {
    case "run_created":
      return "Run accepted and queued for execution.";
    case "turn_started":
      return `Turn ${asNonEmptyString(detail.turn_id) ?? "unknown"} started.`;
    case "turn_completed":
      return `Turn ${asNonEmptyString(detail.turn_id) ?? "unknown"} completed.`;
    case "branch_decision":
      return `Branch matched ${asNonEmptyString(detail.condition_matched) ?? "default route"}.`;
    case "judge_enqueued":
      return "Judge job enqueued.";
    case "judge_reenqueued":
      return "Judge job re-enqueued.";
    case "run_complete":
      return "Run marked complete.";
    case "run_failed":
      return asNonEmptyString(detail.reason) ?? "Run marked failed.";
    case "run_stopped":
      return asNonEmptyString(detail.reason) ?? "Run stopped by operator.";
    case "recording_ready":
      return "Recording uploaded and available.";
    default:
      return "State update recorded.";
  }
}

export function latestRunEvents(events: RunEvent[] | undefined, limit = 10): RunEvent[] {
  return [...(events ?? [])].slice(-limit).reverse();
}

export function derivePackRunMonitorPhase(state: string): PackRunMonitorPhase {
  const normalized = state.trim().toLowerCase();
  if (normalized === "pending") {
    return {
      label: "Queued",
      description: "Pack run is queued and waiting for dispatch.",
      tone: "pending",
    };
  }
  if (normalized === "running") {
    return {
      label: "Dispatching",
      description: "Child runs are being created and executed.",
      tone: "warn",
    };
  }
  if (normalized === "complete") {
    return {
      label: "Complete",
      description: "All child runs completed successfully.",
      tone: "pass",
    };
  }
  if (normalized === "partial" || normalized === "failed" || normalized === "cancelled") {
    return {
      label: normalized === "partial" ? "Partial" : "Failed",
      description: "One or more child runs did not complete cleanly.",
      tone: "fail",
    };
  }
  return {
    label: state,
    description: "Pack run state update received.",
    tone: "pending",
  };
}

function normalize(value: string | null | undefined): string {
  return value?.trim().toLowerCase() ?? "";
}

function packChildTone(child: Pick<PackRunChildSummary, "state" | "run_state" | "failure_category" | "gate_result">) {
  const itemState = normalize(child.state);
  const runState = normalize(child.run_state);
  const failureCategory = normalize(child.failure_category);
  const gateResult = normalize(child.gate_result);

  if (
    itemState === "failed" ||
    runState === "failed" ||
    runState === "error" ||
    failureCategory === "dispatch_error" ||
    failureCategory === "run_error"
  ) {
    return "fail" as const;
  }
  if (itemState === "blocked" || gateResult === "blocked" || failureCategory === "gate_blocked") {
    return "warn" as const;
  }
  if (itemState === "dispatched" || itemState === "running" || runState === "running") {
    return "warn" as const;
  }
  if (itemState === "complete" || runState === "complete") {
    return "pass" as const;
  }
  return "pending" as const;
}

function packChildStatusLabel(child: Pick<PackRunChildSummary, "state" | "run_state" | "failure_category" | "gate_result">): string {
  const failureCategory = normalize(child.failure_category);
  if (failureCategory === "dispatch_error") {
    return "Dispatch Failed";
  }
  if (failureCategory === "run_error") {
    return "Run Failed";
  }
  if (failureCategory === "gate_blocked" || normalize(child.gate_result) === "blocked") {
    return "Blocked";
  }
  if (normalize(child.run_state) === "running" || normalize(child.state) === "running") {
    return "Running";
  }
  if (normalize(child.state) === "dispatched") {
    return "Dispatched";
  }
  if (normalize(child.run_state) === "complete" || normalize(child.state) === "complete") {
    return "Complete";
  }
  return child.state || child.run_state || "Pending";
}

function packChildDetail(child: Pick<PackRunChildSummary, "run_id" | "error_code" | "duration_s" | "gate_result">): string {
  if (child.error_code?.trim()) {
    return child.error_code.trim();
  }
  if (normalize(child.gate_result) === "blocked") {
    return "Scenario completed but failed the configured gate.";
  }
  if (typeof child.duration_s === "number" && Number.isFinite(child.duration_s)) {
    return `${child.duration_s.toFixed(1)}s`;
  }
  if (child.run_id?.trim()) {
    return child.run_id.trim();
  }
  return "Queued for child dispatch.";
}

export function latestPackRunActivity(
  children: PackRunChildSummary[] | undefined,
  limit = 6,
): PackRunActivityItem[] {
  return [...(children ?? [])]
    .sort((left, right) => {
      const leftCreated = left.created_at ? Date.parse(left.created_at) : 0;
      const rightCreated = right.created_at ? Date.parse(right.created_at) : 0;
      return rightCreated - leftCreated || left.order_index - right.order_index;
    })
    .slice(0, limit)
    .map((child) => ({
      id: child.pack_run_item_id,
      title: child.ai_scenario_id ?? child.scenario_id,
      statusLabel: packChildStatusLabel(child),
      tone: packChildTone(child),
      detail: packChildDetail(child),
      summary: child.summary?.trim() || null,
    }));
}
