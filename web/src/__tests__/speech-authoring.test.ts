import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCanonicalTtsVoice,
  deriveSttAuthoringState,
  deriveTtsAuthoringState,
  getDefaultModelForSttProvider,
  getDefaultVoiceForTtsProvider,
  parseAuthoringTtsVoice,
} from "../lib/speech-authoring";

test("parseAuthoringTtsVoice defaults legacy values to openai", () => {
  const parsed = parseAuthoringTtsVoice("nova");

  assert.equal(parsed.providerId, "openai");
  assert.equal(parsed.voice, "nova");
  assert.equal(parsed.canonical, "openai:nova");
  assert.equal(parsed.usesImplicitProvider, true);
});

test("buildCanonicalTtsVoice preserves incomplete provider selections", () => {
  assert.equal(buildCanonicalTtsVoice("elevenlabs", ""), "elevenlabs:");
  assert.equal(buildCanonicalTtsVoice(" openai ", " nova "), "openai:nova");
});

test("deriveTtsAuthoringState hides disabled providers but preserves raw value", () => {
  const state = deriveTtsAuthoringState("elevenlabs:voice-123", {
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
  });

  assert.equal(state.currentProviderUnavailable, true);
  assert.equal(state.parsed.canonical, "elevenlabs:voice-123");
  assert.deepEqual(
    state.availableProviders.map((provider) => provider.id),
    ["openai"]
  );
  assert.equal(state.displayProviderId, "");
});

test("deriveTtsAuthoringState surfaces the implicit default for empty values", () => {
  const state = deriveTtsAuthoringState("", undefined);

  assert.equal(state.displayProviderId, "openai");
  assert.equal(state.displayVoice, "nova");
  assert.equal(state.currentProviderUnavailable, false);
  assert.equal(getDefaultVoiceForTtsProvider("openai"), "nova");
});

test("deriveSttAuthoringState defaults to Deepgram and preserves the current model value", () => {
  const state = deriveSttAuthoringState("", "nova-2-phonecall", {
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
  });

  assert.equal(state.displayProviderId, "deepgram");
  assert.equal(state.displayModel, "nova-2-phonecall");
  assert.equal(state.currentProviderUnavailable, false);
  assert.equal(getDefaultModelForSttProvider("deepgram"), "nova-2-general");
});

test("deriveSttAuthoringState supports Azure defaults from enabled capabilities", () => {
  const state = deriveSttAuthoringState("azure", "", {
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
  });

  assert.equal(state.displayProviderId, "azure");
  assert.equal(state.displayModel, "azure-default");
  assert.equal(getDefaultModelForSttProvider("azure"), "azure-default");
});

test("deriveSttAuthoringState preserves unavailable provider state", () => {
  const state = deriveSttAuthoringState("whisper", "whisper-large", {
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
  });

  assert.equal(state.currentProviderUnavailable, true);
  assert.equal(state.displayProviderId, "");
  assert.equal(state.displayModel, "whisper-large");
});
