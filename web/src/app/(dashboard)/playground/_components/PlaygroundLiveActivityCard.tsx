import { type ReactNode, type RefObject } from "react";
import { Activity, Pause, Play, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { PlaygroundFeedDescriptor, PlaygroundStreamEvent, PlaygroundStreamState } from "@/lib/playground-stream";
import { type PlaygroundMode } from "@/lib/playground";

type FeedItem = {
  event: PlaygroundStreamEvent;
  descriptor: PlaygroundFeedDescriptor;
};

export function PlaygroundLiveActivityCard({
  runId,
  completionEvent,
  stream,
  feedItems,
  feedViewportRef,
  autoScroll,
  onToggleAutoScroll,
  mode,
  debugPanel,
}: {
  runId: string | null;
  completionEvent: PlaygroundStreamEvent | null;
  stream: PlaygroundStreamState;
  feedItems: FeedItem[];
  feedViewportRef: RefObject<HTMLDivElement | null>;
  autoScroll: boolean;
  onToggleAutoScroll: () => void;
  mode: PlaygroundMode;
  debugPanel?: ReactNode;
}) {
  return (
    <Card className="min-h-[640px]">
      <CardHeader>
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
            Live Activity
          </p>
          <h2 className="mt-1 text-base font-semibold text-text-primary">
            Session Feed
          </h2>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {completionEvent ? (
          <div
            data-testid="playground-summary-bar"
            className="rounded-xl border border-pass/20 bg-pass/10 px-4 py-3"
          >
            <p className="text-[11px] uppercase tracking-[0.16em] text-pass">
              Run Complete
            </p>
            <p className="mt-1 text-sm font-medium text-text-primary">
              {String(completionEvent.payload.summary ?? "Playground run completed.")}
            </p>
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-bg-base/50 px-4 py-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">
              Stream Status
            </p>
            <div className="mt-1 flex items-center gap-2">
              <Activity className="h-4 w-4 text-brand" />
              <p className="text-sm font-medium text-text-primary">
                {runId ? stream.status : "idle"}
              </p>
            </div>
            <p className="mt-1 text-xs text-text-muted">
              {stream.events.length} event{stream.events.length === 1 ? "" : "s"} received
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={onToggleAutoScroll}
            disabled={!runId}
          >
            {autoScroll ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {autoScroll ? "Pause Scroll" : "Resume Scroll"}
          </Button>
        </div>

        {stream.error ? (
          <div className="rounded-lg border border-fail-border bg-fail/5 px-4 py-3 text-sm text-fail">
            {stream.error}
          </div>
        ) : null}

        <div
          ref={feedViewportRef}
          data-testid="playground-activity-feed"
          className="flex min-h-[460px] max-h-[640px] flex-col gap-3 overflow-y-auto rounded-xl border border-border bg-bg-base/40 p-4"
        >
          {!runId ? (
            <div className="my-auto text-center">
              <p className="text-base font-medium text-text-primary">Waiting for a playground run</p>
              <p className="mt-2 text-sm text-text-muted">
                Launch a mock or direct HTTP run to start the live event feed.
              </p>
            </div>
          ) : feedItems.length === 0 ? (
            <div className="my-auto text-center">
              <p className="text-base font-medium text-text-primary">Connected and waiting</p>
              <p className="mt-2 text-sm text-text-muted">
                The feed will populate as harness turns, bot replies, and branch decisions arrive.
              </p>
            </div>
          ) : (
            feedItems.map(({ event, descriptor }) => {
              const isBubble = descriptor.kind === "bubble";
              const alignmentClass =
                descriptor.side === "right"
                  ? "items-end"
                  : descriptor.side === "left"
                    ? "items-start"
                    : "items-center";
              const cardClass = isBubble
                ? descriptor.side === "right"
                  ? "max-w-[85%] rounded-2xl rounded-br-md border border-brand/20 bg-brand/8 px-4 py-3"
                  : "max-w-[85%] rounded-2xl rounded-bl-md border border-border bg-bg-elevated px-4 py-3"
                : "w-full rounded-xl border border-border bg-bg-elevated px-4 py-3";

              return (
                <div
                  key={event.sequence_number}
                  className={`flex flex-col ${alignmentClass}`}
                  data-testid={`playground-event-${event.sequence_number}`}
                >
                  <div className={cardClass}>
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted">
                        {descriptor.title}
                      </p>
                      <p className="text-[11px] text-text-muted">#{event.sequence_number}</p>
                    </div>
                    {descriptor.body ? (
                      <p className="mt-2 whitespace-pre-wrap text-sm text-text-primary">
                        {descriptor.body}
                      </p>
                    ) : null}
                    {descriptor.chips && descriptor.chips.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {descriptor.chips.map((chip) => (
                          <span
                            key={`${event.sequence_number}-${chip.label}`}
                            className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                              chip.tone === "pass"
                                ? "bg-pass/10 text-pass"
                                : chip.tone === "fail"
                                  ? "bg-fail/10 text-fail"
                                  : "bg-warn/10 text-warn"
                            }`}
                          >
                            {chip.label}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {descriptor.collapsedDetail ? (
                      <p className="mt-2 text-xs text-text-muted">{descriptor.collapsedDetail}</p>
                    ) : null}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {mode === "mock" ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-3 py-1.5 text-xs text-text-secondary">
            <Sparkles className="h-3.5 w-3.5" />
            Mock mode uses the tenant default model with your supplied system prompt.
          </div>
        ) : null}

        {debugPanel ?? null}
      </CardBody>
    </Card>
  );
}

