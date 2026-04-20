import assert from "node:assert/strict";
import test from "node:test";
import type { BuilderTurn } from "../lib/builder-types";
import {
  mergeFormValuesIntoTurn,
  turnEditorFormSchema,
  turnToFormValues,
  type TurnEditorFormValues,
} from "../lib/schemas/turn-editor";

function makeValues(overrides: Partial<TurnEditorFormValues> = {}): TurnEditorFormValues {
  return {
    text: "Hello caller",
    speaker: "harness",
    wait_for_response: true,
    dtmf: "",
    silence_s: "",
    audio_file: "",
    max_visits: "",
    timeout_s: "",
    listen_for_s: "",
    min_response_duration_s: "",
    retry_on_silence: "",
    pre_speak_pause_s: "",
    post_speak_pause_s: "",
    pre_listen_wait_s: "",
    ...overrides,
  };
}

test("turnToFormValues maps turn fields for edit form", () => {
  const turn: BuilderTurn = {
    id: "t1",
    kind: "bot_listen",
    content: {
      text: "Prompt text",
      dtmf: "9#",
      silence_s: 2.5,
      audio_file: "prompts/intro.wav",
    },
    max_visits: 3,
    config: {
      timeout_s: 21,
      min_response_duration_s: 0.75,
      retry_on_silence: 2,
      pre_speak_pause_s: 0.25,
      post_speak_pause_s: 0.5,
      pre_listen_wait_s: 1.2,
    },
  };

  assert.deepEqual(turnToFormValues(turn), {
    text: "Prompt text",
    speaker: "bot",
    wait_for_response: true,
    dtmf: "9#",
    silence_s: "2.5",
    audio_file: "prompts/intro.wav",
    max_visits: "3",
    timeout_s: "21",
    listen_for_s: "",
    min_response_duration_s: "0.75",
    retry_on_silence: "2",
    pre_speak_pause_s: "0.25",
    post_speak_pause_s: "0.5",
    pre_listen_wait_s: "1.2",
  });
});

test("mergeFormValuesIntoTurn preserves unmanaged keys and removes cleared fields", () => {
  const baseTurn: BuilderTurn = {
    id: "t1",
    kind: "harness_prompt",
    content: {
      text: "Existing",
      dtmf: "1",
      silence_s: 1.2,
      audio_file: "prompts/existing.wav",
    },
    listen: true,
    max_visits: 5,
    custom_key: "keep-me",
    config: {
      timeout_s: 15,
      min_response_duration_s: 0.8,
      retry_on_silence: 1,
      pre_speak_pause_s: 0.4,
      post_speak_pause_s: 0.2,
      pre_listen_wait_s: 0.1,
    },
  };

  const next = mergeFormValuesIntoTurn(
    baseTurn,
    "t1",
    makeValues({
      text: "  Updated text  ",
      speaker: "harness",
      wait_for_response: false,
      dtmf: "   ",
      silence_s: "",
      audio_file: "",
      max_visits: "",
      timeout_s: "",
      listen_for_s: "",
      min_response_duration_s: "",
      retry_on_silence: "",
      pre_speak_pause_s: "0.9",
      post_speak_pause_s: "",
      pre_listen_wait_s: "",
    })
  );

  assert.equal(next.kind, "harness_prompt");
  assert.equal(next.content?.text, "Updated text");
  assert.equal(next.listen, false);
  assert.equal(next.custom_key, "keep-me");
  assert.equal(next.content?.dtmf, undefined);
  assert.equal(next.content?.silence_s, undefined);
  assert.equal(next.content?.audio_file, undefined);
  assert.equal(next.max_visits, undefined);
  assert.deepEqual(next.config, { pre_speak_pause_s: 0.9 });
});

test("mergeFormValuesIntoTurn clamps numeric timing values", () => {
  const baseTurn: BuilderTurn = {
    id: "t1",
    kind: "harness_prompt",
    content: {},
    listen: true,
  };

  const next = mergeFormValuesIntoTurn(
    baseTurn,
    "t1",
    makeValues({
      silence_s: "-2.5",
      max_visits: "-4",
      timeout_s: "0.4",
      listen_for_s: "0.01",
      min_response_duration_s: "0.01",
      retry_on_silence: "-2",
      pre_speak_pause_s: "-1",
      post_speak_pause_s: "-0.5",
      pre_listen_wait_s: "-0.25",
    })
  );

  assert.equal(next.kind, "harness_prompt");
  assert.equal(next.content?.silence_s, 0);
  assert.equal(next.max_visits, 0);
  assert.deepEqual(next.config, {
    timeout_s: 1,
    listen_for_s: 0.1,
    min_response_duration_s: 0.1,
    retry_on_silence: 0,
    pre_speak_pause_s: 0,
    post_speak_pause_s: 0,
    pre_listen_wait_s: 0,
  });
});

test("turnEditorFormSchema rejects invalid numeric strings", () => {
  const parsed = turnEditorFormSchema.safeParse(
    makeValues({
      silence_s: "abc",
      max_visits: "1.5",
      timeout_s: "fast",
      listen_for_s: "0",
      min_response_duration_s: "0",
      retry_on_silence: "1.2",
    })
  );

  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("silence_s")));
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("max_visits")));
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("timeout_s")));
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("listen_for_s")));
  assert.ok(
    parsed.error.issues.some((issue) => issue.path.includes("min_response_duration_s"))
  );
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("retry_on_silence")));
});

test("turnEditorFormSchema rejects negative silence_s", () => {
  const parsed = turnEditorFormSchema.safeParse(
    makeValues({
      silence_s: "-2.5",
    })
  );

  assert.equal(parsed.success, false);
  if (parsed.success) {
    return;
  }
  assert.ok(parsed.error.issues.some((issue) => issue.path.includes("silence_s")));
});

test("turnToFormValues includes listen_for_s override", () => {
  const turn: BuilderTurn = {
    id: "t1",
    kind: "harness_prompt",
    content: { text: "Hello" },
    listen: true,
    config: { listen_for_s: 3.25 },
  };

  assert.equal(turnToFormValues(turn).listen_for_s, "3.25");
});

test("mergeFormValuesIntoTurn writes and clears listen_for_s", () => {
  const baseTurn: BuilderTurn = {
    id: "t1",
    kind: "harness_prompt",
    content: { text: "Hello" },
    listen: true,
    config: { timeout_s: 15 },
  };

  const withOverride = mergeFormValuesIntoTurn(
    baseTurn,
    "t1",
    makeValues({
      listen_for_s: "3.25",
    })
  );
  assert.equal(withOverride.config?.listen_for_s, 3.25);

  const cleared = mergeFormValuesIntoTurn(
    withOverride,
    "t1",
    makeValues({
      listen_for_s: "",
    })
  );
  assert.equal(cleared.config?.listen_for_s, undefined);
});
