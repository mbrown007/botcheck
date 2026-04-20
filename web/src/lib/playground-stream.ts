import { useEffect, useRef, useState } from "react";

import { authHeaders, BASE_URL, ApiHttpError } from "@/lib/api/fetcher";
import type { ScenarioDefinition } from "@/lib/api/types";

export interface PlaygroundStreamEvent {
  run_id: string;
  sequence_number: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface PlaygroundFeedDescriptor {
  kind: "bubble" | "status" | "expectation" | "tool";
  side: "left" | "right" | "center";
  title: string;
  body: string | null;
  tone: "default" | "pending" | "pass" | "fail" | "warn";
  chips?: Array<{ label: string; tone: "pass" | "fail" | "warn" }>;
  collapsedDetail?: string | null;
}

export interface PlaygroundStreamState {
  events: PlaygroundStreamEvent[];
  status: "idle" | "connecting" | "live" | "reconnecting" | "complete" | "error";
  error: string | null;
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function extractSseFrames(buffer: string): {
  frames: string[];
  remainder: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  if (parts.length === 1) {
    return { frames: [], remainder: normalized };
  }
  return {
    frames: parts.slice(0, -1).filter((part) => part.trim().length > 0),
    remainder: parts.at(-1) ?? "",
  };
}

export function parseSseFrame(frame: string): PlaygroundStreamEvent | null {
  let id: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const parsed = JSON.parse(dataLines.join("\n")) as Partial<PlaygroundStreamEvent>;
  const sequenceNumber =
    typeof parsed.sequence_number === "number"
      ? parsed.sequence_number
      : Number.parseInt(id ?? "", 10);

  if (!Number.isFinite(sequenceNumber)) {
    return null;
  }

  return {
    run_id: String(parsed.run_id ?? ""),
    sequence_number: sequenceNumber,
    event_type: String(parsed.event_type ?? ""),
    payload:
      parsed.payload && typeof parsed.payload === "object"
        ? (parsed.payload as Record<string, unknown>)
        : {},
    created_at: String(parsed.created_at ?? ""),
  };
}

function branchAlternatives(
  event: PlaygroundStreamEvent,
  scenario: ScenarioDefinition | null | undefined
): string[] {
  const selected = asText(event.payload.selected_case);
  if (!scenario || !selected) {
    return [];
  }
  const turn = scenario.turns.find((candidate) => candidate.id === asText(event.payload.turn_id));
  const cases = Array.isArray(turn?.branching?.cases) ? turn.branching.cases : [];
  return cases
    .map((item) =>
      item && typeof item === "object" && typeof item.condition === "string"
        ? item.condition.trim()
        : ""
    )
    .filter((condition) => condition && condition !== selected);
}

export function describePlaygroundStreamEvent(
  event: PlaygroundStreamEvent,
  scenario?: ScenarioDefinition | null
): PlaygroundFeedDescriptor | null {
  if (event.event_type.startsWith("harness.")) {
    return null;
  }
  const speaker = asText(event.payload.speaker);
  const transcript = asText(event.payload.transcript) ?? asText(event.payload.text);
  const turnId = asText(event.payload.turn_id);

  if (event.event_type === "turn.start") {
    if (speaker === "harness") {
      return {
        kind: "bubble",
        side: "right",
        title: "Harness",
        body: transcript ?? "Prompt sent.",
        tone: "default",
      };
    }
    return null;
  }

  if (event.event_type === "turn.response") {
    const latencyMs = asNumber(event.payload.latency_ms);
    if (turnId?.endsWith("_bot")) {
      return {
        kind: "bubble",
        side: "left",
        title: "Bot",
        body: transcript ?? "Bot responded.",
        tone: "default",
        collapsedDetail: latencyMs === null ? null : `${latencyMs}ms`,
      };
    }
    return null;
  }

  if (event.event_type === "turn.branch") {
    const selected = asText(event.payload.selected_case) ?? "default";
    const alternatives = branchAlternatives(event, scenario);
    return {
      kind: "status",
      side: "center",
      title: "Branch Decision",
      body: `Selected ${selected}.`,
      tone: "warn",
      collapsedDetail:
        alternatives.length > 0
          ? `${alternatives.length} other path${alternatives.length === 1 ? "" : "s"} hidden`
          : null,
    };
  }

  if (event.event_type === "turn.expect") {
    const assertion = asText(event.payload.assertion) ?? "assertion";
    const passed = event.payload.passed === true;
    return {
      kind: "expectation",
      side: "center",
      title: "Expectation",
      body: null,
      tone: passed ? "pass" : "fail",
      chips: [
        { label: assertion, tone: passed ? "pass" : "fail" },
        { label: passed ? "passed" : "failed", tone: passed ? "pass" : "fail" },
      ],
    };
  }

  if (event.event_type.startsWith("tool.")) {
    return {
      kind: "tool",
      side: "center",
      title: formatToolEventTitle(event.event_type),
      body: transcript ?? asText(event.payload.summary) ?? "Tool activity recorded.",
      tone: "pending",
    };
  }

  if (event.event_type === "run.complete") {
    return {
      kind: "status",
      side: "center",
      title: "Run Complete",
      body: asText(event.payload.summary) ?? "Playground run completed.",
      tone: "pass",
    };
  }

  return {
    kind: "status",
    side: "center",
    title: event.event_type.replace(/\./g, " "),
    body: transcript ?? asText(event.payload.summary) ?? "State update recorded.",
    tone: "pending",
  };
}

function formatToolEventTitle(eventType: string): string {
  return eventType
    .replace(/^tool\./, "")
    .split(".")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

export function usePlaygroundEventStream(runId: string | null): PlaygroundStreamState {
  const [events, setEvents] = useState<PlaygroundStreamEvent[]>([]);
  const [status, setStatus] = useState<PlaygroundStreamState["status"]>("idle");
  const [error, setError] = useState<string | null>(null);
  const seenSequencesRef = useRef<Set<number>>(new Set());
  const lastEventIdRef = useRef(0);

  useEffect(() => {
    setEvents([]);
    setStatus(runId ? "connecting" : "idle");
    setError(null);
    seenSequencesRef.current = new Set();
    lastEventIdRef.current = 0;

    if (!runId) {
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;
    let controller: AbortController | null = null;

    const connect = async () => {
      if (cancelled) {
        return;
      }
      controller = new AbortController();
      setStatus((current) =>
        current === "idle" || current === "connecting" ? "connecting" : "reconnecting"
      );
      try {
        const baseHeaders = await authHeaders();
        const headers: Record<string, string> =
          baseHeaders instanceof Headers
            ? Object.fromEntries(baseHeaders.entries())
            : Array.isArray(baseHeaders)
              ? Object.fromEntries(baseHeaders)
              : { ...baseHeaders };
        if (lastEventIdRef.current > 0) {
          headers["Last-Event-ID"] = String(lastEventIdRef.current);
        }
        const response = await fetch(`${BASE_URL}/runs/${runId}/stream`, {
          headers,
          signal: controller.signal,
        });
        if (!response.ok) {
          const body = await response.text();
          throw new ApiHttpError("Playground stream failed", response.status, body);
        }
        if (!response.body) {
          throw new Error("Playground stream response body is unavailable.");
        }
        setStatus("live");
        setError(null);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const extracted = extractSseFrames(buffer);
          buffer = extracted.remainder;
          for (const frame of extracted.frames) {
            const parsed = parseSseFrame(frame);
            if (!parsed) {
              continue;
            }
            if (seenSequencesRef.current.has(parsed.sequence_number)) {
              continue;
            }
            seenSequencesRef.current.add(parsed.sequence_number);
            lastEventIdRef.current = Math.max(lastEventIdRef.current, parsed.sequence_number);
            setEvents((current) => [...current, parsed]);
            if (parsed.event_type === "run.complete") {
              setStatus("complete");
              await reader.cancel();
              return;
            }
          }
        }

        if (!cancelled) {
          setStatus((current) => (current === "complete" ? current : "reconnecting"));
          reconnectTimer = window.setTimeout(() => {
            void connect();
          }, 800);
        }
      } catch (streamError) {
        if (cancelled || (streamError instanceof Error && streamError.name === "AbortError")) {
          return;
        }
        const message =
          streamError instanceof Error ? streamError.message : "Failed to connect playground stream.";
        setError(message);
        setStatus("error");
      }
    };

    void connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      controller?.abort();
    };
  }, [runId]);

  return { events, status, error };
}
