import assert from "node:assert/strict";
import test from "node:test";

import {
  buildHttpTransportOptionLabel,
  buildPlaygroundAIScenarioOptionLabel,
  buildPlaygroundGraphOptionLabel,
  isPlaygroundCompatibleGraphScenario,
  isPlaygroundRunActive,
  PLAYGROUND_SYSTEM_PROMPT_SOFT_LIMIT,
  playgroundPromptSoftLimitWarning,
} from "@/lib/playground";

test("playground compatibility accepts mock and http graph scenarios", () => {
  assert.equal(
    isPlaygroundCompatibleGraphScenario({
      scenario_kind: "graph",
      bot: { protocol: "mock" },
    } as never),
    true
  );
  assert.equal(
    isPlaygroundCompatibleGraphScenario({
      scenario_kind: "graph",
      bot: { protocol: "http" },
    } as never),
    true
  );
});

test("playground compatibility rejects ai and sip scenarios", () => {
  assert.equal(
    isPlaygroundCompatibleGraphScenario({
      scenario_kind: "ai",
      bot: { protocol: "mock" },
    } as never),
    false
  );
  assert.equal(
    isPlaygroundCompatibleGraphScenario({
      scenario_kind: "graph",
      bot: { protocol: "sip" },
    } as never),
    false
  );
});

test("prompt soft limit warning appears only after the configured threshold", () => {
  assert.equal(playgroundPromptSoftLimitWarning("x".repeat(32)), null);
  assert.match(
    playgroundPromptSoftLimitWarning("x".repeat(PLAYGROUND_SYSTEM_PROMPT_SOFT_LIMIT + 1)) ?? "",
    /soft limit/i
  );
});

test("playground labels remain operator-readable", () => {
  assert.equal(
    buildPlaygroundGraphOptionLabel({
      name: "Billing Smoke",
      bot: { protocol: "http" },
    } as never),
    "Billing Smoke · HTTP"
  );
  assert.equal(
    buildPlaygroundAIScenarioOptionLabel({
      name: "Escalation Probe",
    } as never),
    "Escalation Probe · AI"
  );
  assert.equal(
    buildHttpTransportOptionLabel({
      name: "HTTP Profile",
      default_dial_target: "https://bot.internal/chat",
      endpoint: null,
    } as never),
    "HTTP Profile · https://bot.internal/chat"
  );
});

test("run active helper follows pending running and judging states", () => {
  assert.equal(isPlaygroundRunActive({ state: "pending" } as never), true);
  assert.equal(isPlaygroundRunActive({ state: "running" } as never), true);
  assert.equal(isPlaygroundRunActive({ state: "judging" } as never), true);
  assert.equal(isPlaygroundRunActive({ state: "complete" } as never), false);
  assert.equal(isPlaygroundRunActive(null), false);
});
