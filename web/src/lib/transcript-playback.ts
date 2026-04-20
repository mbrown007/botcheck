import type { ConversationTurn } from "@/lib/api/types";

const START_TOLERANCE_MS = 150;
const END_TOLERANCE_MS = 250;
const NEAREST_FALLBACK_MAX_DISTANCE_MS = 600;

function asFiniteNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function comparePreferredTurn(
  left: ConversationTurn,
  right: ConversationTurn,
): number {
  const leftStart = asFiniteNumber(left.audio_start_ms) ?? Number.NEGATIVE_INFINITY;
  const rightStart = asFiniteNumber(right.audio_start_ms) ?? Number.NEGATIVE_INFINITY;
  if (leftStart !== rightStart) {
    return rightStart - leftStart;
  }

  const leftEnd = asFiniteNumber(left.audio_end_ms) ?? Number.POSITIVE_INFINITY;
  const rightEnd = asFiniteNumber(right.audio_end_ms) ?? Number.POSITIVE_INFINITY;
  return leftEnd - rightEnd;
}

function distanceToTurnWindow(turn: ConversationTurn, currentTimeMs: number): number | null {
  const start = asFiniteNumber(turn.audio_start_ms);
  const end = asFiniteNumber(turn.audio_end_ms);
  if (start === null || end === null || end < start) {
    return null;
  }

  if (currentTimeMs < start) {
    return start - currentTimeMs;
  }
  if (currentTimeMs > end) {
    return currentTimeMs - end;
  }
  return 0;
}

export function findActiveTranscriptTurn(
  turns: ConversationTurn[],
  currentTimeMs?: number,
): ConversationTurn | undefined {
  if (currentTimeMs === undefined || !Number.isFinite(currentTimeMs) || currentTimeMs < 0) {
    return undefined;
  }

  const exactMatches = turns
    .filter((turn) => {
      const start = asFiniteNumber(turn.audio_start_ms);
      const end = asFiniteNumber(turn.audio_end_ms);
      return start !== null && end !== null && end >= start && currentTimeMs >= start && currentTimeMs <= end;
    })
    .sort(comparePreferredTurn);

  if (exactMatches.length > 0) {
    return exactMatches[0];
  }

  const nearMatches = turns
    .map((turn) => {
      const start = asFiniteNumber(turn.audio_start_ms);
      const end = asFiniteNumber(turn.audio_end_ms);
      if (start === null || end === null || end < start) {
        return null;
      }
      const expandedStart = start - START_TOLERANCE_MS;
      const expandedEnd = end + END_TOLERANCE_MS;
      if (currentTimeMs < expandedStart || currentTimeMs > expandedEnd) {
        return null;
      }
      return {
        turn,
        distance: distanceToTurnWindow(turn, currentTimeMs) ?? Number.POSITIVE_INFINITY,
      };
    })
    .filter((value): value is { turn: ConversationTurn; distance: number } => value !== null)
    .sort((left, right) => left.distance - right.distance || comparePreferredTurn(left.turn, right.turn));

  if (nearMatches.length > 0) {
    return nearMatches[0].turn;
  }

  const nearest = turns
    .map((turn) => {
      const distance = distanceToTurnWindow(turn, currentTimeMs);
      if (distance === null || distance > NEAREST_FALLBACK_MAX_DISTANCE_MS) {
        return null;
      }
      return { turn, distance };
    })
    .filter((value): value is { turn: ConversationTurn; distance: number } => value !== null)
    .sort((left, right) => left.distance - right.distance || comparePreferredTurn(left.turn, right.turn));

  return nearest[0]?.turn;
}
