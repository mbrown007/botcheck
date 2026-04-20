import assert from "node:assert/strict";
import test from "node:test";
import {
  aiScenarioEditorFormSchema,
  aiScenarioFormValuesToPayload,
  aiScenarioToFormValues,
  aiScenarioRecordEditorFormSchema,
  aiScenarioRecordFormValuesToPayload,
  createEmptyAIScenarioEditorValues,
  createEmptyAIScenarioRecordEditorValues,
} from "@/lib/schemas/ai-scenario-editor";

test("createEmptyAIScenarioEditorValues returns intent-first defaults", () => {
  assert.deepEqual(createEmptyAIScenarioEditorValues(), {
    name: "",
    publicId: "",
    namespace: "",
    personaId: "",
    scenarioBrief: "",
    scenarioFactsText: "",
    evaluationObjective: "",
    openingStrategy: "wait_for_bot_greeting",
    datasetSource: "",
    scoringProfile: "",
    tts_voice: "",
    stt_provider: "",
    stt_model: "",
    language: "",
    stt_endpointing_ms: "",
    transcript_merge_window_s: "",
    turn_timeout_s: "",
    max_duration_s: "",
    max_total_turns: "",
  });
});

test("aiScenarioEditorFormSchema rejects invalid structured facts json", () => {
  const result = aiScenarioEditorFormSchema.safeParse({
    ...createEmptyAIScenarioEditorValues(),
    name: "Delayed flight",
    personaId: "persona_parent",
    scenarioBrief: "Flight is delayed.",
    evaluationObjective: "Confirm the delay and options.",
    scenarioFactsText: "[]",
  });

  assert.equal(result.success, false);
});

test("aiScenarioFormValuesToPayload trims values and parses facts", () => {
  const payload = aiScenarioFormValuesToPayload({
    name: "  Delayed Flight  ",
    publicId: " delayed-flight ",
    namespace: " /support/flights/ ",
    personaId: " persona_parent ",
    scenarioBrief: "  Parent needs clarity. ",
    scenarioFactsText: '{"booking_ref":"ABC123"}',
    evaluationObjective: "  Confirm timing and support. ",
    openingStrategy: "caller_opens",
    datasetSource: "  airline-delay-dataset ",
    scoringProfile: "  delay-handling ",
    tts_voice: " openai:alloy ",
    stt_provider: " Deepgram ",
    stt_model: " nova-2-phonecall ",
    language: "  en-GB ",
    stt_endpointing_ms: " 600 ",
    transcript_merge_window_s: " 2.5 ",
    turn_timeout_s: " 30 ",
    max_duration_s: " 450 ",
    max_total_turns: " 9 ",
  });

  assert.deepEqual(payload, {
    ai_scenario_id: "delayed-flight",
    namespace: "support/flights",
    persona_id: "persona_parent",
    name: "Delayed Flight",
    scenario_brief: "Parent needs clarity.",
    scenario_facts: { booking_ref: "ABC123" },
    evaluation_objective: "Confirm timing and support.",
    opening_strategy: "caller_opens",
    is_active: true,
    dataset_source: "airline-delay-dataset",
    scoring_profile: "delay-handling",
    config: {
      tts_voice: "openai:alloy",
      stt_provider: "deepgram",
      stt_model: "nova-2-phonecall",
      language: "en-GB",
      stt_endpointing_ms: 600,
      transcript_merge_window_s: 2.5,
      turn_timeout_s: 30,
      max_duration_s: 450,
      max_total_turns: 9,
    },
  });
});

test("aiScenarioFormValuesToPayload omits runtime config when advanced fields are blank", () => {
  const payload = aiScenarioFormValuesToPayload({
    ...createEmptyAIScenarioEditorValues(),
    name: "Delayed Flight",
    personaId: "persona_parent",
    scenarioBrief: "Parent needs clarity.",
    evaluationObjective: "Confirm timing and support.",
  });

  assert.deepEqual(payload.config, {});
});

test("aiScenarioFormValuesToPayload omits blank namespace", () => {
  const payload = aiScenarioFormValuesToPayload({
    ...createEmptyAIScenarioEditorValues(),
    name: "Delayed Flight",
    namespace: "   /   ",
    personaId: "persona_parent",
    scenarioBrief: "Parent needs clarity.",
    evaluationObjective: "Confirm timing and support.",
  });

  assert.equal(payload.namespace, undefined);
});

