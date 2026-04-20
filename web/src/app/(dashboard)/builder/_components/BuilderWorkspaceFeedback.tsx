"use client";

import { cn } from "@/lib/utils";
import type { BuilderToast } from "../hooks/useBuilderToast";

interface BuilderWorkspaceFeedbackProps {
  loadError: string | null;
  parseError: string | null;
  redirectToAIScenarios: boolean;
  saveError: string | null;
  statusMessage: string | null;
  structuralErrorCount: number;
  toasts: BuilderToast[];
}

export function BuilderWorkspaceFeedback({
  loadError,
  parseError,
  redirectToAIScenarios,
  saveError,
  statusMessage,
  structuralErrorCount,
  toasts,
}: BuilderWorkspaceFeedbackProps) {
  const hasStructuralErrors = structuralErrorCount > 0;

  return (
    <>
      {(loadError || saveError || parseError || statusMessage || hasStructuralErrors || redirectToAIScenarios) && (
        <div className="space-y-2">
          {loadError && (
            <div className="rounded-md border border-fail-border bg-fail-bg px-4 py-3 text-sm text-fail">
              {loadError}
            </div>
          )}
          {saveError && (
            <div className="whitespace-pre-wrap rounded-md border border-fail-border bg-fail-bg px-4 py-3 text-sm text-fail">
              {saveError}
            </div>
          )}
          {parseError && (
            <div className="rounded-md border border-warn-border bg-warn-bg px-4 py-3 text-sm text-warn">
              YAML parse error: {parseError}
            </div>
          )}
          {hasStructuralErrors && (
            <div className="rounded-md border border-fail-border bg-fail-bg px-4 py-3 text-sm text-fail">
              Structural node issues detected on {structuralErrorCount} node
              {structuralErrorCount === 1 ? "" : "s"}.
            </div>
          )}
          {statusMessage && (
            <div className="rounded-md border border-pass-border bg-pass-bg px-4 py-3 text-sm text-pass">
              {statusMessage}
            </div>
          )}
          {redirectToAIScenarios && (
            <div className="rounded-md border border-warn-border bg-warn-bg px-4 py-3 text-sm text-text-secondary">
              Redirecting to AI Scenarios. AI scenarios are edited from the AI Scenarios
              workspace.
            </div>
          )}
        </div>
      )}

      {toasts.length > 0 && (
        <div className="pointer-events-none fixed bottom-4 right-4 z-[90] flex w-[320px] max-w-[calc(100vw-2rem)] flex-col gap-2">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={cn(
                "rounded-md border px-3 py-2 text-xs shadow-md",
                toast.tone === "error" && "border-fail-border bg-fail-bg text-fail",
                toast.tone === "warn" && "border-warn-border bg-warn-bg text-warn",
                toast.tone === "info" && "border-pass-border bg-pass-bg text-pass",
              )}
            >
              {toast.message}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
