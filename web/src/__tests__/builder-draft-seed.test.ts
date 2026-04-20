import test from "node:test";
import assert from "node:assert/strict";
import YAML from "yaml";
import { buildSeededBuilderDraftYaml } from "../lib/builder-draft-seed";

test("buildSeededBuilderDraftYaml builds a blank seeded draft from name only", () => {
  const yaml = buildSeededBuilderDraftYaml({
    name: "Billing Escalation Smoke",
    templateKey: "blank",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;

  assert.equal(parsed.name, "Billing Escalation Smoke");
  assert.equal(parsed.id, "billing-escalation-smoke");
  assert.equal(parsed.type, "reliability");
  assert.equal((parsed.bot as Record<string, unknown>).protocol, "sip");
  assert.deepEqual((parsed.turns as Array<Record<string, unknown>>)[0], {
    id: "t1",
    kind: "harness_prompt",
    content: { text: "Hello, this is the builder scaffold." },
    listen: true,
  });
  assert.equal((parsed.turns as Array<Record<string, unknown>>).length, 1);
});

test("buildSeededBuilderDraftYaml can seed a bot-opens blank draft", () => {
  const yaml = buildSeededBuilderDraftYaml({
    name: "Greeting Capture",
    templateKey: "blank",
    startMode: "bot_opens",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;
  const turns = parsed.turns as Array<Record<string, unknown>>;

  assert.equal(turns.length, 2);
  assert.deepEqual(turns[0], {
    id: "t0_pickup",
    kind: "bot_listen",
    config: {
      timeout_s: 15,
    },
  });
  assert.deepEqual(turns[1], {
    id: "t1_intro",
    kind: "harness_prompt",
    content: { text: "Hello, this is the builder scaffold." },
    listen: true,
  });
});

test("buildSeededBuilderDraftYaml applies optional type and protocol seeds", () => {
  const yaml = buildSeededBuilderDraftYaml({
    name: "HTTP Router",
    type: "golden_path",
    botProtocol: "mock",
    templateKey: "blank",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;
  const bot = parsed.bot as Record<string, unknown>;

  assert.equal(parsed.type, "golden_path");
  assert.equal(bot.protocol, "mock");
  assert.equal(bot.endpoint, "mock://local-agent");
});

test("buildSeededBuilderDraftYaml omitting startMode defaults to caller_opens", () => {
  const withDefault = buildSeededBuilderDraftYaml({ name: "X", templateKey: "blank" });
  const withExplicit = buildSeededBuilderDraftYaml({
    name: "X",
    templateKey: "blank",
    startMode: "caller_opens",
  });
  assert.equal(withDefault, withExplicit);
});

test("buildSeededBuilderDraftYaml non-blank template ignores bot_opens startMode", () => {
  const yaml = buildSeededBuilderDraftYaml({
    name: "Router",
    templateKey: "branching_router",
    startMode: "bot_opens",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;
  // description must not mention bot-speaks-first
  assert.ok(
    !(parsed.description as string).includes("Bot speaks first"),
    "non-blank template must not inherit bot_opens description",
  );
  // turns from the template, not the bot_opens scaffold
  const turns = parsed.turns as Array<Record<string, unknown>>;
  assert.equal(turns[0]?.id, "t1_intake");
});

test("buildSeededBuilderDraftYaml builds the adversarial template in adversarial mode", () => {
  const yaml = buildSeededBuilderDraftYaml({
    name: "Prompt Guard",
    templateKey: "adversarial_refusal",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;
  const scoring = parsed.scoring as Record<string, unknown>;

  assert.equal(parsed.type, "adversarial");
  assert.equal(Array.isArray(parsed.turns), true);
  assert.equal(Array.isArray(scoring.rubric), true);
  assert.equal(
    ((parsed.turns as Array<Record<string, unknown>>)[0] || {}).kind,
    "harness_prompt",
  );
});
