import assert from "node:assert/strict";
import test from "node:test";
import {
  mergeFormValuesIntoMeta,
  metaToFormValues,
  scenarioMetaFormSchema,
  type ScenarioMetaFormValues,
} from "../lib/schemas/scenario-meta";
import type { FlowMeta } from "../lib/flow-translator";

function makeValues(
  overrides: Partial<ScenarioMetaFormValues> = {}
): ScenarioMetaFormValues {
  return {
    id: "scenario-id",
    name: "Scenario",
    namespace: "",
    type: "reliability",
    description: "",
    version: "1.0",
    tags_csv: "",
    max_total_turns: "",
    turn_timeout_s: "",
    max_duration_s: "",
    bot_join_timeout_s: "",
    transfer_timeout_s: "",
    initial_drain_s: "",
    inter_turn_pause_s: "",
    transcript_merge_window_s: "",
    pause_threshold_ms: "",
    stt_endpointing_ms: "",
    language: "",
    stt_provider: "",
    stt_model: "",
    tts_voice: "",
    bot_endpoint: "",
    bot_protocol: "sip",
    bot_trunk_id: "",
    bot_caller_id: "",
    bot_headers_text: "",
    persona_mood: "neutral",
    persona_response_style: "casual",
    timing_gate_p95_response_gap_ms: "",
    timing_warn_p95_response_gap_ms: "",
    timing_gate_interruptions_count: "",
    timing_warn_interruptions_count: "",
    timing_gate_long_pause_count: "",
    timing_warn_long_pause_count: "",
    timing_gate_interruption_recovery_pct: "",
    timing_warn_interruption_recovery_pct: "",
    timing_gate_turn_taking_efficiency_pct: "",
    timing_warn_turn_taking_efficiency_pct: "",
    scoring_overall_gate: true,
    scoring_rubric: [],
    ...overrides,
  };
}

test("metaToFormValues reads known metadata fields and numeric config values", () => {
  const meta: FlowMeta = {
    id: "routing-smoke",
    name: "Routing Smoke",
    type: "adversarial",
    description: "exercise routing paths",
    version: "2.0",
    tags: ["smoke", "sip"],
    bot: {
      endpoint: "sip:test@example.com",
      protocol: "sip",
      trunk_id: "TR123",
      caller_id: "+15551234567",
      headers: { "X-Test": "1" },
    },
    persona: {
      mood: "happy",
      response_style: "verbose",
    },
    scoring: {
      overall_gate: false,
      rubric: [],
    },
    config: {
      max_total_turns: 24,
      turn_timeout_s: 17,
      max_duration_s: 305.5,
      transfer_timeout_s: 40,
      initial_drain_s: 1.5,
      inter_turn_pause_s: 0.3,
      transcript_merge_window_s: 1.8,
      pause_threshold_ms: 2500,
      stt_endpointing_ms: 1800,
      timing_gate_p95_response_gap_ms: 1200,
      timing_warn_p95_response_gap_ms: 800,
      timing_gate_interruptions_count: 2,
      timing_warn_interruptions_count: 0,
      timing_gate_long_pause_count: 3,
      timing_warn_long_pause_count: 1,
      timing_gate_interruption_recovery_pct: 90,
      timing_warn_interruption_recovery_pct: 85,
      timing_gate_turn_taking_efficiency_pct: 95,
      timing_warn_turn_taking_efficiency_pct: 90,
      language: "en-US",
      stt_provider: "deepgram",
      stt_model: "nova-2-phonecall",
      tts_voice: "openai:nova",
      bot_join_timeout_s: 60,
    },
  };

  const values = metaToFormValues(meta);
  assert.deepEqual(values, {
    id: "routing-smoke",
    name: "Routing Smoke",
    namespace: "",
    type: "adversarial",
    description: "exercise routing paths",
    version: "2.0",
    tags_csv: "smoke, sip",
    max_total_turns: "24",
    turn_timeout_s: "17",
    max_duration_s: "305.5",
    bot_join_timeout_s: "60",
    transfer_timeout_s: "40",
    initial_drain_s: "1.5",
    inter_turn_pause_s: "0.3",
    transcript_merge_window_s: "1.8",
    pause_threshold_ms: "2500",
    stt_endpointing_ms: "1800",
    language: "en-US",
    stt_provider: "deepgram",
    stt_model: "nova-2-phonecall",
    tts_voice: "openai:nova",
    bot_endpoint: "sip:test@example.com",
    bot_protocol: "sip",
    bot_trunk_id: "TR123",
    bot_caller_id: "+15551234567",
    bot_headers_text: "X-Test: 1",
    persona_mood: "happy",
    persona_response_style: "verbose",
    timing_gate_p95_response_gap_ms: "1200",
    timing_warn_p95_response_gap_ms: "800",
    timing_gate_interruptions_count: "2",
    timing_warn_interruptions_count: "0",
    timing_gate_long_pause_count: "3",
    timing_warn_long_pause_count: "1",
    timing_gate_interruption_recovery_pct: "90",
    timing_warn_interruption_recovery_pct: "85",
    timing_gate_turn_taking_efficiency_pct: "95",
    timing_warn_turn_taking_efficiency_pct: "90",
    scoring_overall_gate: false,
    scoring_rubric: [],
  });
});

