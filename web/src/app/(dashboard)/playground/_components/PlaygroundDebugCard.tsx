import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { PlaygroundDebugEntry } from "@/lib/playground-debug";

export function PlaygroundDebugCard({
  debugEntries,
  debugPanelOpen,
  onToggle,
  className = "",
}: {
  debugEntries: PlaygroundDebugEntry[];
  debugPanelOpen: boolean;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <Card data-testid="playground-debug-panel" className={className}>
      <CardHeader>
        <div className="flex w-full items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
              Harness Reasoning
            </p>
            <h2 className="mt-1 text-base font-semibold text-text-primary">
              AI Debug
            </h2>
            <p className="mt-1 text-xs text-text-muted">
              Caller reasoning summaries and decision events for AI playground runs.
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            data-testid="playground-debug-toggle"
            onClick={onToggle}
          >
            {debugPanelOpen ? "Hide" : "Show"}
          </Button>
        </div>
      </CardHeader>
      <CardBody>
        {debugPanelOpen ? (
          debugEntries.length === 0 ? (
            <p className="text-sm text-text-muted">
              No harness reasoning events yet. Launch an AI playground run to populate this panel.
            </p>
          ) : (
            <div className="space-y-3">
              {debugEntries.map((entry) => (
                <div
                  key={`${entry.sequenceNumber}-${entry.kind}`}
                  className="rounded-lg border border-border bg-bg-elevated px-3 py-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                      {entry.title}
                    </p>
                    <div className="flex items-center gap-2 text-[11px] text-text-muted">
                      {entry.confidence !== null ? (
                        <span>confidence {(entry.confidence * 100).toFixed(0)}%</span>
                      ) : null}
                      <span>#{entry.sequenceNumber}</span>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-text-primary">{entry.body}</p>
                </div>
              ))}
            </div>
          )
        ) : (
          <p className="text-sm text-text-muted">
            Expand this panel to inspect AI harness classifier and reasoning summaries.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
