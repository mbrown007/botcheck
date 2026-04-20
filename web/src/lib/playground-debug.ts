import type { PlaygroundStreamEvent } from "@/lib/playground-stream";

export interface PlaygroundDebugEntry {
  sequenceNumber: number;
  kind: "reasoning" | "classifier_input" | "classifier_output";
  title: string;
  body: string;
  confidence: number | null;
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asConfidence(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function derivePlaygroundDebugEntries(
  events: PlaygroundStreamEvent[]
): PlaygroundDebugEntry[] {
  return events.flatMap<PlaygroundDebugEntry>((event) => {
    if (event.event_type === "harness.caller_reasoning") {
      const summary = asText(event.payload.summary);
      return summary
        ? [
            {
              sequenceNumber: event.sequence_number,
              kind: "reasoning",
              title: "Caller reasoning",
              body: summary,
              confidence: null,
            },
          ]
        : [];
    }
    if (event.event_type === "harness.classifier_input") {
      const transcript = asText(event.payload.transcript);
      return transcript
        ? [
            {
              sequenceNumber: event.sequence_number,
              kind: "classifier_input",
              title: "Classifier input",
              body: transcript,
              confidence: null,
            },
          ]
        : [];
    }
    if (event.event_type === "harness.classifier_output") {
      const selectedCase = asText(event.payload.selected_case);
      return selectedCase
        ? [
            {
              sequenceNumber: event.sequence_number,
              kind: "classifier_output",
              title: "Classifier output",
              body: selectedCase,
              confidence: asConfidence(event.payload.confidence),
            },
          ]
        : [];
    }
    return [];
  });
}
