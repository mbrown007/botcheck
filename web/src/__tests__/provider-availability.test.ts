import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSpeechCapabilitiesFromAvailableProviders,
  filterAvailableProvidersByCapability,
  formatAvailableProviderLabel,
  formatProviderCredentialSource,
} from "@/lib/provider-availability";

test("buildSpeechCapabilitiesFromAvailableProviders aggregates model providers into vendor authoring capabilities", () => {
  const capabilities = buildSpeechCapabilitiesFromAvailableProviders(
    [
      {
        provider_id: "openai:gpt-4o-mini-tts",
        vendor: "openai",
        model: "gpt-4o-mini-tts",
        capability: "tts",
        runtime_scopes: ["api", "agent"],
        credential_source: "env",
        configured: true,
        availability_status: "available",
        supports_tenant_credentials: false,
      },
      {
        provider_id: "azure:azure-speech",
        vendor: "azure",
        model: "azure-speech",
        capability: "stt",
        runtime_scopes: ["api", "agent"],
        credential_source: "db_encrypted",
        configured: true,
        availability_status: "available",
        supports_tenant_credentials: true,
      },
    ],
    undefined
  );

  assert.ok(capabilities);
  assert.ok(capabilities.tts);
  assert.ok(capabilities.stt);
  assert.equal(capabilities.tts.find((item) => item.id === "openai")?.enabled, true);
  assert.equal(capabilities.tts.find((item) => item.id === "elevenlabs")?.enabled, false);
  assert.equal(capabilities.stt.find((item) => item.id === "azure")?.enabled, true);
  assert.equal(capabilities.stt.find((item) => item.id === "deepgram")?.enabled, false);
});

test("buildSpeechCapabilitiesFromAvailableProviders keeps explicit empty availability from falling back to defaults", () => {
  const capabilities = buildSpeechCapabilitiesFromAvailableProviders([], undefined);

  assert.ok(capabilities);
  assert.ok(capabilities.tts);
  assert.ok(capabilities.stt);
  assert.equal(capabilities.tts.every((item) => item.enabled === false), true);
  assert.equal(capabilities.stt.every((item) => item.enabled === false), true);
});

test("provider availability helpers format provider labels and capability filters", () => {
  const providers = [
    {
      provider_id: "anthropic:claude-sonnet-4-6",
      vendor: "anthropic",
      model: "claude-sonnet-4-6",
      capability: "judge",
      runtime_scopes: ["judge"],
      credential_source: "db_encrypted",
      configured: true,
      availability_status: "available",
      supports_tenant_credentials: false,
    },
    {
      provider_id: "openai:gpt-4o-mini",
      vendor: "openai",
      model: "gpt-4o-mini",
      capability: "llm",
      runtime_scopes: ["api"],
      credential_source: "env",
      configured: true,
      availability_status: "available",
      supports_tenant_credentials: false,
    },
  ];

  assert.deepEqual(
    filterAvailableProvidersByCapability(providers, "judge").map((item) => item.provider_id),
    ["anthropic:claude-sonnet-4-6"]
  );
  assert.equal(formatAvailableProviderLabel(providers[1]), "openai:gpt-4o-mini");
  assert.equal(formatProviderCredentialSource("db_encrypted"), "stored");
  assert.equal(formatProviderCredentialSource("env"), "env");
});
