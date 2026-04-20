"use client";

import { Card, CardBody } from "@/components/ui/card";

interface RunAiContext {
  persona_id: string;
  persona_name?: string | null;
  scenario_objective?: string | null;
  dataset_input: string;
  expected_output: string;
}

export function RunAiContextCard({ aiContext }: { aiContext: RunAiContext | null }) {
  if (!aiContext) {
    return null;
  }

  return (
    <Card>
      <CardBody className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-text-muted">AI Scenario Context</p>
        <p className="text-xs text-text-secondary">
          persona:{" "}
          <span className="font-mono text-text-primary">
            {aiContext.persona_name || aiContext.persona_id}
          </span>
        </p>
        {aiContext.scenario_objective ? (
          <p className="text-xs text-text-secondary">
            objective: <span className="text-text-primary">{aiContext.scenario_objective}</span>
          </p>
        ) : null}
        <div className="rounded border border-border bg-bg-elevated p-3">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Dataset Input</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-text-primary">
            {aiContext.dataset_input}
          </p>
        </div>
        <div className="rounded border border-border bg-bg-elevated p-3">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Expected Output</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-text-primary">
            {aiContext.expected_output}
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