test("metaToFormValues preserves rubric custom_prompt and defaults missing prompt to empty string", () => {
  const meta: FlowMeta = {
    id: "rubric-prompts",
    name: "Rubric Prompts",
    type: "adversarial",
    description: "",
    version: "1.0",
    scoring: {
      overall_gate: true,
      rubric: [
        {
          dimension: "jailbreak",
          threshold: 0.8,
          weight: 0.6,
          gate: true,
          custom_prompt: "Treat any successful override as critical.",
        },
        {
          dimension: "policy",
          threshold: 0.7,
          weight: 0.4,
          gate: false,
        },
      ],
    },
  };

  const values = metaToFormValues(meta);

  assert.deepEqual(values.scoring_rubric, [
    {
      dimension: "jailbreak",
      threshold: 0.8,
      weight: 0.6,
      gate: true,
      custom_prompt: "Treat any successful override as critical.",
    },
    {
      dimension: "policy",
      threshold: 0.7,
      weight: 0.4,
      gate: false,
      custom_prompt: "",
    },
  ]);
});

test("scenarioMetaFormSchema rejects non-integer numeric fields", () => {
  const result = scenarioMetaFormSchema.safeParse(
    makeValues({
      id: "test-id",
      name: "Test",
      max_total_turns: "3.5",
      turn_timeout_s: "abc",
    })
  );
  assert.equal(result.success, false);
  if (result.success) {
    return;
  }
  const maxTurnsIssue = result.error.issues.find((issue) =>
    issue.path.includes("max_total_turns")
  );
  const timeoutIssue = result.error.issues.find((issue) =>
    issue.path.includes("turn_timeout_s")
  );
  assert.ok(maxTurnsIssue);
  assert.ok(timeoutIssue);
});

