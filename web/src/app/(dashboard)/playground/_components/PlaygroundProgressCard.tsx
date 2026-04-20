import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { AIScenarioSummary, ScenarioDefinition } from "@/lib/api/types";
import type { PlaygroundProgressNode } from "@/lib/playground-progress";
import { progressStatusClasses, progressStatusIcon } from "./playground-types";

export function PlaygroundProgressCard({
  progressScenario,
  selectedAIScenario,
  progressNodes,
  completionRunId,
}: {
  progressScenario: ScenarioDefinition | null;
  selectedAIScenario: AIScenarioSummary | null;
  progressNodes: PlaygroundProgressNode[];
  completionRunId: string | null;
}) {
  return (
    <Card className="min-h-[640px] xl:sticky xl:top-6">
      <CardHeader>
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
            Scenario Progress
          </p>
          <h2 className="mt-1 text-base font-semibold text-text-primary">
            Turn Path
          </h2>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {progressScenario ? (
          <div className="rounded-xl border border-border bg-bg-base/50 px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
              Active Scenario
            </p>
            <p className="mt-1 text-sm font-medium text-text-primary">
              {progressScenario.name}
            </p>
            <p className="mt-1 text-xs text-text-muted">
              {progressScenario.turns.length} turns · {progressScenario.bot.protocol.toUpperCase()} transport
            </p>
          </div>
        ) : selectedAIScenario ? (
          <div className="rounded-xl border border-border bg-bg-base/50 px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
              AI Runtime Scenario
            </p>
            <p className="mt-1 text-sm font-medium text-text-primary">
              {selectedAIScenario.name}
            </p>
            <p className="mt-1 text-xs text-text-muted">
              Launch the playground run to load the bound runtime graph and track turn-by-turn progress here.
            </p>
          </div>
        ) : null}

        <div
          data-testid="playground-progress-pane"
          className="flex min-h-[460px] flex-col gap-3 rounded-xl border border-border bg-bg-base/40 p-3"
        >
          {progressNodes.length === 0 ? (
            <div className="my-auto text-center">
              <p className="text-base font-medium text-text-primary">No runtime graph loaded</p>
              <p className="mt-2 text-sm text-text-muted">
                Select a graph scenario or launch an AI playground run to see turn progress.
              </p>
            </div>
          ) : (
            progressNodes.map((node) => (
              <div
                key={node.turnId}
                data-testid={`playground-progress-node-${node.turnId}`}
                className={`rounded-xl border px-3 py-3 ${progressStatusClasses(node.status)}`}
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 shrink-0">{progressStatusIcon(node.status)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-text-primary">{node.turnId}</p>
                      <span className="rounded-full border border-border bg-bg-elevated px-2 py-0.5 text-[11px] font-medium text-text-secondary">
                        {node.statusLabel}
                      </span>
                    </div>
                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-text-muted">
                      {node.speaker}
                    </p>
                    <p className="mt-2 text-sm text-text-secondary">{node.textPreview}</p>
                    {node.caseStates.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {node.caseStates.map((item) => (
                          <span
                            key={`${node.turnId}-${item.condition}`}
                            className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                              item.status === "selected"
                                ? "bg-brand/12 text-brand"
                                : item.status === "dimmed"
                                  ? "bg-bg-elevated text-text-muted opacity-80"
                                  : "bg-bg-elevated text-text-secondary"
                            }`}
                          >
                            {item.condition}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {completionRunId ? (
          <Link
            href={`/runs/${completionRunId}`}
            className="inline-flex items-center gap-2 text-sm font-medium text-brand transition-colors hover:text-brand/80"
          >
            Open full run detail
            <ExternalLink className="h-4 w-4" />
          </Link>
        ) : null}
      </CardBody>
    </Card>
  );
}
