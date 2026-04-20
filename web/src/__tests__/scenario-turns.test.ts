import assert from "node:assert/strict";
import test from "node:test";

import {
  getScenarioTurnAudioFile,
  getScenarioTurnDtmf,
  getScenarioTurnKind,
  getScenarioTurnListen,
  getScenarioTurnSilenceS,
  getScenarioTurnSpeaker,
  getScenarioTurnText,
} from "../lib/scenario-turns";
import type { ScenarioTurn } from "../lib/api/types";

test("scenario-turn helpers read canonical harness_prompt content", () => {
  const turn: ScenarioTurn = {
    id: "t1",
    kind: "harness_prompt",
    content: {
      text: "Press 1 for billing",
      dtmf: "1",
      silence_s: 2,
      audio_file: "prompts/billing.wav",
    },
    listen: true,
  } as ScenarioTurn;

  assert.equal(getScenarioTurnKind(turn), "harness_prompt");
  assert.equal(getScenarioTurnSpeaker(turn), "harness");
  assert.equal(getScenarioTurnText(turn), "Press 1 for billing");
  assert.equal(getScenarioTurnDtmf(turn), "1");
  assert.equal(getScenarioTurnSilenceS(turn), 2);
  assert.equal(getScenarioTurnAudioFile(turn), "prompts/billing.wav");
  assert.equal(getScenarioTurnListen(turn), true);
});

test("scenario-turn helpers derive bot and hangup behavior from canonical kind", () => {
  const botTurn: ScenarioTurn = {
    id: "t2",
    kind: "bot_listen",
  } as ScenarioTurn;
  const hangupTurn: ScenarioTurn = {
    id: "t3",
    kind: "hangup",
  } as ScenarioTurn;

  assert.equal(getScenarioTurnSpeaker(botTurn), "bot");
  assert.equal(getScenarioTurnText(botTurn), "");
  assert.equal(getScenarioTurnListen(botTurn), true);

  assert.equal(getScenarioTurnSpeaker(hangupTurn), "harness");
  assert.equal(getScenarioTurnText(hangupTurn), "");
  assert.equal(getScenarioTurnListen(hangupTurn), false);
});

test("scenario-turn helpers treat wait and time_route as non-listening harness blocks", () => {
  const waitTurn: ScenarioTurn = {
    id: "t_wait",
    kind: "wait",
    wait_s: 2,
  } as ScenarioTurn;
  const timeRouteTurn: ScenarioTurn = {
    id: "t_route",
    kind: "time_route",
    timezone: "UTC",
    windows: [],
    default: "t_end",
  } as unknown as ScenarioTurn;

  assert.equal(getScenarioTurnSpeaker(waitTurn), "harness");
  assert.equal(getScenarioTurnListen(waitTurn), false);
  assert.equal(getScenarioTurnText(waitTurn), "");

  assert.equal(getScenarioTurnSpeaker(timeRouteTurn), "harness");
  assert.equal(getScenarioTurnListen(timeRouteTurn), false);
  assert.equal(getScenarioTurnText(timeRouteTurn), "");
});