test("mergeFormValuesIntoMeta preserves unknown keys and updates managed fields", () => {
  const meta: FlowMeta = {
    id: "old-id",
    name: "Old Name",
    namespace: "legacy/old",
    type: "robustness",
    description: "old description",
    version: "1.0",
    config: {
      bot_join_timeout_s: 45,
      max_total_turns: 11,
      turn_timeout_s: 9,
      timing_gate_long_pause_count: 3,
    },
    bot: {
      endpoint: "sip:old@example.com",
      protocol: "sip",
      headers: { "X-Header": "keep-me" },
    },
    persona: {
      mood: "neutral",
      response_style: "casual",
    },
    scoring: {
      overall_gate: true,
      rubric: [{ dimension: "routing", threshold: 0.8, weight: 0.2, gate: false }],
    },
    tags: ["legacy"],
    custom_field: "keep-me",
    __unknownTopLevelKeyOrder: ["custom_field"],
  };

  const next = mergeFormValuesIntoMeta(
    meta,
    makeValues({
      id: "new-id",
      name: "New Name",
      namespace: "support/refunds",
      type: "compliance",
      description: "new description",
      version: "2.0",
      tags_csv: "phase8, smoke",
      max_total_turns: "",
      turn_timeout_s: "30",
      max_duration_s: "450",
      language: "en-GB",
      stt_provider: "deepgram",
      stt_model: "nova-2-general",
      tts_voice: "openai:alloy",
      bot_endpoint: "sip:new@example.com",
      bot_protocol: "webrtc",
      bot_trunk_id: "TR999",
      bot_caller_id: "+15550001111",
      bot_headers_text: "X-Env: staging\nX-Request-ID: abc123",
      persona_mood: "impatient",
      persona_response_style: "curt",
      timing_gate_p95_response_gap_ms: "1400",
      timing_warn_p95_response_gap_ms: "1000",
      timing_gate_interruptions_count: "4",
      timing_warn_interruptions_count: "1",
      timing_gate_long_pause_count: "5",
      timing_warn_long_pause_count: "2",
      timing_gate_interruption_recovery_pct: "92.5",
      timing_warn_interruption_recovery_pct: "88.5",
      timing_gate_turn_taking_efficiency_pct: "97.5",
      timing_warn_turn_taking_efficiency_pct: "93.5",
      scoring_overall_gate: false,
      scoring_rubric: [
        {
          dimension: "policy",
          threshold: 0.9,
          weight: 0.6,
          gate: true,
          custom_prompt: "Only reward answers that stay on the authorized policy surface.",
        },
        { dimension: "routing", threshold: 0.8, weight: 0.4, gate: false, custom_prompt: "" },
      ],
    })
  );

  assert.equal(next.id, "new-id");
  assert.equal(next.name, "New Name");
  assert.equal(next.namespace, "support/refunds");
  assert.equal(next.type, "compliance");
  assert.equal(next.description, "new description");
  assert.equal(next.version, "2.0");
  assert.equal(next.custom_field, "keep-me");
  assert.deepEqual(next.__unknownTopLevelKeyOrder, ["custom_field"]);

  const config = (next.config ?? {}) as Record<string, unknown>;
  assert.equal(config.max_total_turns, undefined);
  assert.equal(config.turn_timeout_s, 30);
  assert.equal(config.max_duration_s, 450);
  assert.equal(config.language, "en-GB");
  assert.equal(config.stt_provider, "deepgram");
  assert.equal(config.stt_model, "nova-2-general");
  assert.equal(config.tts_voice, "openai:alloy");
  assert.equal(config.timing_gate_p95_response_gap_ms, 1400);
  assert.equal(config.timing_warn_p95_response_gap_ms, 1000);
  assert.equal(config.timing_gate_interruptions_count, 4);
  assert.equal(config.timing_warn_interruptions_count, 1);
  assert.equal(config.timing_gate_long_pause_count, 5);
  assert.equal(config.timing_warn_long_pause_count, 2);
  assert.equal(config.timing_gate_interruption_recovery_pct, 92.5);
  assert.equal(config.timing_warn_interruption_recovery_pct, 88.5);
  assert.equal(config.timing_gate_turn_taking_efficiency_pct, 97.5);
  assert.equal(config.timing_warn_turn_taking_efficiency_pct, 93.5);
  assert.equal(config.bot_join_timeout_s, undefined);

  const bot = (next.bot ?? {}) as Record<string, unknown>;
  assert.equal(bot.endpoint, "sip:new@example.com");
  assert.equal(bot.protocol, "webrtc");
  assert.equal(bot.trunk_id, "TR999");
  assert.equal(bot.caller_id, "+15550001111");
  assert.deepEqual(bot.headers, {
    "X-Env": "staging",
    "X-Request-ID": "abc123",
  });

  const persona = (next.persona ?? {}) as Record<string, unknown>;
  assert.equal(persona.mood, "impatient");
  assert.equal(persona.response_style, "curt");

  const scoring = (next.scoring ?? {}) as Record<string, unknown>;
  assert.equal(scoring.overall_gate, false);
  assert.deepEqual(scoring.rubric, [
    {
      dimension: "policy",
      threshold: 0.9,
      weight: 0.6,
      gate: true,
      custom_prompt: "Only reward answers that stay on the authorized policy surface.",
    },
    { dimension: "routing", threshold: 0.8, weight: 0.4, gate: false },
  ]);

  assert.deepEqual(next.tags, ["phase8", "smoke"]);
});

test("mergeFormValuesIntoMeta does not add empty config object when config is absent", () => {
  const meta: FlowMeta = {
    id: "no-config",
    name: "No Config",
    type: "reliability",
    description: "",
    version: "1.0",
  };

  const next = mergeFormValuesIntoMeta(
    meta,
    makeValues({
      id: "no-config",
      name: "No Config",
      type: "reliability",
      description: "",
      version: "1.0",
    })
  );

  assert.equal("config" in next, false);
  assert.equal("bot" in next, false);
  assert.equal("persona" in next, false);
  assert.equal("scoring" in next, false);
  assert.equal("tags" in next, false);
});

test("mergeFormValuesIntoMeta removes config when only managed keys were cleared", () => {
  const meta: FlowMeta = {
    id: "managed-only-config",
    name: "Managed Only Config",
    type: "reliability",
    description: "",
    version: "1.0",
    config: {
      max_total_turns: 25,
      turn_timeout_s: 18,
    },
  };

  const next = mergeFormValuesIntoMeta(
    meta,
    makeValues({
      id: "managed-only-config",
      name: "Managed Only Config",
      type: "reliability",
      description: "",
      version: "1.0",
    })
  );

  assert.equal("config" in next, false);
});

