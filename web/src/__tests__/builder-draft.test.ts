import test from "node:test";
import assert from "node:assert/strict";
import YAML from "yaml";
import { createCopiedScenarioYaml, nextCopyScenarioId } from "../lib/builder-draft";

test("nextCopyScenarioId picks -copy when available", () => {
  const next = nextCopyScenarioId("billing-smoke", []);
  assert.equal(next, "billing-smoke-copy");
});

test("nextCopyScenarioId increments suffix when -copy already exists", () => {
  const next = nextCopyScenarioId("billing-smoke", [
    "billing-smoke-copy",
    "billing-smoke-copy-2",
  ]);
  assert.equal(next, "billing-smoke-copy-3");
});

test("createCopiedScenarioYaml updates id and name", () => {
  const source = `version: "1.0"
id: routing-transfer
name: Routing Transfer
type: reliability
description: smoke
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 8
scoring:
  overall_gate: false
  rubric: []
tags: []
turns:
  - id: t1
    speaker: harness
    text: hello
`;

  const copied = createCopiedScenarioYaml(source, ["routing-transfer-copy"]);
  assert.equal(copied.copiedId, "routing-transfer-copy-2");
  assert.ok(copied.yaml.includes("id: routing-transfer-copy-2"));
  assert.ok(copied.yaml.includes("name: Routing Transfer (copy)"));
});

test("createCopiedScenarioYaml falls back name to copied id when source has no name", () => {
  const source = `version: "1.0"
id: copy-fallback
type: reliability
description: smoke
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 8
scoring:
  overall_gate: false
  rubric: []
tags: []
turns:
  - id: t1
    speaker: harness
    text: hello
`;

  const copied = createCopiedScenarioYaml(source, []);
  const parsed = YAML.parse(copied.yaml) as Record<string, unknown>;
  assert.equal(parsed.id, "copy-fallback-copy");
  assert.equal(parsed.name, "copy-fallback-copy");
});
