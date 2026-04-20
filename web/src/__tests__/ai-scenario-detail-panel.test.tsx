import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AIScenarioDetailPanel } from "@/app/(dashboard)/ai-scenarios/_components/AIScenarioDetailPanel";

test("AI scenario detail panel surfaces stored TTS voice overrides", () => {
  const markup = renderToStaticMarkup(
    <AIScenarioDetailPanel
      scenario={{
        ai_scenario_id: "ai_delay",
        scenario_id: "ai-backing-delay",
        name: "Delayed flight",
        namespace: "support/flights",
        persona_id: "persona_parent",
        scenario_brief: "Parent needs clarity.",
        scenario_facts: { booking_ref: "ABC123" },
        evaluation_objective: "Confirm timing and support.",
        opening_strategy: "caller_opens",
        is_active: true,
        scoring_profile: "delay-handling",
        dataset_source: "manual",
        record_count: 2,
        created_at: "2026-03-01T00:00:00Z",
        updated_at: "2026-03-01T00:00:00Z",
        config: {
          tts_voice: "openai:alloy",
          stt_provider: "deepgram",
          stt_model: "nova-2-phonecall",
        },
      }}
      speechCapabilities={{
        tts: [
          {
            id: "openai",
            label: "OpenAI",
            enabled: true,
            voice_mode: "static_select",
            supports_preview: true,
            supports_cache_warm: true,
            supports_live_synthesis: true,
            supports_live_stream: true,
          },
        ],
        stt: [
          {
            id: "deepgram",
            label: "Deepgram",
            enabled: true,
            voice_mode: "freeform_id",
            supports_preview: false,
            supports_cache_warm: false,
            supports_live_synthesis: false,
            supports_live_stream: true,
          },
        ],
      }}
      personaName="Concerned Parent"
      onClose={() => {}}
    />
  );

  assert.match(markup, />TTS Voice</);
  assert.match(markup, />OpenAI</);
  assert.match(markup, />Alloy</);
  assert.match(markup, />support\/flights</);
  assert.match(markup, />STT Provider</);
  assert.match(markup, />Deepgram</);
  assert.match(markup, />nova-2-phonecall</);
});

test("AI scenario detail panel marks unavailable stored TTS providers", () => {
  const markup = renderToStaticMarkup(
    <AIScenarioDetailPanel
      scenario={{
        ai_scenario_id: "ai_delay",
        scenario_id: "ai-backing-delay",
        name: "Delayed flight",
        persona_id: "persona_parent",
        scenario_brief: "Parent needs clarity.",
        scenario_facts: {},
        evaluation_objective: "Confirm timing and support.",
        opening_strategy: "caller_opens",
        is_active: true,
        scoring_profile: "delay-handling",
        dataset_source: "manual",
        record_count: 2,
        created_at: "2026-03-01T00:00:00Z",
        updated_at: "2026-03-01T00:00:00Z",
        config: {
          tts_voice: "elevenlabs:voice-123",
        },
      }}
      speechCapabilities={{
        tts: [
          {
            id: "openai",
            label: "OpenAI",
            enabled: true,
            voice_mode: "static_select",
            supports_preview: true,
            supports_cache_warm: true,
            supports_live_synthesis: true,
            supports_live_stream: true,
          },
          {
            id: "elevenlabs",
            label: "ElevenLabs",
            enabled: false,
            voice_mode: "freeform_id",
            supports_preview: true,
            supports_cache_warm: true,
            supports_live_synthesis: true,
            supports_live_stream: false,
          },
        ],
        stt: [],
      }}
      personaName="Concerned Parent"
      onClose={() => {}}
    />
  );

  assert.match(markup, />ElevenLabs \(unavailable\)</);
  assert.match(markup, /elevenlabs:voice-123/);
});

test("AI scenario detail panel marks unavailable stored STT providers", () => {
  const markup = renderToStaticMarkup(
    <AIScenarioDetailPanel
      scenario={{
        ai_scenario_id: "ai_delay",
        scenario_id: "ai-backing-delay",
        name: "Delayed flight",
        persona_id: "persona_parent",
        scenario_brief: "Parent needs clarity.",
        scenario_facts: {},
        evaluation_objective: "Confirm timing and support.",
        opening_strategy: "caller_opens",
        is_active: true,
        scoring_profile: "delay-handling",
        dataset_source: "manual",
        record_count: 2,
        created_at: "2026-03-01T00:00:00Z",
        updated_at: "2026-03-01T00:00:00Z",
        config: {
          stt_provider: "whisper",
          stt_model: "whisper-1",
        },
      }}
      speechCapabilities={{
        tts: [],
        stt: [
          {
            id: "deepgram",
            label: "Deepgram",
            enabled: true,
            voice_mode: "freeform_id",
            supports_preview: false,
            supports_cache_warm: false,
            supports_live_synthesis: false,
            supports_live_stream: true,
          },
        ],
      }}
      personaName="Concerned Parent"
      onClose={() => {}}
    />
  );

  assert.match(markup, />STT Provider</);
  assert.match(markup, />whisper \(unavailable\)</);
  assert.match(markup, />whisper-1</);
});
