import assert from "node:assert/strict";
import test from "node:test";
import type { ConversationTurn } from "@/lib/api/types";
import { findActiveTranscriptTurn } from "@/lib/transcript-playback";

function turn(
  turnId: string,
  speaker: "harness" | "bot",
  audioStartMs?: number,
  audioEndMs?: number,
): ConversationTurn {
  return {
    turn_id: turnId,
    speaker,
    text: turnId,
    audio_start_ms: audioStartMs,
    audio_end_ms: audioEndMs,
  };
}

test("findActiveTranscriptTurn highlights the first turn at 0ms", () => {
  const result = findActiveTranscriptTurn(
    [turn("bot-1", "bot", 0, 700), turn("harness-1", "harness", 900, 1400)],
    0,
  );

  assert.equal(result?.turn_id, "bot-1");
});

test("findActiveTranscriptTurn uses start/end tolerance near boundaries", () => {
  const turns = [turn("bot-1", "bot", 1000, 1600)];

  assert.equal(findActiveTranscriptTurn(turns, 900)?.turn_id, "bot-1");
  assert.equal(findActiveTranscriptTurn(turns, 1800)?.turn_id, "bot-1");
});

test("findActiveTranscriptTurn prefers the turn whose real window contains the playback position", () => {
  const turns = [
    turn("bot-1", "bot", 0, 1000),
    turn("harness-1", "harness", 1001, 1500),
  ];

  const result = findActiveTranscriptTurn(turns, 1100);

  assert.equal(result?.turn_id, "harness-1");
});

test("findActiveTranscriptTurn falls back to the nearest turn for small gaps", () => {
  const result = findActiveTranscriptTurn(
    [turn("bot-1", "bot", 0, 700), turn("harness-1", "harness", 1400, 1800)],
    1100,
  );

  assert.equal(result?.turn_id, "harness-1");
});

test("findActiveTranscriptTurn returns undefined when playback is too far from any turn", () => {
  const result = findActiveTranscriptTurn(
    [turn("bot-1", "bot", 0, 300), turn("harness-1", "harness", 2000, 2300)],
    1100,
  );

  assert.equal(result, undefined);
});

test("findActiveTranscriptTurn ignores invalid timing windows", () => {
  const result = findActiveTranscriptTurn(
    [turn("broken", "bot", 500, 100), turn("valid", "harness", 900, 1200)],
    950,
  );

  assert.equal(result?.turn_id, "valid");
});