test("aiScenarioToFormValues reads allowed runtime config fields and ignores unsupported keys", () => {
  const values = aiScenarioToFormValues({
    ai_scenario_id: "ai_delay",
    name: "Delayed Flight",
    namespace: "support/refunds",
    persona_id: "persona_parent",
    scenario_brief: "Parent needs clarity.",
    scenario_facts: { booking_ref: "ABC123" },
    evaluation_objective: "Confirm timing and support.",
    opening_strategy: "caller_opens",
    dataset_source: "manual",
    scoring_profile: "delay-handling",
    config: {
      stt_provider: "deepgram",
      stt_model: "nova-2-phonecall",
      language: "en-US",
      stt_endpointing_ms: 1800,
      transcript_merge_window_s: 1.8,
      turn_timeout_s: 20,
      max_duration_s: 305.5,
      max_total_turns: 24,
      tts_voice: "openai:nova",
    },
  });

  assert.equal(values.tts_voice, "openai:nova");
  assert.equal(values.namespace, "support/refunds");
  assert.equal(values.stt_provider, "deepgram");
  assert.equal(values.stt_model, "nova-2-phonecall");
  assert.equal(values.language, "en-US");
  assert.equal(values.stt_endpointing_ms, "1800");
  assert.equal(values.transcript_merge_window_s, "1.8");
  assert.equal(values.turn_timeout_s, "20");
  assert.equal(values.max_duration_s, "305.5");
  assert.equal(values.max_total_turns, "24");
});

test("AI scenario form values preserve legacy hidden-provider tts_voice for round-trip", () => {
  const formValues = aiScenarioToFormValues({
    ai_scenario_id: "ai_legacy_voice",
    name: "Legacy Voice Scenario",
    persona_id: "persona_parent",
    scenario_brief: "Parent needs clarity.",
    scenario_facts: {},
    evaluation_objective: "Confirm timing and support.",
    opening_strategy: "caller_opens",
    dataset_source: "manual",
    scoring_profile: "delay-handling",
    config: {
      tts_voice: "elevenlabs:voice-123",
    },
  });

  assert.equal(formValues.tts_voice, "elevenlabs:voice-123");

  const payload = aiScenarioFormValuesToPayload({
    ...createEmptyAIScenarioEditorValues(),
    ...formValues,
  });

  assert.deepEqual(payload.config, {
    tts_voice: "elevenlabs:voice-123",
  });
});

test("AI scenario form values preserve hidden-provider STT overrides for round-trip", () => {
  const formValues = aiScenarioToFormValues({
    ai_scenario_id: "ai_legacy_stt",
    name: "Legacy STT Scenario",
    persona_id: "persona_parent",
    scenario_brief: "Parent needs clarity.",
    scenario_facts: {},
    evaluation_objective: "Confirm timing and support.",
    opening_strategy: "caller_opens",
    dataset_source: "manual",
    scoring_profile: "delay-handling",
    config: {
      stt_provider: "whisper",
      stt_model: "whisper-1",
    },
  });

  assert.equal(formValues.stt_provider, "whisper");
  assert.equal(formValues.stt_model, "whisper-1");

  const payload = aiScenarioFormValuesToPayload({
    ...createEmptyAIScenarioEditorValues(),
    ...formValues,
  });

  assert.deepEqual(payload.config, {
    stt_provider: "whisper",
    stt_model: "whisper-1",
  });
});

test("aiScenarioFormValuesToPayload preserves azure STT overrides explicitly", () => {
  const payload = aiScenarioFormValuesToPayload({
    ...createEmptyAIScenarioEditorValues(),
    name: "Azure STT Scenario",
    personaId: "persona_parent",
    scenarioBrief: "Parent needs clarity.",
    evaluationObjective: "Confirm timing and support.",
    stt_provider: " Azure ",
    stt_model: " azure-default ",
  });

  assert.deepEqual(payload.config, {
    stt_provider: "azure",
    stt_model: "azure-default",
  });
});

test("createEmptyAIScenarioRecordEditorValues returns blank defaults", () => {
  assert.deepEqual(createEmptyAIScenarioRecordEditorValues(), {
    orderIndex: "",
    inputText: "",
    expectedOutput: "",
  });
});

test("aiScenarioRecordEditorFormSchema rejects non-integer order indexes", () => {
  const result = aiScenarioRecordEditorFormSchema.safeParse({
    orderIndex: "1.5",
    inputText: "Caller says hello",
    expectedOutput: "Bot responds politely",
  });

  assert.equal(result.success, false);
});

test("aiScenarioRecordFormValuesToPayload normalizes optional order index", () => {
  const payload = aiScenarioRecordFormValuesToPayload({
    orderIndex: " 2 ",
    inputText: "  Caller asks for refund. ",
    expectedOutput: "  Bot explains refund policy. ",
  });

  assert.deepEqual(payload, {
    order_index: 2,
    input_text: "Caller asks for refund.",
    expected_output: "Bot explains refund policy.",
    metadata: {},
    is_active: true,
  });
});
