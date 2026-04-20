import type { ConversationTurn, ProviderCircuitState } from "@/lib/api/types";

interface LatencySummary {
  samples: number;
  avgMs: number | null;
  p95Ms: number | null;
  maxMs: number | null;
}

interface AiLatencyBreakdown {
  replyGap: LatencySummary;
  botTurnDuration: LatencySummary;
  harnessPlayback: LatencySummary;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function summarize(values: number[]): LatencySummary {
  if (values.length === 0) {
    return {
      samples: 0,
      avgMs: null,
      p95Ms: null,
      maxMs: null,
    };
  }
  const sorted = [...values].sort((left, right) => left - right);
  const avgMs = sorted.reduce((sum, value) => sum + value, 0) / sorted.length;
  const p95Index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1);
  return {
    samples: sorted.length,
    avgMs,
    p95Ms: sorted[p95Index],
    maxMs: sorted[sorted.length - 1],
  };
}

export function deriveAiLatencyBreakdown(turns: ConversationTurn[]): AiLatencyBreakdown {
  const replyGapValues: number[] = [];
  const botTurnDurationValues: number[] = [];
  const harnessPlaybackValues: number[] = [];

  for (let index = 0; index < turns.length; index += 1) {
    const turn = turns[index];
    const startMs = asNumber(turn.audio_start_ms);
    const endMs = asNumber(turn.audio_end_ms);
    if (startMs !== null && endMs !== null && endMs >= startMs) {
      const durationMs = endMs - startMs;
      if (turn.speaker === "bot") {
        botTurnDurationValues.push(durationMs);
      } else if (turn.speaker === "harness") {
        harnessPlaybackValues.push(durationMs);
      }
    }

    const nextTurn = turns[index + 1];
    if (!nextTurn || turn.speaker !== "bot" || nextTurn.speaker !== "harness") {
      continue;
    }
    const botEndMs = asNumber(turn.audio_end_ms);
    const harnessStartMs = asNumber(nextTurn.audio_start_ms);
    if (botEndMs !== null && harnessStartMs !== null && harnessStartMs >= botEndMs) {
      replyGapValues.push(harnessStartMs - botEndMs);
    }
  }

  return {
    replyGap: summarize(replyGapValues),
    botTurnDuration: summarize(botTurnDurationValues),
    harnessPlayback: summarize(harnessPlaybackValues),
  };
}

export function hasAiLatencySamples(breakdown: AiLatencyBreakdown | null | undefined): boolean {
  if (!breakdown) {
    return false;
  }
  return (
    breakdown.replyGap.samples > 0 ||
    breakdown.botTurnDuration.samples > 0 ||
    breakdown.harnessPlayback.samples > 0
  );
}

export function aiLatencyDegradedComponents(
  circuits: ProviderCircuitState[] | undefined,
): string[] {
  if (!circuits || circuits.length === 0) {
    return [];
  }
  return circuits
    .filter(
      (circuit) =>
        circuit.source === "agent" &&
        (circuit.component === "agent_live_tts" || circuit.component === "agent_ai_caller") &&
        (circuit.state === "open" || circuit.state === "half_open"),
    )
    .map((circuit) => `${circuit.component}:${circuit.state}`);
}

export function formatLatencyMs(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${Math.round(value)} ms`;
}