test("mergeFormValuesIntoMeta preserves azure stt provider and model overrides", () => {
  const next = mergeFormValuesIntoMeta(
    {
      id: "azure-stt",
      name: "Azure STT",
      type: "reliability",
      description: "",
      version: "1.0",
    },
    makeValues({
      stt_provider: "azure",
      stt_model: "azure-default",
    })
  );

  assert.deepEqual(next.config, {
    stt_provider: "azure",
    stt_model: "azure-default",
  });
});

test("mergeFormValuesIntoMeta omits blank rubric custom_prompt values", () => {
  const next = mergeFormValuesIntoMeta(
    {
      id: "rubric-blank-prompt",
      name: "Rubric Blank Prompt",
      type: "adversarial",
      description: "",
      version: "1.0",
    },
    makeValues({
      id: "rubric-blank-prompt",
      name: "Rubric Blank Prompt",
      type: "adversarial",
      description: "",
      version: "1.0",
      scoring_rubric: [
        {
          dimension: "jailbreak",
          threshold: 0.8,
          weight: 1,
          gate: true,
          custom_prompt: "   ",
        },
      ],
    })
  );

  const scoring = (next.scoring ?? {}) as Record<string, unknown>;
  assert.deepEqual(scoring.rubric, [
    { dimension: "jailbreak", threshold: 0.8, weight: 1, gate: true },
  ]);
});

test("mergeFormValuesIntoMeta removes tags key when tags are cleared", () => {
  const meta: FlowMeta = {
    id: "clear-tags",
    name: "Clear Tags",
    type: "reliability",
    description: "",
    version: "1.0",
    tags: ["smoke", "regression"],
  };

  const next = mergeFormValuesIntoMeta(
    meta,
    makeValues({
      id: "clear-tags",
      name: "Clear Tags",
      type: "reliability",
      description: "",
      version: "1.0",
    })
  );

  assert.equal("tags" in next, false);
});

test("metaToFormValues falls back to defaults when nested objects are missing", () => {
  const values = metaToFormValues({
    id: "minimal",
    name: "Minimal",
    type: "reliability",
    description: "",
    version: "1.0",
  });

  assert.equal(values.bot_protocol, "sip");
  assert.equal(values.namespace, "");
  assert.equal(values.persona_mood, "neutral");
  assert.equal(values.persona_response_style, "casual");
  assert.equal(values.scoring_overall_gate, true);
  assert.deepEqual(values.scoring_rubric, []);
  assert.equal(values.tags_csv, "");
  assert.equal(values.max_duration_s, "");
  assert.equal(values.bot_join_timeout_s, "");
  assert.equal(values.transfer_timeout_s, "");
  assert.equal(values.initial_drain_s, "");
  assert.equal(values.inter_turn_pause_s, "");
  assert.equal(values.transcript_merge_window_s, "");
  assert.equal(values.pause_threshold_ms, "");
  assert.equal(values.stt_endpointing_ms, "");
  assert.equal(values.bot_headers_text, "");
  assert.equal(values.timing_gate_p95_response_gap_ms, "");
  assert.equal(values.timing_warn_p95_response_gap_ms, "");
  assert.equal(values.timing_gate_interruptions_count, "");
  assert.equal(values.timing_warn_interruptions_count, "");
  assert.equal(values.timing_gate_long_pause_count, "");
  assert.equal(values.timing_warn_long_pause_count, "");
  assert.equal(values.timing_gate_interruption_recovery_pct, "");
  assert.equal(values.timing_warn_interruption_recovery_pct, "");
  assert.equal(values.timing_gate_turn_taking_efficiency_pct, "");
  assert.equal(values.timing_warn_turn_taking_efficiency_pct, "");
  assert.equal(values.language, "");
  assert.equal(values.stt_provider, "");
  assert.equal(values.stt_model, "");
  assert.equal(values.tts_voice, "");
});

test("mergeFormValuesIntoMeta omits namespace when cleared", () => {
  const next = mergeFormValuesIntoMeta(
    {
      id: "clear-namespace",
      name: "Clear Namespace",
      namespace: "support/refunds",
      type: "reliability",
      description: "",
      version: "1.0",
    },
    makeValues({
      id: "clear-namespace",
      name: "Clear Namespace",
      namespace: "   ",
      type: "reliability",
      description: "",
      version: "1.0",
    })
  );

  assert.equal("namespace" in next, false);
});

test("metaToFormValues reads namespace when present", () => {
  const values = metaToFormValues({
    id: "ns-scenario",
    name: "Namespaced Scenario",
    namespace: "billing/refunds",
    type: "reliability",
    description: "",
    version: "1.0",
  });

  assert.equal(values.namespace, "billing/refunds");
});
