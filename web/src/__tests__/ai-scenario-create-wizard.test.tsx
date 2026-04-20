import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { useForm } from "react-hook-form";
import {
  AIScenarioAdvancedRuntimeSettings,
  AIScenarioSpeechSettings,
} from "@/app/(dashboard)/ai-scenarios/_components/AIScenarioCreateWizard";
import { createEmptyAIScenarioEditorValues } from "@/lib/schemas/ai-scenario-editor";

test("AI scenario wizard advanced runtime section renders approved controls and excludes speech controls", () => {
  function Harness() {
    const { register, formState } = useForm({
      defaultValues: {
        ...createEmptyAIScenarioEditorValues(),
        language: "en-GB",
        turn_timeout_s: "30",
      },
    });

    return (
      <AIScenarioAdvancedRuntimeSettings
        open
        runtimeOverrideCount={2}
        register={register}
        errors={formState.errors}
        onToggle={() => {}}
      />
    );
  }

  const markup = renderToStaticMarkup(
    <Harness />
  );

  assert.match(markup, /ai-scenario-runtime-language-input/);
  assert.match(markup, /ai-scenario-runtime-stt-endpointing-input/);
  assert.match(markup, /ai-scenario-runtime-transcript-merge-window-input/);
  assert.match(markup, /ai-scenario-runtime-turn-timeout-input/);
  assert.match(markup, /ai-scenario-runtime-max-duration-input/);
  assert.match(markup, /ai-scenario-runtime-max-total-turns-input/);
  assert.match(markup, />2 overrides</);

  assert.doesNotMatch(markup, /name="tts_voice"/);
  assert.doesNotMatch(markup, /name="stt_provider"/);
  assert.doesNotMatch(markup, /name="stt_model"/);
  assert.doesNotMatch(markup, />TTS Voice</);
  assert.doesNotMatch(markup, />STT Provider</);
  assert.doesNotMatch(markup, />STT Model</);
});

test("AI scenario wizard speech section renders TTS and STT controls", () => {
  function Harness() {
    const { register, setValue, watch, formState } = useForm({
      defaultValues: {
        ...createEmptyAIScenarioEditorValues(),
        tts_voice: "openai:alloy",
        stt_provider: "deepgram",
        stt_model: "nova-2-phonecall",
      },
    });

    return (
      <AIScenarioSpeechSettings
        register={register}
        setValue={setValue}
        watch={watch}
        errors={formState.errors}
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
            {
              id: "azure",
              label: "Azure Speech",
              enabled: true,
              voice_mode: "freeform_id",
              supports_preview: false,
              supports_cache_warm: false,
              supports_live_synthesis: false,
              supports_live_stream: true,
            },
          ],
        }}
      />
    );
  }

  const markup = renderToStaticMarkup(<Harness />);

  assert.match(markup, /name="tts_voice"/);
  assert.match(markup, /ai-scenario-tts-provider-select/);
  assert.match(markup, /ai-scenario-tts-voice-select/);
  assert.match(markup, />TTS Provider</);
  assert.match(markup, />Voice</);
  assert.match(markup, /name="stt_provider"/);
  assert.match(markup, /name="stt_model"/);
  assert.match(markup, /ai-scenario-stt-provider-select/);
  assert.match(markup, /ai-scenario-stt-model-input/);
  assert.match(markup, />STT Provider</);
  assert.match(markup, />STT Model</);
  assert.match(markup, />Azure Speech</);
});

test("AI scenario wizard basic step defaults include namespace field", () => {
  const values = createEmptyAIScenarioEditorValues();

  assert.equal(values.namespace, "");
});

test("AI scenario wizard speech section preserves unavailable stored providers safely", () => {
  function Harness() {
    const { register, setValue, watch, formState } = useForm({
      defaultValues: {
        ...createEmptyAIScenarioEditorValues(),
        tts_voice: "elevenlabs:voice-123",
      },
    });

    return (
      <AIScenarioSpeechSettings
        register={register}
        setValue={setValue}
        watch={watch}
        errors={formState.errors}
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
      />
    );
  }

  const markup = renderToStaticMarkup(<Harness />);

  assert.match(markup, /Stored value uses an unavailable provider/);
  assert.match(markup, /elevenlabs:voice-123/);
  assert.match(markup, />Unavailable: elevenlabs</);
  assert.match(markup, />OpenAI</);
  assert.doesNotMatch(markup, /ai-scenario-tts-voice-select/);
});

test("AI scenario wizard speech section preserves unavailable stored STT providers safely", () => {
  function Harness() {
    const { register, setValue, watch, formState } = useForm({
      defaultValues: {
        ...createEmptyAIScenarioEditorValues(),
        stt_provider: "whisper",
        stt_model: "whisper-1",
      },
    });

    return (
      <AIScenarioSpeechSettings
        register={register}
        setValue={setValue}
        watch={watch}
        errors={formState.errors}
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
      />
    );
  }

  const markup = renderToStaticMarkup(<Harness />);

  assert.match(markup, /Stored value uses an unavailable STT provider/);
  assert.match(markup, />Unavailable: whisper</);
  assert.match(markup, /value="whisper-1"/);
  assert.match(markup, />Deepgram</);
});
